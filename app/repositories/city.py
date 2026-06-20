"""Data-access for cities — SQLAlchemy ORM reads, no business logic.

The ``City`` schema REQUIRES ``hotel_count``, which is NOT an ORM column — it is
computed from a hotel-count-by-city query. The repo therefore constructs
``City`` EXPLICITLY (never ``model_validate``) so it can inject ``hotel_count``.
It reuses ``HotelRepository.count_by_city()`` for that count, so the number
always matches the hotels table.

Fuzzy name resolution stays in the consumer (Chunk E); ``get`` is an exact
(case-insensitive) name lookup, mirroring ``GET /cities/{city_name}``.
"""

from sqlalchemy import select

from app.db import models
from app.repositories.base import Repo
from app.repositories.hotel_ref import HotelRepository
from app.schemas.city import City


class CityRepository(Repo):
    """Read-only store of city rows behind a ``session_factory``."""

    def __init__(self, session_or_factory) -> None:
        super().__init__(session_or_factory)
        self._hotels = HotelRepository(session_or_factory)

    def distinct_names(self) -> list[str]:
        """Return every city name (the fuzzy-resolution target)."""
        with self._session() as s:
            return list(s.scalars(select(models.City.name)).all())

    def _build(self, row: models.City, hotel_count: int) -> City:
        return City(
            name=row.name,
            country=row.country,
            airport_codes=row.airport_codes,
            hotel_count=hotel_count,
            latitude=row.latitude,
            longitude=row.longitude,
        )

    def get(self, name: str) -> City | None:
        """Return a single city by exact (case-insensitive) ``name``, or ``None``.

        Matches ``GET /cities/{city_name}`` — an exact-name lookup, not fuzzy.
        """
        target = name.strip().lower()
        counts = self._hotels.count_by_city()
        with self._session() as s:
            for row in s.scalars(select(models.City)):
                if row.name.lower() == target:
                    return self._build(row, counts.get(row.name, 0))
        return None

    def list_with_counts(self) -> list[City]:
        """Return every city as a ``City`` schema, with ``hotel_count`` filled.

        Reproduces the cities router's ``_ALL_CITIES`` build (in seed order).
        """
        counts = self._hotels.count_by_city()
        with self._session() as s:
            rows = s.scalars(select(models.City).order_by(models.City.id)).all()
            return [self._build(r, counts.get(r.name, 0)) for r in rows]
