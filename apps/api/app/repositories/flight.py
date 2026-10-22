"""Data-access for the flight lookup index. Flights are never stored, but the search params behind each issued flight ID are — so ``find_flight_by_id`` can re-resolve any ID this deployment handed out by re-running the deterministic generator."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import models
from app.db.base import Base, new_uuid
from app.repositories.base import Repo


class FlightIndexRepository(Repo):
    """ORM-backed map of flight ID -> the search params that generated it."""

    def init_db(self) -> None:
        Base.metadata.create_all(self._bind(), checkfirst=True)

    def remember_many(self, rows: list[tuple[str, str, str, str]]) -> None:
        """Idempotently record (flight_id, origin, destination, departure_date) via a dialect-aware ON CONFLICT DO NOTHING — closes the read-modify-write race two concurrent searches for the same route would hit."""
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
        with self._session() as s:
            dialect = s.get_bind().dialect.name
            if dialect == "postgresql":
                from sqlalchemy.dialects.postgresql import insert as pg_insert

                stmt = pg_insert(models.FlightIndex).values(values)
                stmt = stmt.on_conflict_do_nothing(index_elements=["flight_id"])
                s.execute(stmt)
                self._commit(s)
            elif dialect == "sqlite":
                from sqlalchemy.dialects.sqlite import insert as sqlite_insert

                stmt = sqlite_insert(models.FlightIndex).values(values)
                stmt = stmt.on_conflict_do_nothing(index_elements=["flight_id"])
                s.execute(stmt)
                self._commit(s)
            else:
                # Other dialects: no portable Core ON CONFLICT — insert each row and swallow duplicates.
                for value in values:
                    try:
                        with s.begin_nested():
                            s.execute(
                                models.FlightIndex.__table__.insert().values(value)
                            )
                    except IntegrityError:
                        pass
                self._commit(s)

    def known_ids(self, ids: list[str]) -> set[str]:
        """Return the subset of ``ids`` present as ``flight_id`` rows; empty input skips the query."""
        if not ids:
            return set()
        with self._session() as s:
            return set(
                s.scalars(
                    select(models.FlightIndex.flight_id).where(
                        models.FlightIndex.flight_id.in_(ids)
                    )
                ).all()
            )

    def lookup(self, flight_id: str) -> tuple[str, str, str] | None:
        with self._session() as s:
            row = s.scalars(
                select(models.FlightIndex).where(
                    models.FlightIndex.flight_id == flight_id
                )
            ).first()
            if row is None:
                return None
            return (row.origin, row.destination, row.departure_date)
