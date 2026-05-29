"""Data-access layer for the flight lookup index — SQLite persistence only.

Flights themselves are never stored (see ``services/flight_service.py``), but
the *search parameters* behind each issued flight ID are. Persisting that map
lets ``find_flight_by_id`` resolve any flight ID this deployment has ever
handed out — even after a restart or on a different worker process — by
re-running the deterministic generator for those params.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

# One row per flight ID ever generated. The columns are exactly what
# `generate_flights` needs to deterministically reproduce the flight.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS flight_index (
    flight_id       TEXT PRIMARY KEY,
    origin          TEXT NOT NULL,
    destination     TEXT NOT NULL,
    departure_date  TEXT NOT NULL
)
"""

_INSERT = (
    "INSERT OR IGNORE INTO flight_index "
    "(flight_id, origin, destination, departure_date) VALUES (?, ?, ?, ?)"
)


class FlightIndexRepository:
    """SQLite-backed map of flight ID → the search params that generated it."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Open a connection, commit on success, and always close it.

        A fresh connection per call keeps this safe across FastAPI's
        threadpool — the same pattern as ``BookingRepository``.
        """
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        # WAL for concurrent readers/writer under the threadpool — same
        # rationale as ``BookingRepository._connect``.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_db(self) -> None:
        """Create the flight_index table if it does not exist. Called on startup."""
        with self._connect() as conn:
            conn.execute(_SCHEMA)

    def remember_many(
        self, rows: list[tuple[str, str, str, str]]
    ) -> None:
        """Record ``(flight_id, origin, destination, departure_date)`` rows.

        ``INSERT OR IGNORE`` makes this idempotent — re-recording a flight ID
        already on file is a no-op, so callers need not check first.
        """
        if not rows:
            return
        with self._connect() as conn:
            conn.executemany(_INSERT, rows)

    def lookup(self, flight_id: str) -> tuple[str, str, str] | None:
        """Return ``(origin, destination, departure_date)`` for a flight ID.

        Returns ``None`` if the ID was never issued by this deployment.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT origin, destination, departure_date "
                "FROM flight_index WHERE flight_id = ?",
                (flight_id,),
            ).fetchone()
        if row is None:
            return None
        return (row["origin"], row["destination"], row["departure_date"])
