"""Data-access layer for the flight lookup index — SQLAlchemy ORM only.

Flights themselves are never stored (see ``services/flight_service.py``), but
the *search parameters* behind each issued flight ID are. Persisting that map
lets ``find_flight_by_id`` resolve any flight ID this deployment has ever
handed out — even after a restart or on a different worker process — by
re-running the deterministic generator for those params.
"""

from sqlalchemy import select

from app.db.base import Base
from app.db.models import FlightIndexRow


class FlightIndexRepository:
    """ORM-backed map of flight ID -> the search params that generated it."""

    def __init__(self, session_factory) -> None:
        self._sf = session_factory

    def init_db(self) -> None:
        Base.metadata.create_all(self._sf().get_bind(), checkfirst=True)

    def remember_many(self, rows: list[tuple[str, str, str, str]]) -> None:
        """Idempotently record (flight_id, origin, destination, departure_date).

        Portable insert-or-ignore: skip IDs already present, insert the rest.
        """
        if not rows:
            return
        ids = [r[0] for r in rows]
        with self._sf() as s:
            existing = set(
                s.scalars(
                    select(FlightIndexRow.flight_id).where(
                        FlightIndexRow.flight_id.in_(ids)
                    )
                ).all()
            )
            new_rows = [
                FlightIndexRow(
                    flight_id=fid, origin=o, destination=d, departure_date=dep
                )
                for (fid, o, d, dep) in rows
                if fid not in existing
            ]
            if new_rows:
                s.add_all(new_rows)
                s.commit()

    def lookup(self, flight_id: str) -> tuple[str, str, str] | None:
        with self._sf() as s:
            row = s.get(FlightIndexRow, flight_id)
            if row is None:
                return None
            return (row.origin, row.destination, row.departure_date)
