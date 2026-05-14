"""Data-access layer for bookings — the SQLite persistence, nothing else.

This is the ``crud`` tier: it knows how to read and write booking rows and
nothing about *why*. Business rules (pricing, looking up the referenced
flight/hotel, filtering, sorting) live in ``services/booking_service.py``.
"""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from app.schemas.booking import Booking

# One row per booking. The type-specific payload is kept as JSON text in
# `details` — it varies between flight and hotel bookings.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS bookings (
    id             TEXT PRIMARY KEY,
    type           TEXT NOT NULL,
    reference_id   TEXT NOT NULL,
    customer_name  TEXT NOT NULL,
    customer_email TEXT NOT NULL,
    total_price    REAL NOT NULL,
    currency       TEXT NOT NULL,
    status         TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    details        TEXT NOT NULL,
    notes          TEXT
)
"""

_COLUMNS = (
    "id",
    "type",
    "reference_id",
    "customer_name",
    "customer_email",
    "total_price",
    "currency",
    "status",
    "created_at",
    "details",
    "notes",
)


def _row_to_booking(row: sqlite3.Row) -> Booking:
    """Rebuild a ``Booking`` model from a database row."""
    return Booking(
        id=row["id"],
        type=row["type"],
        reference_id=row["reference_id"],
        customer_name=row["customer_name"],
        customer_email=row["customer_email"],
        total_price=row["total_price"],
        currency=row["currency"],
        status=row["status"],
        created_at=row["created_at"],
        details=json.loads(row["details"]),
        notes=row["notes"],
    )


class BookingRepository:
    """SQLite-backed store of booking rows."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Open a connection, commit on success, and always close it.

        A fresh connection per call keeps this safe across FastAPI's
        threadpool — sync endpoints each run in their own thread.
        """
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_db(self) -> None:
        """Create the bookings table if it does not exist. Called on startup."""
        with self._connect() as conn:
            conn.execute(_SCHEMA)

    def get(self, booking_id: str) -> Booking | None:
        """Return a booking by ID, or ``None`` if there is no such row."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM bookings WHERE id = ?", (booking_id,)
            ).fetchone()
        return _row_to_booking(row) if row is not None else None

    def list_all(self) -> list[Booking]:
        """Return every booking, newest first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM bookings ORDER BY created_at DESC"
            ).fetchall()
        return [_row_to_booking(row) for row in rows]

    def add(self, booking: Booking) -> Booking:
        """Insert a booking and return it unchanged."""
        values = (
            booking.id,
            booking.type.value,
            booking.reference_id,
            booking.customer_name,
            booking.customer_email,
            booking.total_price,
            booking.currency,
            booking.status.value,
            booking.created_at.isoformat(),
            json.dumps(booking.details, default=str),
            booking.notes,
        )
        placeholders = ", ".join("?" for _ in _COLUMNS)
        with self._connect() as conn:
            conn.execute(
                f"INSERT INTO bookings ({', '.join(_COLUMNS)}) VALUES ({placeholders})",
                values,
            )
        return booking
