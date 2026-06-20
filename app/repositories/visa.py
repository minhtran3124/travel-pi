"""Data-access for visa / entry requirements — SQLAlchemy ORM reads.

``get`` returns the ``EntryRequirements`` Pydantic schema (the visa table's
columns are a superset: it also stores the ``country`` PK, which the schema
does not carry), so the repo constructs the schema explicitly. Returning
``None`` for an unknown country mirrors ``COUNTRY_VISA.get(...)`` — the service
keeps deciding what an absent record means.
"""

from sqlalchemy import select

from app.db import models
from app.repositories.base import Repo
from app.schemas.visa import EntryRequirements


class VisaRepository(Repo):
    """Read-only store of visa rows behind a ``session_factory``."""

    def countries(self) -> list[str]:
        """Return every country that has a visa record, sorted.

        Mirrors ``sorted(COUNTRY_VISA)`` — the dashboard's visa picker list.
        """
        with self._session() as s:
            return sorted(s.scalars(select(models.Visa.country)).all())

    def get(self, country: str) -> EntryRequirements | None:
        """Return entry requirements for a resolved ``country``, or ``None``."""
        with self._session() as s:
            row = s.scalars(
                select(models.Visa).where(models.Visa.country == country)
            ).first()
            if row is None:
                return None
            return EntryRequirements(
                visa_free_days=row.visa_free_days,
                visa_on_arrival=row.visa_on_arrival,
                e_visa=row.e_visa,
                passport_validity_months=row.passport_validity_months,
                summary=row.summary,
            )
