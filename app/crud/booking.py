"""Data-access layer for bookings — the SQLite persistence, nothing else.

This is the ``crud`` tier: it knows how to read and write booking rows and
nothing about *why*. Business rules (pricing, looking up the referenced
flight/hotel, filtering, sorting) live in ``services/booking_service.py``.
"""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from app.crud._migrations import ensure_column, ensure_unique_partial_index
from app.schemas.booking import Booking, confirmation_code_for

# One row per booking. The type-specific payload is kept as JSON text in
# `details` — it varies between flight and hotel bookings. `idempotency_key`
# is the optional client-supplied key that makes booking POSTs replay-safe;
# it is persistence metadata, not part of the Booking resource itself.
# `confirmation_code` is derived deterministically from `id` (see
# `confirmation_code_for`) — storing it as its own column lets lookups by
# confirmation code use an index instead of scanning the whole table and
# rebuilding every model. The migration in `init_db` backfills it for any
# rows created before this column existed.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS bookings (
    id                 TEXT PRIMARY KEY,
    type               TEXT NOT NULL,
    reference_id       TEXT NOT NULL,
    customer_name      TEXT NOT NULL,
    customer_email     TEXT NOT NULL,
    total_price        REAL NOT NULL,
    currency           TEXT NOT NULL,
    status             TEXT NOT NULL,
    created_at         TEXT NOT NULL,
    details            TEXT NOT NULL,
    notes              TEXT,
    idempotency_key    TEXT,
    confirmation_code  TEXT
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
    "idempotency_key",
    "confirmation_code",
)


def _row_to_booking(row: sqlite3.Row) -> Booking:
    """Rebuild a ``Booking`` model from a database row."""
    details = json.loads(row["details"])
    # Backfill the discriminator on rows written before ``details`` became a
    # tagged union — ``row["type"]`` is the source of truth and matches the
    # ``kind`` literal on each details model.
    if isinstance(details, dict) and "kind" not in details:
        details["kind"] = row["type"]
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
        details=details,
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
        """Create the bookings table if it does not exist. Called on startup.

        Also runs tiny forward migrations: a ``bookings`` table created
        before a feature shipped is missing the column it needs, so add it
        in place rather than forcing the DB file to be recreated.
        """
        with self._connect() as conn:
            conn.execute(_SCHEMA)
            ensure_column(conn, "bookings", "idempotency_key")
            if ensure_column(conn, "bookings", "confirmation_code"):
                # Backfill the new column for rows that pre-date it. The code
                # is deterministic from the UUID, so this is a one-shot
                # idempotent migration — re-running init_db is a no-op.
                rows = conn.execute(
                    "SELECT id FROM bookings WHERE confirmation_code IS NULL"
                ).fetchall()
                conn.executemany(
                    "UPDATE bookings SET confirmation_code = ? WHERE id = ?",
                    [(confirmation_code_for(r["id"]), r["id"]) for r in rows],
                )
            # A UNIQUE index makes the idempotency check atomic: two concurrent
            # POSTs with the same key can't both pass the replay check and
            # insert — the second INSERT fails, and `add()` returns the row the
            # winner created. SQLite can't add a UNIQUE column via ALTER TABLE,
            # so the constraint lives in this index instead. Partial (`WHERE
            # ... IS NOT NULL`) so the many keyless bookings aren't forced
            # unique on NULL.
            ensure_unique_partial_index(conn, "bookings", "idempotency_key")
            # Plain (non-unique) index on confirmation_code — the alphabet is
            # 31 chars × 6 positions ≈ 887M codes; collisions are extremely
            # unlikely but a UNIQUE index would crash on the off chance.
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_bookings_confirmation_code "
                "ON bookings (confirmation_code)"
            )

    def ping(self) -> bool:
        """Return True if the database is reachable (cheap SELECT 1)."""
        with self._connect() as conn:
            conn.execute("SELECT 1")
        return True

    def get(self, booking_id: str) -> Booking | None:
        """Return a booking by ID, or ``None`` if there is no such row."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM bookings WHERE id = ?", (booking_id,)
            ).fetchone()
        return _row_to_booking(row) if row is not None else None

    def get_by_idempotency_key(self, key: str) -> Booking | None:
        """Return the booking previously stored under ``key``, or ``None``.

        Used to make booking POSTs replay-safe: a repeat request carrying a
        key already on file returns the original booking instead of creating
        a duplicate.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM bookings WHERE idempotency_key = ?", (key,)
            ).fetchone()
        return _row_to_booking(row) if row is not None else None

    def get_by_confirmation_code(self, code: str) -> Booking | None:
        """Return the booking with this 6-char confirmation code, or ``None``.

        Uses the ``ix_bookings_confirmation_code`` index — O(log n) instead
        of the scan-and-rebuild approach the service used to do.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM bookings WHERE confirmation_code = ?",
                (code.strip().upper(),),
            ).fetchone()
        return _row_to_booking(row) if row is not None else None

    def list_all(self) -> list[Booking]:
        """Return every booking, newest first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM bookings ORDER BY created_at DESC"
            ).fetchall()
        return [_row_to_booking(row) for row in rows]

    def update_status(self, booking_id: str, status: str) -> bool:
        """Set a booking's ``status``. Returns ``True`` if a row was updated."""
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE bookings SET status = ? WHERE id = ?",
                (status, booking_id),
            )
            return cursor.rowcount > 0

    def add(self, booking: Booking, idempotency_key: str | None = None) -> Booking:
        """Insert a booking and return it.

        ``idempotency_key`` is stored alongside the row (when supplied) so a
        later repeat request can be detected via
        :meth:`get_by_idempotency_key`.

        If a concurrent request already inserted a row under the same
        ``idempotency_key``, the UNIQUE index makes this INSERT fail with an
        ``IntegrityError``; rather than surface that, we return the row the
        winner created — so racing requests still get one shared booking.
        """
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
            json.dumps(booking.details.model_dump(mode="json")),
            booking.notes,
            idempotency_key,
            booking.confirmation_code,
        )
        placeholders = ", ".join("?" for _ in _COLUMNS)
        try:
            with self._connect() as conn:
                conn.execute(
                    f"INSERT INTO bookings ({', '.join(_COLUMNS)}) "
                    f"VALUES ({placeholders})",
                    values,
                )
        except sqlite3.IntegrityError:
            # Lost an idempotency-key race — return the winner's booking.
            if idempotency_key is not None:
                existing = self.get_by_idempotency_key(idempotency_key)
                if existing is not None:
                    return existing
            raise
        return booking
