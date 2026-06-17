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

from app.schemas.trip import Trip, TripItem

_TRIPS_SCHEMA = """
CREATE TABLE IF NOT EXISTS trips (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    city        TEXT,
    start_date  TEXT,
    end_date    TEXT,
    travelers   INTEGER NOT NULL,
    notes       TEXT,
    created_at  TEXT NOT NULL
)
"""

_ITEMS_SCHEMA = """
CREATE TABLE IF NOT EXISTS trip_items (
    id          TEXT PRIMARY KEY,
    trip_id     TEXT NOT NULL,
    day         INTEGER NOT NULL,
    sort_order  INTEGER NOT NULL,
    kind        TEXT NOT NULL,
    title       TEXT NOT NULL,
    place_id    TEXT,
    booking_id  TEXT,
    start_time  TEXT,
    notes       TEXT
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


def _trip_values(trip: Trip) -> tuple:
    return (
        trip.id,
        trip.title,
        trip.city,
        _iso(trip.start_date),
        _iso(trip.end_date),
        trip.travelers,
        trip.notes,
        _iso(trip.created_at),
    )


def _item_values(item: TripItem) -> tuple:
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
        """Create the trips/trip_items tables and item index if absent."""
        with self._connect() as conn:
            conn.execute(_TRIPS_SCHEMA)
            conn.execute(_ITEMS_SCHEMA)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_trip_items_trip_id "
                "ON trip_items (trip_id)"
            )

    def _insert_item(self, conn: sqlite3.Connection, item: TripItem) -> None:
        placeholders = ", ".join("?" for _ in _ITEM_COLUMNS)
        conn.execute(
            f"INSERT INTO trip_items ({', '.join(_ITEM_COLUMNS)}) "
            f"VALUES ({placeholders})",
            _item_values(item),
        )

    def create_trip(self, trip: Trip) -> Trip:
        """Insert a trip and all of its items in one transaction."""
        trip_placeholders = ", ".join("?" for _ in _TRIP_COLUMNS)
        with self._connect() as conn:
            conn.execute(
                f"INSERT INTO trips ({', '.join(_TRIP_COLUMNS)}) "
                f"VALUES ({trip_placeholders})",
                _trip_values(trip),
            )
            for item in trip.items:
                self._insert_item(conn, item)
        return trip

    def get_trip(self, trip_id: str) -> Trip | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM trips WHERE id = ?", (trip_id,)
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
                "SELECT * FROM trips ORDER BY created_at DESC"
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

    def delete_trip(self, trip_id: str) -> bool:
        """Delete a trip and its items. Returns True if the trip existed."""
        with self._connect() as conn:
            conn.execute("DELETE FROM trip_items WHERE trip_id = ?", (trip_id,))
            cursor = conn.execute("DELETE FROM trips WHERE id = ?", (trip_id,))
            return cursor.rowcount > 0

    def add_item(self, item: TripItem) -> TripItem:
        with self._connect() as conn:
            self._insert_item(conn, item)
        return item

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
