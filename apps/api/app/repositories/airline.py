"""Data-access for airlines. ``list()`` returns dicts in seed order because flight_service does seeded ``rng.choice`` over them — the order is load-bearing for flight determinism."""

from sqlalchemy import select

from app.db import models
from app.repositories.base import Repo

# Fallback colour for an airline code without an explicit brand colour (presentation only).
AIRLINE_COLOR_DEFAULT = "#444b55"


class AirlineRepository(Repo):
    """Read-only store of airline rows behind a ``session_factory``."""

    def list(self) -> list[dict]:
        """Return airlines as ``{code, name}`` dicts in seed order (determinism-critical for seeded ``rng.choice``)."""
        with self._session() as s:
            rows = s.scalars(
                select(models.Airline).order_by(models.Airline.position)
            ).all()
            return [{"code": r.code, "name": r.name} for r in rows]

    def color(self, code: str) -> str | None:
        with self._session() as s:
            row = s.scalars(
                select(models.Airline).where(models.Airline.code == code)
            ).first()
            return row.color if row is not None else None

    def colors(self) -> dict[str, str]:
        """Return ``{code: color}`` for airlines with a brand colour."""
        with self._session() as s:
            rows = s.scalars(select(models.Airline)).all()
            return {r.code: r.color for r in rows if r.color is not None}
