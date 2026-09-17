"""Data-access for airports. The ORM PK is ``iata`` but the ``Airport`` schema names it ``code``, so the repo constructs ``Airport`` explicitly to map ``iata → code``."""

from sqlalchemy import select

from app.db import models
from app.repositories.base import Repo
from app.schemas.airport import Airport


def _row_to_airport(row: models.Airport) -> Airport:
    return Airport(
        code=row.iata,
        name=row.name,
        city=row.city,
        country=row.country,
    )


class AirportRepository(Repo):
    """Read-only store of airport rows behind a ``session_factory``."""

    def list(self) -> list[Airport]:
        """Return every airport as an ``Airport`` schema, ordered by ``position`` (stable across engines and matches the order board_service samples routes from)."""
        with self._session() as s:
            rows = s.scalars(
                select(models.Airport).order_by(models.Airport.position)
            ).all()
            return [_row_to_airport(r) for r in rows]

    def get(self, code: str) -> Airport | None:
        """Return the airport for an IATA ``code`` (upper-cased), or ``None``."""
        with self._session() as s:
            row = s.scalars(
                select(models.Airport).where(models.Airport.iata == code.upper())
            ).first()
            return _row_to_airport(row) if row is not None else None
