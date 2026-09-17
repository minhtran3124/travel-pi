"""Data-access for local tips, ordered by ``position`` to reproduce positional ids and seed order. The presentation ``location`` field is added by tip_service, not here."""

from sqlalchemy import select

from app.db import models
from app.repositories.base import Repo
from app.schemas.tip import Tip


def _row_to_tip(row: models.Tip) -> Tip:
    return Tip(
        id=row.id,
        scope=row.scope,
        category=row.category,
        title=row.title,
        content=row.content,
        is_essential=row.is_essential,
    )


class TipRepository(Repo):
    """Read-only store of tip rows behind a ``session_factory``."""

    def for_location(self, scope: str, key: str) -> list[Tip]:
        """Return tips for one ``(scope, key)``, ordered by ``position``; ``[]`` when none."""
        stmt = (
            select(models.Tip)
            .where(models.Tip.scope == scope, models.Tip.key == key)
            .order_by(models.Tip.position)
        )
        with self._session() as s:
            return [_row_to_tip(r) for r in s.scalars(stmt).all()]

    def all_tips(self) -> list[Tip]:
        """Return every tip ordered by ``(scope, key, position)`` — country scope sorts before city."""
        stmt = select(models.Tip).order_by(
            models.Tip.scope, models.Tip.key, models.Tip.position
        )
        with self._session() as s:
            return [_row_to_tip(r) for r in s.scalars(stmt).all()]

    def country_summary(self, country: str) -> str:
        """Return the one-line summary for ``country``, or ``""`` if none."""
        with self._session() as s:
            row = s.scalars(
                select(models.CountrySummary).where(
                    models.CountrySummary.country == country
                )
            ).first()
            return row.summary if row is not None else ""
