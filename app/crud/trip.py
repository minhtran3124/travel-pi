"""Data-access layer for trips — the SQLite persistence, nothing else.

The ``crud`` tier: it reads and writes trip rows and knows nothing about
*why*. Business rules (resolving the destination city, validating the
booking/place references, expanding the detail view) live in
``services/trip_service.py``. Mirrors ``crud/booking.py`` deliberately —
trips are the second piece of mutable state in the API.
"""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from app.schemas.trip import Trip, TripItem

# One row per trip. ``booking_ids`` and ``items`` are variable-length, so
# they are stored as JSON text. ``confirmation_code`` is derived from ``id``
# (see ``trip_confirmation_code``) but stored in its own indexed column so a
# lookup by code doesn't scan the table. ``idempotency_key`` makes
# ``POST /trips`` replay-safe, the same as bookings.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS trips (
    id                 TEXT PRIMARY KEY,
    name               TEXT NOT NULL,
    destination_city   TEXT NOT NULL,
    country            TEXT NOT NULL,
    start_date         TEXT NOT NULL,
    end_date           TEXT NOT NULL,
    booking_ids        TEXT NOT NULL,
    items              TEXT NOT NULL,
    status             TEXT NOT NULL,
    notes              TEXT,
    created_at         TEXT NOT NULL,
    idempotency_key    TEXT,
    confirmation_code  TEXT
)
"""

_COLUMNS = (
    "id",
    "name",
    "destination_city",
    "country",
    "start_date",
    "end_date",
    "booking_ids",
    "items",
    "status",
    "notes",
    "created_at",
    "idempotency_key",
    "confirmation_code",
)


def _row_to_trip(row: sqlite3.Row) -> Trip:
    """Rebuild a ``Trip`` model from a database row."""
    return Trip(
        id=row["id"],
        name=row["name"],
        destination_city=row["destination_city"],
        country=row["country"],
        start_date=row["start_date"],
        end_date=row["end_date"],
        booking_ids=json.loads(row["booking_ids"]),
        items=[TripItem(**item) for item in json.loads(row["items"])],
        status=row["status"],
        notes=row["notes"],
        created_at=row["created_at"],
    )


class TripRepository:
    """SQLite-backed store of trip rows."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Open a connection, commit on success, and always close it.

        A fresh connection per call keeps this safe across FastAPI's
        threadpool — same pattern (and WAL settings) as ``BookingRepository``.
        """
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_db(self) -> None:
        """Create the trips table + indexes if they do not exist (startup)."""
        with self._connect() as conn:
            conn.execute(_SCHEMA)
            # Atomic idempotency for POST /trips — see crud/booking.py for the
            # full rationale. Partial so the many keyless trips aren't forced
            # unique on NULL.
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_trips_idempotency_key "
                "ON trips (idempotency_key) WHERE idempotency_key IS NOT NULL"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_trips_confirmation_code "
                "ON trips (confirmation_code)"
            )

    def _values(self, trip: Trip, idempotency_key: str | None) -> tuple:
        """Flatten a ``Trip`` into the column tuple for INSERT/UPDATE."""
        return (
            trip.id,
            trip.name,
            trip.destination_city,
            trip.country,
            trip.start_date,
            trip.end_date,
            json.dumps(trip.booking_ids),
            json.dumps([item.model_dump() for item in trip.items]),
            trip.status.value,
            trip.notes,
            trip.created_at.isoformat(),
            idempotency_key,
            trip.confirmation_code,
        )

    def get(self, trip_id: str) -> Trip | None:
        """Return a trip by ID, or ``None`` if there is no such row."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM trips WHERE id = ?", (trip_id,)
            ).fetchone()
        return _row_to_trip(row) if row is not None else None

    def get_by_confirmation_code(self, code: str) -> Trip | None:
        """Return the trip with this ``TRP-XXXXXX`` code, or ``None``."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM trips WHERE confirmation_code = ?",
                (code.strip().upper(),),
            ).fetchone()
        return _row_to_trip(row) if row is not None else None

    def get_by_idempotency_key(self, key: str) -> Trip | None:
        """Return the trip previously stored under ``key``, or ``None``."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM trips WHERE idempotency_key = ?", (key,)
            ).fetchone()
        return _row_to_trip(row) if row is not None else None

    def list_all(self) -> list[Trip]:
        """Return every trip, newest first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM trips ORDER BY created_at DESC"
            ).fetchall()
        return [_row_to_trip(row) for row in rows]

    def add(self, trip: Trip, idempotency_key: str | None = None) -> Trip:
        """Insert a trip and return it.

        If a concurrent request already inserted a row under the same
        ``idempotency_key``, the UNIQUE index makes this INSERT fail; we
        return the row the winner created instead of surfacing the error.
        """
        placeholders = ", ".join("?" for _ in _COLUMNS)
        try:
            with self._connect() as conn:
                conn.execute(
                    f"INSERT INTO trips ({', '.join(_COLUMNS)}) "
                    f"VALUES ({placeholders})",
                    self._values(trip, idempotency_key),
                )
        except sqlite3.IntegrityError:
            if idempotency_key is not None:
                existing = self.get_by_idempotency_key(idempotency_key)
                if existing is not None:
                    return existing
            raise
        return trip

    def update(self, trip: Trip) -> bool:
        """Overwrite a trip's mutable columns. Returns ``True`` if a row matched.

        ``id``, ``created_at``, ``idempotency_key`` and ``confirmation_code``
        never change, so they are not in the SET list.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE trips SET "
                "name = ?, destination_city = ?, country = ?, start_date = ?, "
                "end_date = ?, booking_ids = ?, items = ?, status = ?, notes = ? "
                "WHERE id = ?",
                (
                    trip.name,
                    trip.destination_city,
                    trip.country,
                    trip.start_date,
                    trip.end_date,
                    json.dumps(trip.booking_ids),
                    json.dumps([item.model_dump() for item in trip.items]),
                    trip.status.value,
                    trip.notes,
                    trip.id,
                ),
            )
            return cursor.rowcount > 0

    def update_status(self, trip_id: str, status: str) -> bool:
        """Set a trip's ``status``. Returns ``True`` if a row was updated."""
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE trips SET status = ? WHERE id = ?",
                (status, trip_id),
            )
            return cursor.rowcount > 0
