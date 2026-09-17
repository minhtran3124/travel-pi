"""Visa / entry-requirement lookup over DB-backed seed data — pure, synchronous, fuzzy free-text resolution; an unrecognised location yields ``found: False``, never a 404."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.text import best_match
from app.db.session import get_session
from app.repositories.city import CityRepository
from app.repositories.country import CountryRepository
from app.repositories.visa import VisaRepository
from app.schemas.visa import VisaResponse

DISCLAIMER = (
    "General guidance only and dependent on your nationality — always confirm "
    "current requirements with the destination's official immigration authority "
    "or embassy before you travel."
)


class VisaService:
    """Visa / entry-requirement lookup over DB-backed seed data."""

    def __init__(self, session: Session) -> None:
        self._visa_repo = VisaRepository(session)
        self._city_repo = CityRepository(session)
        self._country_repo = CountryRepository(session)

    def get_visa(
        self,
        *,
        city: str | None = None,
        country: str | None = None,
    ) -> VisaResponse:
        """Return entry-requirement guidance for a destination (city takes precedence and resolves its own country; both matched fuzzily)."""
        resolved_country: str | None = None
        resolved_city: str | None = None

        if city:
            name = best_match(city, self._city_repo.distinct_names(), [lambda c: c])
            if name is not None:
                record = self._city_repo.get(name)
                if record is not None:
                    resolved_city = record.name
                    resolved_country = record.country
        elif country:
            resolved_country = best_match(
                country, self._country_repo.distinct_names(), [lambda c: c]
            )

        entry = self._visa_repo.get(resolved_country) if resolved_country else None

        return VisaResponse(
            city=resolved_city,
            country=resolved_country or (country or city or ""),
            found=entry is not None,
            entry=entry,
            disclaimer=DISCLAIMER,
        )


def get_visa_service(
    session: Annotated[Session, Depends(get_session)],
) -> VisaService:
    """FastAPI dependency: a visa service bound to the request session."""
    return VisaService(session)
