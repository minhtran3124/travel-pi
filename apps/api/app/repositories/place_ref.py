"""Data-access for places. ``search`` does exact/range SQL filters only — fuzzy city resolution and result ordering stay in place_service."""

from sqlalchemy import func, select

from app.db import models
from app.repositories.base import Repo
from app.schemas.place import Place


def _row_to_place(row: models.Place) -> Place:
    return Place.model_validate(row, from_attributes=True)


class PlaceRepository(Repo):
    """Read-only store of place rows behind a ``session_factory``."""

    def all(self) -> list[Place]:
        """Return every seeded place in stable ``position`` (seed) order — never relies on insertion-order coincidence."""
        with self._session() as s:
            rows = s.scalars(select(models.Place).order_by(models.Place.position)).all()
            return [_row_to_place(r) for r in rows]

    def get(self, place_id: str) -> Place | None:
        with self._session() as s:
            row = s.get(models.Place, place_id)
            return _row_to_place(row) if row is not None else None

    def by_short_code(self, code: str) -> Place | None:
        """Return the place whose computed ``short_code`` matches (case-insensitive); short codes derive from ``id``, not a column, so this scans and compares."""
        needle = code.strip().upper()
        with self._session() as s:
            for row in s.scalars(select(models.Place)):
                place = _row_to_place(row)
                if place.short_code.upper() == needle:
                    return place
        return None

    def known_ids(self, ids: list[str]) -> set[str]:
        """Return the subset of ``ids`` that exist as place rows; empty input skips the query."""
        if not ids:
            return set()
        with self._session() as s:
            return set(s.scalars(select(models.Place.id).where(models.Place.id.in_(ids))).all())

    def distinct_cities(self) -> list[str]:
        """Return the distinct city names that have places, sorted (the fuzzy-resolution target)."""
        with self._session() as s:
            return sorted(set(s.scalars(select(models.Place.city)).all()))

    def distinct_categories(self) -> list[str]:
        """Return the distinct place categories, sorted."""
        with self._session() as s:
            return sorted(set(s.scalars(select(models.Place.category)).all()))

    def count_by_city(self) -> dict[str, int]:
        """Return ``{city: place_count}`` — feeds the startup coverage check."""
        stmt = select(models.Place.city, func.count()).group_by(models.Place.city)
        with self._session() as s:
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
        """Return places matching the exact/range filters (no fuzzy, no sort); ``city`` is an already-resolved exact name, ``category`` matched case-insensitively."""
        stmt = select(models.Place).order_by(models.Place.position)
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

        with self._session() as s:
            return [_row_to_place(r) for r in s.scalars(stmt).all()]
