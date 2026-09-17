"""Data-access for hotels. City/star/price filters run as SQL; the ``amenities`` all-contains predicate is refined in Python (portable across engines). Fuzzy city resolution stays in the service."""

from sqlalchemy import func, select

from app.db import models
from app.repositories.base import Repo
from app.schemas.hotel import Hotel


def _row_to_hotel(row: models.Hotel) -> Hotel:
    return Hotel.model_validate(row, from_attributes=True)


class HotelRepository(Repo):
    """Read-only store of hotel rows behind a ``session_factory``."""

    def all(self) -> list[Hotel]:
        """Return every seeded hotel in stable ``position`` (seed) order — pagination stays stable across engines."""
        with self._session() as s:
            stmt = select(models.Hotel).order_by(models.Hotel.position)
            return [_row_to_hotel(r) for r in s.scalars(stmt).all()]

    def get(self, hotel_id: str) -> Hotel | None:
        with self._session() as s:
            row = s.get(models.Hotel, hotel_id)
            return _row_to_hotel(row) if row is not None else None

    def by_short_code(self, code: str) -> Hotel | None:
        """Return the hotel whose computed ``short_code`` matches (case-insensitive); short codes are hash-derived from ``id``, not a column, so this scans and compares."""
        needle = code.strip().upper()
        with self._session() as s:
            for row in s.scalars(select(models.Hotel)):
                hotel = _row_to_hotel(row)
                if hotel.short_code.upper() == needle:
                    return hotel
        return None

    def search(
        self,
        *,
        city: str | None = None,
        min_stars: int | None = None,
        max_price: float | None = None,
        amenities: list[str] | None = None,
    ) -> list[Hotel]:
        """Return hotels matching the (already-resolved exact) ``city`` + filters; ``amenities`` is an all-contains refinement done in Python (case-insensitive)."""
        stmt = select(models.Hotel).order_by(models.Hotel.position)
        if city is not None:
            stmt = stmt.where(models.Hotel.city == city)
        if min_stars is not None:
            stmt = stmt.where(models.Hotel.star_rating >= min_stars)
        if max_price is not None:
            stmt = stmt.where(models.Hotel.price_per_night <= max_price)

        with self._session() as s:
            hotels = [_row_to_hotel(r) for r in s.scalars(stmt).all()]

        if amenities:
            required = [a.strip().lower() for a in amenities]
            hotels = [
                h
                for h in hotels
                if all(req in [a.lower() for a in h.amenities] for req in required)
            ]
        return hotels

    def count_by_city(self) -> dict[str, int]:
        """Return ``{city: hotel_count}`` — feeds ``City.hotel_count``."""
        stmt = select(models.Hotel.city, func.count()).group_by(models.Hotel.city)
        with self._session() as s:
            return dict(s.execute(stmt).all())

    def distinct_cities(self) -> list[str]:
        """Return the distinct city names that have hotels, sorted (the fuzzy-resolution target)."""
        with self._session() as s:
            return sorted(set(s.scalars(select(models.Hotel.city)).all()))

    def distinct_amenities(self) -> list[str]:
        """Return the distinct amenity strings across all hotels, sorted; ``amenities`` is a JSON list column, so this flattens in Python."""
        with self._session() as s:
            rows = s.scalars(select(models.Hotel.amenities)).all()
        return sorted({a for row in rows for a in row})
