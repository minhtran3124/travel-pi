"""Data-access for places — SQLAlchemy ORM reads, no business logic.

Filename is ``place_ref`` for symmetry with ``hotel_ref``. Returns the
``Place`` Pydantic schema (``model_validate(from_attributes=True)`` is safe —
every required field is a column, and the computed ``short_code`` derives from
``id`` so it stays identical).

``search`` does exact / range SQL filters ONLY — no fuzzy resolution and no
sort. Fuzzy city resolution and the result ordering stay in ``place_service``
(Chunk E); the repo's ``search`` takes an already-resolved exact city.
"""

from sqlalchemy import func, select

from app.db import models
from app.schemas.place import Place


def _row_to_place(row: models.Place) -> Place:
    return Place.model_validate(row, from_attributes=True)


class PlaceRepository:
    """Read-only store of place rows behind a ``session_factory``."""

    def __init__(self, session_factory) -> None:
        self._sf = session_factory

    def all(self) -> list[Place]:
        """Return every seeded place in stable id order.

        Explicit ``ORDER BY id`` (the seed insertion order == id order) so the
        output never relies on insertion-order coincidence. Also fixes the
        ordering of ``nearby_places``, which sources its candidates from here.
        """
        with self._sf() as s:
            rows = s.scalars(select(models.Place).order_by(models.Place.id)).all()
            return [_row_to_place(r) for r in rows]

    def get(self, place_id: str) -> Place | None:
        """Return the place by raw UUID ``id``, or ``None``."""
        with self._sf() as s:
            row = s.get(models.Place, place_id)
            return _row_to_place(row) if row is not None else None

    def by_short_code(self, code: str) -> Place | None:
        """Return the place whose computed ``short_code`` matches ``code``.

        Short codes derive from ``id`` (a computed field, not a column), so this
        builds the models and compares — case-insensitive, matching
        ``place_service.get_place``'s ``PLC-...`` branch.
        """
        needle = code.strip().upper()
        with self._sf() as s:
            for row in s.scalars(select(models.Place)):
                place = _row_to_place(row)
                if place.short_code.upper() == needle:
                    return place
        return None

    def distinct_cities(self) -> list[str]:
        """Return the distinct city names that have places, sorted.

        The fuzzy-resolution target for ``place_service.resolve_city`` — mirrors
        the module-level ``CITIES`` list.
        """
        with self._sf() as s:
            return sorted(set(s.scalars(select(models.Place.city)).all()))

    def distinct_categories(self) -> list[str]:
        """Return the distinct place categories, sorted — mirrors ``CATEGORIES``."""
        with self._sf() as s:
            return sorted(set(s.scalars(select(models.Place.category)).all()))

    def count_by_city(self) -> dict[str, int]:
        """Return ``{city: place_count}`` — feeds the startup coverage check."""
        stmt = select(models.Place.city, func.count()).group_by(models.Place.city)
        with self._sf() as s:
            return dict(s.execute(stmt).all())

    def search(
        self,
        *,
        city: str | None = None,
        category: str | None = None,
        min_rating: float | None = None,
        price_level: int | None = None,
        price_level_max: int | None = None,
        recommended: bool | None = None,
    ) -> list[Place]:
        """Return places matching the exact/range filters (no fuzzy, no sort).

        ``city`` is an already-resolved exact name; ``category`` is matched
        case-insensitively (lower-cased) as in ``place_service.search_places``.
        """
        stmt = select(models.Place)
        if city is not None:
            stmt = stmt.where(models.Place.city == city)
        if category is not None:
            stmt = stmt.where(models.Place.category == category.strip().lower())
        if min_rating is not None:
            stmt = stmt.where(models.Place.rating >= min_rating)
        if price_level is not None:
            stmt = stmt.where(models.Place.price_level == price_level)
        if price_level_max is not None:
            stmt = stmt.where(models.Place.price_level <= price_level_max)
        if recommended:
            stmt = stmt.where(models.Place.is_recommended.is_(True))

        with self._sf() as s:
            return [_row_to_place(r) for r in s.scalars(stmt).all()]
