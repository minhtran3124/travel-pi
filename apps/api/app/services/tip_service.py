"""Local-tips lookup over DB-backed seed data — country tips inherited by every city, city tips merged on top; unknown locations return an empty list, never a 404."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.text import best_match
from app.db.session import get_session
from app.repositories.city import CityRepository
from app.repositories.country import CountryRepository
from app.repositories.tip import TipRepository
from app.schemas.tip import Tip, TipsResponse

VALID_CATEGORIES = {
    "transport",
    "money",
    "safety",
    "culture",
    "food",
    "connectivity",
    "health",
    "etiquette",
    "best_time",
    "language",
}


class TipService:
    """Local-tips lookup over the DB-backed seed data."""

    def __init__(self, session: Session) -> None:
        self._tip_repo = TipRepository(session)
        self._city_repo = CityRepository(session)
        self._country_repo = CountryRepository(session)

    def _resolve_tips(
        self, scope: str, key: str, *, location_label: str | None = None
    ) -> list[Tip]:
        """Fetch tips for one ``(scope, key)`` and attach the optional presentation ``location`` label."""
        tips = self._tip_repo.for_location(scope, key)
        if location_label is not None:
            for t in tips:
                t.location = location_label
        return tips

    def get_tips(
        self,
        *,
        city: str | None = None,
        country: str | None = None,
        category: str | None = None,
        essential_only: bool = False,
    ) -> TipsResponse:
        """Return merged country + city tips for a destination (city takes precedence and resolves its own country; both matched fuzzily)."""
        resolved_country: str | None = None
        resolved_city: str | None = None
        tips: list[Tip] = []

        all_cities = self._city_repo.list_with_counts()

        if city:
            record = best_match(city, all_cities, [lambda c: c.name])
            if record is not None:
                resolved_city = record.name
                resolved_country = record.country
                tips += self._resolve_tips("city", resolved_city)
        elif country:
            countries = sorted({c.country for c in all_cities})
            resolved_country = best_match(country, countries, [lambda c: c])

        if resolved_country is not None:
            tips += self._resolve_tips("country", resolved_country)

        if category:
            cat = category.strip().lower()
            tips = [t for t in tips if t.category == cat]
        if essential_only:
            tips = [t for t in tips if t.is_essential]

        summary = (
            self._tip_repo.country_summary(resolved_country)
            if resolved_country is not None
            else ""
        )

        return TipsResponse(
            city=resolved_city,
            country=resolved_country or (country or city or ""),
            count=len(tips),
            summary=summary,
            tips=tips,
        )

    def get_all_tips(
        self,
        *,
        category: str | None = None,
        essential_only: bool = False,
    ) -> TipsResponse:
        """Return every tip across every country and city, each carrying its ``location`` label (countries first alphabetically, then cities in seed order)."""
        tips: list[Tip] = []

        all_cities = self._city_repo.list_with_counts()
        all_countries = sorted({c.country for c in all_cities})

        for country_name in all_countries:
            tips += self._resolve_tips(
                "country", country_name, location_label=country_name
            )

        for city in all_cities:
            city_tips = self._resolve_tips(
                "city",
                city.name,
                location_label=f"{city.name} · {city.country}",
            )
            tips += city_tips

        if category:
            cat = category.strip().lower()
            tips = [t for t in tips if t.category == cat]
        if essential_only:
            tips = [t for t in tips if t.is_essential]

        return TipsResponse(
            city=None,
            country="",  # No single destination — empty so the template hides the summary header.
            count=len(tips),
            summary="",
            tips=tips,
        )


def get_tip_service(
    session: Annotated[Session, Depends(get_session)],
) -> TipService:
    """FastAPI dependency: a tip service bound to the request session."""
    return TipService(session)
