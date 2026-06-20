"""Data-access layer for the flight lookup index — SQLAlchemy ORM only.

Flights themselves are never stored (see ``services/flight_service.py``), but
the *search parameters* behind each issued flight ID are. Persisting that map
lets ``find_flight_by_id`` resolve any flight ID this deployment has ever
handed out — even after a restart or on a different worker process — by
re-running the deterministic generator for those params.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import models
from app.db.base import Base, new_uuid


class FlightIndexRepository:
    """ORM-backed map of flight ID -> the search params that generated it."""

    def __init__(self, session_factory) -> None:
        self._sf = session_factory

    def init_db(self) -> None:
        Base.metadata.create_all(self._sf().get_bind(), checkfirst=True)

    def remember_many(self, rows: list[tuple[str, str, str, str]]) -> None:
        """Idempotently record (flight_id, origin, destination, departure_date).

        Atomic insert-or-ignore via a dialect-aware ``ON CONFLICT DO NOTHING``.
        Doing the insert and the conflict-skip in one statement closes the
        read-modify-write window that a prior SELECT-then-INSERT had: two
        concurrent searches for the same not-yet-indexed route would both find
        nothing, both insert the same ``flight_id``, and the loser's COMMIT
        would raise an ``IntegrityError`` (PK violation) -> HTTP 500. The
        upsert-ignore inserts every new row and silently drops duplicates.
        """
        if not rows:
            return
        now = datetime.now(timezone.utc).isoformat()
        values = [
            {
                "id": new_uuid(),
                "flight_id": fid,
                "origin": o,
                "destination": d,
                "departure_date": dep,
                "created_at": now,
                "updated_at": now,
            }
            for (fid, o, d, dep) in rows
        ]
        with self._sf() as s:
            dialect = s.get_bind().dialect.name
            if dialect == "postgresql":
                from sqlalchemy.dialects.postgresql import insert as pg_insert

                stmt = pg_insert(models.FlightIndex).values(values)
                stmt = stmt.on_conflict_do_nothing(index_elements=["flight_id"])
                s.execute(stmt)
                s.commit()
            elif dialect == "sqlite":
                from sqlalchemy.dialects.sqlite import insert as sqlite_insert

                stmt = sqlite_insert(models.FlightIndex).values(values)
                stmt = stmt.on_conflict_do_nothing(index_elements=["flight_id"])
                s.execute(stmt)
                s.commit()
            else:
                # Other dialects: no portable Core ON CONFLICT. Insert each row
                # on its own and swallow duplicates so the result is still an
                # idempotent insert-or-ignore.
                for value in values:
                    try:
                        with s.begin_nested():
                            s.execute(
                                models.FlightIndex.__table__.insert().values(value)
                            )
                    except IntegrityError:
                        pass
                s.commit()

    def lookup(self, flight_id: str) -> tuple[str, str, str] | None:
        with self._sf() as s:
            row = s.scalars(
                select(models.FlightIndex).where(
                    models.FlightIndex.flight_id == flight_id
                )
            ).first()
            if row is None:
                return None
            return (row.origin, row.destination, row.departure_date)
