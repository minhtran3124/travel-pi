"""Data-access for countries — SQLAlchemy ORM reads, no business logic.

``app/data/countries.py`` is the source of truth and is consumed today as a
list of ``{name, code, region, latitude, longitude}`` dicts (the dashboard
builds country tiles from it) and as a set of distinct country *names* (the
fuzzy-resolution target in cities/tips/visa). The repo exposes both shapes.
"""

# Defer annotation evaluation: this class defines a ``list`` method, which would
# otherwise shadow the ``list[...]`` builtin in later method annotations under
# eager-annotation Python (3.12 in the test container; 3.14 evaluates lazily).
from __future__ import annotations

from sqlalchemy import select

from app.db import models
from app.repositories.base import Repo


def _row_to_dict(row: models.Country) -> dict:
    return {
        "name": row.name,
        "code": row.code,
        "region": row.region,
        "latitude": row.latitude,
        "longitude": row.longitude,
    }


class CountryRepository(Repo):
    """Read-only store of country rows behind a ``session_factory``."""

    def list(self) -> list[dict]:
        """Return every country as a ``{name, code, region, lat, long}`` dict.

        Ordered by ``position`` (the curated ``COUNTRIES`` seed order), so the
        dashboard region tiles keep their hand-curated ordering — symmetric
        with how ``AirlineRepository.list`` preserves airline order.
        """
        with self._session() as s:
            rows = s.scalars(
                select(models.Country).order_by(models.Country.position)
            ).all()
            return [_row_to_dict(r) for r in rows]

    def get(self, code: str) -> dict | None:
        """Return the country for an ISO 3166-1 alpha-2 ``code``, or ``None``."""
        with self._session() as s:
            row = s.scalars(
                select(models.Country).where(models.Country.code == code)
            ).first()
            return _row_to_dict(row) if row is not None else None

    def get_by_name(self, name: str) -> dict | None:
        """Return the country with display ``name`` (exact), or ``None``."""
        with self._session() as s:
            row = s.scalars(
                select(models.Country).where(models.Country.name == name)
            ).first()
            return _row_to_dict(row) if row is not None else None

    def distinct_names(self) -> list[str]:
        """Return the distinct country names that appear on city records, sorted.

        Mirrors ``sorted({c["country"] for c in CITIES})`` — the fuzzy-resolution
        target used by cities/tips/visa. Derived from the ``cities`` table so it
        matches today's behaviour exactly (countries with no cities are excluded).
        """
        with self._session() as s:
            names = s.scalars(select(models.City.country).distinct()).all()
            return sorted(set(names))
