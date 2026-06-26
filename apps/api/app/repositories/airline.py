"""Data-access for airlines — SQLAlchemy ORM reads, no business logic.

``list()`` returns ``{code, name}`` dicts in seed order (``ORDER BY position``)
because ``flight_service.generate_flights`` does ``rng.choice(AIRLINES)`` over a
*seeded* RNG: the order is load-bearing for flight determinism.
"""

from sqlalchemy import select

from app.db import models
from app.repositories.base import Repo

# Fallback colour for any airline code without an explicit brand colour.
# Presentation only (moved here from app/data/airlines.py so the colour lookup
# has a single home now that airlines are DB-backed).
AIRLINE_COLOR_DEFAULT = "#444b55"


class AirlineRepository(Repo):
    """Read-only store of airline rows behind a ``session_factory``."""

    def list(self) -> list[dict]:
        """Return airlines as ``{code, name}`` dicts in seed order.

        Determinism-critical: ``ORDER BY position`` reproduces ``AIRLINES``
        order so seeded ``rng.choice`` selections are unchanged.
        """
        with self._session() as s:
            rows = s.scalars(
                select(models.Airline).order_by(models.Airline.position)
            ).all()
            return [{"code": r.code, "name": r.name} for r in rows]

    def color(self, code: str) -> str | None:
        """Return the brand colour for an airline ``code``, or ``None``."""
        with self._session() as s:
            row = s.scalars(
                select(models.Airline).where(models.Airline.code == code)
            ).first()
            return row.color if row is not None else None

    def colors(self) -> dict[str, str]:
        """Return ``{code: color}`` for airlines with a brand colour.

        Mirrors the ``AIRLINE_COLORS`` dict the dashboard templates do
        ``.get(code, default)`` against.
        """
        with self._session() as s:
            rows = s.scalars(select(models.Airline)).all()
            return {r.code: r.color for r in rows if r.color is not None}
