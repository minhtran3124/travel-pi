"""Data-access for airports — SQLAlchemy ORM reads, no business logic.

The ORM primary key is ``iata`` but the ``Airport`` Pydantic schema names the
field ``code`` — the repo constructs ``Airport`` explicitly (no
``model_validate``) to map ``iata → code``.
"""

from sqlalchemy import select

from app.db import models
from app.schemas.airport import Airport


def _row_to_airport(row: models.Airport) -> Airport:
    return Airport(
        code=row.iata,
        name=row.name,
        city=row.city,
        country=row.country,
    )


class AirportRepository:
    """Read-only store of airport rows behind a ``session_factory``."""

    def __init__(self, session_factory) -> None:
        self._sf = session_factory

    def list(self) -> list[Airport]:
        """Return every supported airport as an ``Airport`` schema.

        Ordered by ``position`` (the ``AIRPORTS`` dict insertion order) so the
        listing is stable across engines AND matches the pre-migration order
        board_service samples its routes from (SQLite and Postgres make no
        row-order guarantee otherwise).
        """
        with self._sf() as s:
            rows = s.scalars(
                select(models.Airport).order_by(models.Airport.position)
            ).all()
            return [_row_to_airport(r) for r in rows]

    def get(self, code: str) -> Airport | None:
        """Return the airport for an IATA ``code`` (upper-cased), or ``None``.

        Matches ``airport_service.get_airport`` — the lookup upper-cases the
        input so ``"dad"`` resolves the same as ``"DAD"``.
        """
        with self._sf() as s:
            row = s.scalars(
                select(models.Airport).where(models.Airport.iata == code.upper())
            ).first()
            return _row_to_airport(row) if row is not None else None
