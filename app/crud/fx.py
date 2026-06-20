"""Data-access for FX rates / currencies — SQLAlchemy ORM reads.

Currency codes are exact identifiers (like IATA codes): exact-code lookups
return ``None`` for an unknown code and the *service* keeps raising
``NotFoundError`` (the 404 policy stays in ``currency_service``). ``rate`` and
``name`` come from the ``fx_rates`` table; ``country_currency`` from the
``country_currency`` table; ``last_updated`` from the singleton ``fx_meta`` row.
"""

from sqlalchemy import select

from app.crud.base import Repo
from app.db import models


class FxRepository(Repo):
    """Read-only store of FX rows behind a ``session_factory``."""


    def rate(self, code: str) -> float | None:
        """Return the units-per-USD rate for ``code`` (exact), or ``None``."""
        with self._session() as s:
            row = s.scalars(
                select(models.FxRate).where(models.FxRate.code == code)
            ).first()
            return row.rate if row is not None else None

    def name(self, code: str) -> str | None:
        """Return the human currency name for ``code`` (exact), or ``None``."""
        with self._session() as s:
            row = s.scalars(
                select(models.FxRate).where(models.FxRate.code == code)
            ).first()
            return row.name if row is not None else None

    def country_currency(self, country: str) -> str | None:
        """Return the ISO 4217 code for a resolved ``country``, or ``None``."""
        with self._session() as s:
            row = s.scalars(
                select(models.CountryCurrency).where(
                    models.CountryCurrency.country == country
                )
            ).first()
            return row.code if row is not None else None

    def last_updated(self) -> str | None:
        """Return the snapshot date for the FX table (singleton row)."""
        with self._session() as s:
            row = s.scalars(select(models.FxMeta)).first()
            return row.last_updated if row is not None else None

    def valid_codes(self) -> list[str]:
        """Return every supported currency code, sorted — mirrors ``sorted(RATES)``."""
        with self._session() as s:
            return sorted(s.scalars(select(models.FxRate.code)).all())

    def country_names(self) -> list[str]:
        """Return the country names with a known currency, sorted.

        Mirrors ``sorted(COUNTRY_CURRENCY)`` — the fuzzy-resolution target for
        the ``country`` param in ``currency_service``.
        """
        with self._session() as s:
            return sorted(s.scalars(select(models.CountryCurrency.country)).all())
