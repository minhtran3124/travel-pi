"""Data-access layer for trips — SQLite persistence, nothing else.

The ``crud`` tier reads/writes trip and trip_item rows; business rules
(ID generation, existence checks, 404s) live in
``services/trip_service.py``. Mirrors ``crud/booking.py``: a fresh
connection per call (threadpool-safe for sync endpoints), idempotent
``init_db``.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from app.crud._migrations import ensure_column, ensure_unique_partial_index
from app.schemas.trip import Trip, TripItem

_TRIPS_SCHEMA = """
CREATE TABLE IF NOT EXISTS trips (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    city            TEXT,
    start_date      TEXT,
    end_date        TEXT,
    travelers       INTEGER NOT NULL,
    notes           TEXT,
    created_at      TEXT NOT NULL,
    idempotency_key TEXT,
    deleted_at      TEXT
)
"""

_ITEMS_SCHEMA = """
CREATE TABLE IF NOT EXISTS trip_items (
    id              TEXT PRIMARY KEY,
    trip_id         TEXT NOT NULL,
    day             INTEGER NOT NULL,
    sort_order      INTEGER NOT NULL,
    kind            TEXT NOT NULL,
    title           TEXT NOT NULL,
    place_id        TEXT,
    booking_id      TEXT,
    start_time      TEXT,
    notes           TEXT,
    idempotency_key TEXT
)
"""

_LINKS_SCHEMA = """
CREATE TABLE IF NOT EXISTS trip_place_link (
    id        TEXT PRIMARY KEY,
    trip_id   TEXT NOT NULL,
    place_id  TEXT NOT NULL,
    source    TEXT NOT NULL,
    added_at  TEXT NOT NULL
)
"""

_TRIP_COLUMNS = (
    "id",
    "title",
    "city",
    "start_date",
    "end_date",
    "travelers",
    "notes",
    "created_at",
    "idempotency_key",
)

_ITEM_COLUMNS = (
    "id",
    "trip_id",
    "day",
    "sort_order",
    "kind",
    "title",
    "place_id",
    "booking_id",
    "start_time",
    "notes",
    "idempotency_key",
)


def _iso(value) -> str | None:
    """Serialise a date/datetime to ISO text, passing through None and str."""
    return value.isoformat() if hasattr(value, "isoformat") else value


def _row_to_item(row: sqlite3.Row) -> TripItem:
    return TripItem(
        id=row["id"],
        trip_id=row["trip_id"],
        day=row["day"],
        sort_order=row["sort_order"],
        kind=row["kind"],
        title=row["title"],
        place_id=row["place_id"],
        booking_id=row["booking_id"],
        start_time=row["start_time"],
        notes=row["notes"],
    )


def _row_to_trip(row: sqlite3.Row, item_rows: list[sqlite3.Row]) -> Trip:
    items = sorted(
        (_row_to_item(r) for r in item_rows), key=lambda i: (i.day, i.sort_order)
    )
    return Trip(
        id=row["id"],
        title=row["title"],
        city=row["city"],
        start_date=row["start_date"],
        end_date=row["end_date"],
        travelers=row["travelers"],
        notes=row["notes"],
        created_at=row["created_at"],
        items=items,
    )


def _trip_values(trip: Trip, idempotency_key: str | None) -> tuple:
    return (
        trip.id,
        trip.title,
        trip.city,
        _iso(trip.start_date),
        _iso(trip.end_date),
        trip.travelers,
        trip.notes,
        _iso(trip.created_at),
        idempotency_key,
    )


def _item_values(item: TripItem, idempotency_key: str | None) -> tuple:
    return (
        item.id,
        item.trip_id,
        item.day,
        item.sort_order,
        item.kind.value,
        item.title,
        item.place_id,
        item.booking_id,
        item.start_time,
        item.notes,
        idempotency_key,
    )


class TripRepository:
    """SQLite-backed store of trip + trip_item rows."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_db(self) -> None:
        """Create the trips/trip_items tables and item index if absent.

        Also idempotently migrates legacy trip_items tables that pre-date the
        booking_id column (ALTER TABLE is safe to skip when the column already
        exists — guarded by the PRAGMA check).
        """
        with self._connect() as conn:
            conn.execute(_TRIPS_SCHEMA)
            conn.execute(_ITEMS_SCHEMA)
            conn.execute(_LINKS_SCHEMA)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_trip_items_trip_id "
                "ON trip_items (trip_id)"
            )
            # One shortlist entry per (trip, place, source). A plain composite
            # UNIQUE index (not the single-column partial helper) — all three
            # columns are NOT NULL, so no partial WHERE is needed.
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_trip_place_link_unique "
                "ON trip_place_link (trip_id, place_id, source)"
            )
            # Add booking_id to legacy tables that were created before this column.
            ensure_column(conn, "trip_items", "booking_id")
            # Add idempotency_key to legacy trips/trip_items tables, then a
            # UNIQUE partial index per table — the constraint makes concurrent
            # same-key POSTs collide so only one row wins (mirrors bookings).
            # Partial (WHERE ... IS NOT NULL) so keyless rows aren't forced
            # unique on NULL.
            for table in ("trips", "trip_items"):
                ensure_column(conn, table, "idempotency_key")
                ensure_unique_partial_index(conn, table, "idempotency_key")
            # Add deleted_at to legacy trips tables (soft-delete tombstone).
            ensure_column(conn, "trips", "deleted_at")

    def _insert_item(
        self,
        conn: sqlite3.Connection,
        item: TripItem,
        idempotency_key: str | None = None,
    ) -> None:
        placeholders = ", ".join("?" for _ in _ITEM_COLUMNS)
        conn.execute(
            f"INSERT INTO trip_items ({', '.join(_ITEM_COLUMNS)}) "
            f"VALUES ({placeholders})",
            _item_values(item, idempotency_key),
        )

    def create_trip(self, trip: Trip, idempotency_key: str | None = None) -> Trip:
        """Insert a trip and all of its items in one transaction.

        ``idempotency_key`` is stored on the trip row so a repeat request can
        be detected via :meth:`get_trip_by_idempotency_key`. If a concurrent
        request already inserted a trip under the same key, the UNIQUE index
        makes this INSERT fail; we return the winner's trip instead of raising.
        """
        trip_placeholders = ", ".join("?" for _ in _TRIP_COLUMNS)
        try:
            with self._connect() as conn:
                conn.execute(
                    f"INSERT INTO trips ({', '.join(_TRIP_COLUMNS)}) "
                    f"VALUES ({trip_placeholders})",
                    _trip_values(trip, idempotency_key),
                )
                for item in trip.items:
                    self._insert_item(conn, item)
        except sqlite3.IntegrityError:
            if idempotency_key is not None:
                existing = self.get_trip_by_idempotency_key(idempotency_key)
                if existing is not None:
                    return existing
            raise
        return trip

    def get_trip(self, trip_id: str) -> Trip | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM trips WHERE id = ? AND deleted_at IS NULL", (trip_id,)
            ).fetchone()
            if row is None:
                return None
            item_rows = conn.execute(
                "SELECT * FROM trip_items WHERE trip_id = ?", (trip_id,)
            ).fetchall()
        return _row_to_trip(row, item_rows)

    def list_trips(self) -> list[Trip]:
        """Return every trip (newest first) with its items attached."""
        with self._connect() as conn:
            trip_rows = conn.execute(
                "SELECT * FROM trips WHERE deleted_at IS NULL ORDER BY created_at DESC"
            ).fetchall()
            item_rows = conn.execute("SELECT * FROM trip_items").fetchall()
        by_trip: dict[str, list[sqlite3.Row]] = {}
        for r in item_rows:
            by_trip.setdefault(r["trip_id"], []).append(r)
        return [_row_to_trip(t, by_trip.get(t["id"], [])) for t in trip_rows]

    def update_trip(self, trip: Trip) -> bool:
        """Replace a trip's top-level columns. Returns True if a row changed."""
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE trips SET title = ?, city = ?, start_date = ?, "
                "end_date = ?, travelers = ?, notes = ? WHERE id = ?",
                (
                    trip.title,
                    trip.city,
                    _iso(trip.start_date),
                    _iso(trip.end_date),
                    trip.travelers,
                    trip.notes,
                    trip.id,
                ),
            )
            return cursor.rowcount > 0

    def delete_trip(self, trip_id: str, *, when: str) -> bool:
        """Soft-delete: stamp deleted_at, keep the row. True if it existed and was live.

        The idempotency_key is cleared on tombstoning: it is only meaningful for
        replaying *live* trips, and the UNIQUE key index spans all rows — leaving
        it would make a later create that reuses the key collide with the dead
        row (which the deleted_at-filtered replay lookup can't recover).
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE trips SET deleted_at = ?, idempotency_key = NULL "
                "WHERE id = ? AND deleted_at IS NULL",
                (when, trip_id),
            )
            return cursor.rowcount > 0

    def add_item(self, item: TripItem, idempotency_key: str | None = None) -> TripItem:
        """Insert an item and return it.

        ``idempotency_key`` is stored on the row so a repeat request can be
        detected via :meth:`get_item_by_idempotency_key`. If a concurrent
        request already inserted an item under the same key, the UNIQUE index
        makes this INSERT fail; we return the winner's item instead of raising.
        """
        try:
            with self._connect() as conn:
                self._insert_item(conn, item, idempotency_key)
        except sqlite3.IntegrityError:
            if idempotency_key is not None:
                existing = self.get_item_by_idempotency_key(idempotency_key)
                if existing is not None:
                    return existing
            raise
        return item

    def get_trip_by_idempotency_key(self, key: str) -> Trip | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM trips WHERE idempotency_key = ? AND deleted_at IS NULL",
                (key,),
            ).fetchone()
            if row is None:
                return None
            items = conn.execute(
                "SELECT * FROM trip_items WHERE trip_id = ?", (row["id"],)
            ).fetchall()
        return _row_to_trip(row, items)

    def get_item_by_idempotency_key(self, key: str) -> TripItem | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM trip_items WHERE idempotency_key = ?", (key,)
            ).fetchone()
        return _row_to_item(row) if row is not None else None

    def get_item(self, item_id: str) -> TripItem | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM trip_items WHERE id = ?", (item_id,)
            ).fetchone()
        return _row_to_item(row) if row is not None else None

    def update_item(self, item: TripItem) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE trip_items SET day = ?, sort_order = ?, kind = ?, "
                "title = ?, place_id = ?, booking_id = ?, start_time = ?, notes = ? WHERE id = ?",
                (
                    item.day,
                    item.sort_order,
                    item.kind.value,
                    item.title,
                    item.place_id,
                    item.booking_id,
                    item.start_time,
                    item.notes,
                    item.id,
                ),
            )
            return cursor.rowcount > 0

    def delete_item(self, item_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM trip_items WHERE id = ?", (item_id,))
            return cursor.rowcount > 0

    # --- trip_place_link (shortlist) ------------------------------------- #

    def add_trip_place(
        self, link_id: str, trip_id: str, place_id: str, source: str, added_at: str
    ) -> None:
        """Insert a shortlist link. Re-raises sqlite3.IntegrityError on the
        (trip_id, place_id, source) UNIQUE collision — the service maps it
        to a 409."""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO trip_place_link (id, trip_id, place_id, source, added_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (link_id, trip_id, place_id, source, added_at),
            )

    def list_trip_places(self, trip_id: str) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM trip_place_link WHERE trip_id = ? ORDER BY added_at",
                (trip_id,),
            ).fetchall()

    def get_trip_place(self, link_id: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM trip_place_link WHERE id = ?", (link_id,)
            ).fetchone()

    def delete_trip_place(self, trip_id: str, link_id: str) -> bool:
        """Delete a shortlist link scoped to its trip. True if a row was removed."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM trip_place_link WHERE id = ? AND trip_id = ?",
                (link_id, trip_id),
            )
            return cursor.rowcount > 0
