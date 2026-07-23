"""Data-access for hotels — SQLAlchemy ORM reads, no business logic.

Filename is ``hotel_ref`` (not ``hotel``) to avoid clashing with any future
bookable-hotel crud. Returns the ``Hotel`` Pydantic schema with the ``id``
preserved verbatim, so ``hotel_service.available_rooms`` (which MD5-hashes
``hotel.id``) stays byte-identical.

City / star / price filters run as SQL; the ``amenities`` all-contains
predicate is refined in Python over the fetched rows (portable across SQLite
and Postgres — no JSON-containment operator needed). Fuzzy city resolution
stays in the service (Chunk E); ``search`` takes an already-resolved exact city.
"""

from sqlalchemy import func, select

from app.db import models
from app.repositories.base import Repo
from app.schemas.hotel import Hotel


def _row_to_hotel(row: models.Hotel) -> Hotel:
    return Hotel.model_validate(row, from_attributes=True)


class HotelRepository(Repo):
    """Read-only store of hotel rows behind a ``session_factory``."""

    def all(self) -> list[Hotel]:
        """Return every seeded hotel in stable ``position`` (seed) order.

        Explicit ``ORDER BY position`` so ``/hotels`` offset/limit pagination
        is stable across engines (Postgres makes no row-order guarantee).

        :return: All hotels, ordered by ``position``.
        """
        with self._session() as s:
            stmt = select(models.Hotel).order_by(models.Hotel.position)
            return [_row_to_hotel(r) for r in s.scalars(stmt).all()]

    def get(self, hotel_id: str) -> Hotel | None:
        """Return the hotel by raw UUID ``id``, or ``None``.

        :param hotel_id: The hotel's raw UUID.
        :return: The matching hotel, or ``None`` if unknown.
        """
        with self._session() as s:
            row = s.get(models.Hotel, hotel_id)
            return _row_to_hotel(row) if row is not None else None

    def by_short_code(self, code: str) -> Hotel | None:
        """Return the hotel whose computed ``short_code`` matches ``code``.

        Short codes are hash-derived from ``id`` (a Pydantic computed field, not
        a column), so this builds the models and compares — case-insensitive,
        matching ``hotel_service.get_hotel``'s ``HTL-...`` branch.

        :param code: The short code to match, compared case-insensitively.
        :return: The matching hotel, or ``None`` if no hotel's short code matches.
        """
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
        """Return hotels matching the (already-resolved exact) ``city`` + filters.

        City / stars / price are SQL predicates; ``amenities`` is an
        all-contains refinement done in Python over the fetched rows
        (case-insensitive), mirroring ``hotel_service.search_hotels``.

        :param city: Exact city name to filter by, or ``None`` for all cities.
        :param min_stars: Minimum ``star_rating`` (inclusive), or ``None``.
        :param max_price: Maximum ``price_per_night`` (inclusive), or ``None``.
        :param amenities: Amenities that must all be present (case-insensitive),
            or ``None``/empty to skip the filter.
        :return: Hotels matching every supplied filter, in ``position`` order.
        """
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
        """Return ``{city: hotel_count}`` — feeds ``City.hotel_count``.

        :return: A mapping of city name to hotel count.
        """
        stmt = select(models.Hotel.city, func.count()).group_by(models.Hotel.city)
        with self._session() as s:
            return dict(s.execute(stmt).all())

    def distinct_cities(self) -> list[str]:
        """Return the distinct city names that have hotels, sorted.

        The fuzzy-resolution target for ``hotel_service.resolve_city``.

        :return: Sorted distinct city names that have at least one hotel.
        """
        with self._session() as s:
            return sorted(set(s.scalars(select(models.Hotel.city)).all()))

    def distinct_amenities(self) -> list[str]:
        """Return the distinct amenity strings across all seeded hotels, sorted.

        ``amenities`` is a JSON list column (no cross-engine SQL distinct), so
        this flattens it in Python. The fuzzy-resolution target for
        ``hotel_service.resolve_amenities``.

        :return: Sorted distinct amenity strings.
        """
        with self._session() as s:
            rows = s.scalars(select(models.Hotel.amenities)).all()
        return sorted({a for row in rows for a in row})
