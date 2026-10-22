"""Data-access for countries. Exposes both shapes consumed today: full ``{name, code, region, lat, long}`` dicts and the set of distinct country names (the fuzzy-resolution target)."""

# Defer annotations: the ``list`` method would otherwise shadow the ``list[...]`` builtin in later annotations under eager-annotation Python.
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
        """Return every country as a ``{name, code, region, lat, long}`` dict, ordered by curated ``position`` seed order."""
        with self._session() as s:
            rows = s.scalars(
                select(models.Country).order_by(models.Country.position)
            ).all()
            return [_row_to_dict(r) for r in rows]

    def get(self, code: str) -> dict | None:
        with self._session() as s:
            row = s.scalars(
                select(models.Country).where(models.Country.code == code)
            ).first()
            return _row_to_dict(row) if row is not None else None

    def get_by_name(self, name: str) -> dict | None:
        with self._session() as s:
            row = s.scalars(
                select(models.Country).where(models.Country.name == name)
            ).first()
            return _row_to_dict(row) if row is not None else None

    def distinct_names(self) -> list[str]:
        """Return the distinct country names on city records, sorted (the fuzzy-resolution target; countries with no cities are excluded)."""
        with self._session() as s:
            names = s.scalars(select(models.City.country).distinct()).all()
            return sorted(set(names))
