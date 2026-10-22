"""Data-access for visa / entry requirements. The table's columns are a superset of ``EntryRequirements``, so the repo constructs the schema explicitly; an unknown country returns ``None`` and the service decides what that means."""

from sqlalchemy import select

from app.db import models
from app.repositories.base import Repo
from app.schemas.visa import EntryRequirements


class VisaRepository(Repo):
    """Read-only store of visa rows behind a ``session_factory``."""

    def countries(self) -> list[str]:
        """Return every country that has a visa record, sorted."""
        with self._session() as s:
            return sorted(s.scalars(select(models.Visa.country)).all())

    def get(self, country: str) -> EntryRequirements | None:
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
