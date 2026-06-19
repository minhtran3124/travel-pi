"""Data-access for local tips — SQLAlchemy ORM reads, no business logic.

Tips are returned as the ``Tip`` Pydantic schema ORDERED BY ``position`` so the
positional ids (``tip_{scope}_{prefix}_{NN}``) and seed order are reproduced.
The repo does NOT set the presentation ``location`` field — ``tip_service`` adds
that (it is only populated for the dashboard's mixed-destination view).

The schema field ``scope`` maps from the column ``scope``; the schema has no
``key``/``position`` field, so the repo constructs ``Tip`` explicitly.
"""

from sqlalchemy import select

from app.db import models
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


class TipRepository:
    """Read-only store of tip rows behind a ``session_factory``."""

    def __init__(self, session_factory) -> None:
        self._sf = session_factory

    def for_location(self, scope: str, key: str) -> list[Tip]:
        """Return tips for one ``(scope, key)``, ordered by ``position``.

        ``scope`` is ``"country"`` or ``"city"``; ``key`` is the resolved
        country or city name. Empty list when none — never raises.
        """
        stmt = (
            select(models.Tip)
            .where(models.Tip.scope == scope, models.Tip.key == key)
            .order_by(models.Tip.position)
        )
        with self._sf() as s:
            return [_row_to_tip(r) for r in s.scalars(stmt).all()]

    def all_tips(self) -> list[Tip]:
        """Return every tip, country scope first then city, each in seed order.

        Mirrors ``tip_service.get_all_tips``'s merge (country tips, then city
        tips), ordered by ``(scope, key, position)`` — country sorts before city
        alphabetically, matching the country-first iteration there. The
        presentation ``location`` label is added by the service, not here.
        """
        stmt = select(models.Tip).order_by(
            models.Tip.scope, models.Tip.key, models.Tip.position
        )
        with self._sf() as s:
            return [_row_to_tip(r) for r in s.scalars(stmt).all()]

    def country_summary(self, country: str) -> str:
        """Return the one-line summary for ``country``, or ``""`` if none.

        Mirrors ``COUNTRY_SUMMARIES.get(country, "")``.
        """
        with self._sf() as s:
            row = s.get(models.CountrySummary, country)
            return row.summary if row is not None else ""
