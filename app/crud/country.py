"""Data-access for countries — SQLAlchemy ORM reads, no business logic.

``app/data/countries.py`` is the source of truth and is consumed today as a
list of ``{name, code, region, latitude, longitude}`` dicts (the dashboard
builds country tiles from it) and as a set of distinct country *names* (the
fuzzy-resolution target in cities/tips/visa). The repo exposes both shapes.
"""

from sqlalchemy import select

from app.db import models


def _row_to_dict(row: models.Country) -> dict:
    return {
        "name": row.name,
        "code": row.code,
        "region": row.region,
        "latitude": row.latitude,
        "longitude": row.longitude,
    }


class CountryRepository:
    """Read-only store of country rows behind a ``session_factory``."""

    def __init__(self, session_factory) -> None:
        self._sf = session_factory

    def list(self) -> list[dict]:
        """Return every country as a ``{name, code, region, lat, long}`` dict.

        Ordering is *not* guaranteed by the DB (``Country`` has no position
        column). Consumers that need the region-ordered list from
        ``countries.py`` must sort/order it themselves — see the Chunk E
        notes for the dashboard.
        """
        with self._sf() as s:
            rows = s.scalars(select(models.Country)).all()
            return [_row_to_dict(r) for r in rows]

    def get(self, code: str) -> dict | None:
        """Return the country for an ISO 3166-1 alpha-2 ``code``, or ``None``."""
        with self._sf() as s:
            row = s.get(models.Country, code)
            return _row_to_dict(row) if row is not None else None

    def get_by_name(self, name: str) -> dict | None:
        """Return the country with display ``name`` (exact), or ``None``."""
        with self._sf() as s:
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
        with self._sf() as s:
            names = s.scalars(select(models.City.country).distinct()).all()
            return sorted(set(names))
