"""Aggregates weather, places, tips, and hotel stats for a city overview."""

import logging
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.text import best_match
from app.db.session import get_session
from app.exceptions import NotFoundError
from app.repositories.city import CityRepository
from app.schemas.destination import (
    DestinationOverviewResponse,
    HotelSummary,
    PriceRange,
    StarRange,
)
from app.services import weather_service
from app.services.hotel_service import HotelService
from app.services.place_service import PlaceService
from app.services.tip_service import TipService

logger = logging.getLogger(__name__)

_ATTRIBUTION = "Weather data by Open-Meteo.com (CC BY 4.0)"


class DestinationService:
    """Aggregates a city overview from city data + place/tip/hotel/weather."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._city = CityRepository(session)

    async def get_overview(
        self,
        city: str,
        *,
        include: set[str],
        place_limit: int,
        tip_limit: int,
    ) -> DestinationOverviewResponse:
        """Return an aggregated destination overview for *city*."""
        matched = best_match(city, self._city.distinct_names(), [lambda c: c])
        record = self._city.get(matched) if matched is not None else None
        if record is None:
            raise NotFoundError(
                f"City '{city}' not found",
                hint="Call GET /cities to list available cities.",
            )
        name: str = record.name
        country: str = record.country
        latitude: float = record.latitude
        longitude: float = record.longitude

        places = []
        if "places" in include:
            results = PlaceService(self._session).search_places(
                city=name, sort="rating_desc"
            )
            # Recommended first, then by rating (search already sorted, so ties keep order).
            results.sort(key=lambda p: (not p.is_recommended, -p.rating))
            places = results[:place_limit]

        tips = []
        if "tips" in include:
            tips_response = TipService(self._session).get_tips(
                city=name, essential_only=True
            )
            tips = tips_response.tips[:tip_limit]

        hotel_summary: HotelSummary | None = None
        if "hotels" in include:
            hotels = HotelService(self._session).search_hotels(name)
            if hotels:
                price_range = PriceRange(
                    min=min(h.price_per_night for h in hotels),
                    max=max(h.price_per_night for h in hotels),
                )
                star_range = StarRange(
                    min=min(h.star_rating for h in hotels),
                    max=max(h.star_rating for h in hotels),
                )
                sample = sorted(hotels, key=lambda h: -h.rating)[:3]
            else:
                price_range = None
                star_range = None
                sample = []
            hotel_summary = HotelSummary(
                count=len(hotels),
                price_range_usd=price_range,
                star_range=star_range,
                sample=sample,
            )

        weather = None
        if "weather" in include:
            try:
                weather = await weather_service.get_weather(name)
            except Exception:
                # Best-effort enrichment — any weather failure degrades to null, never fails the overview.
                logger.warning(
                    "[destination_service] Weather unavailable for %s; returning null",
                    name,
                    exc_info=True,
                )

        return DestinationOverviewResponse(
            city=name,
            country=country,
            latitude=latitude,
            longitude=longitude,
            weather=weather,
            top_places=places,
            essential_tips=tips,
            hotel_summary=hotel_summary,
            attribution=_ATTRIBUTION,
        )


def get_destination_service(
    session: Annotated[Session, Depends(get_session)],
) -> DestinationService:
    """FastAPI dependency: a destination service bound to the request session."""
    return DestinationService(session)
