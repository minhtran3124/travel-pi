"""Destination overview aggregation service.

Bundles weather, top places, essential tips, and hotel statistics for a
city into a single :class:`DestinationOverviewResponse`. Intended as the
backing logic for ``GET /destinations/{city}/overview``.

Only ``get_overview`` is ``async`` — the weather call is the sole network
I/O; all other helpers are sync in-memory lookups.
"""

import logging

from app.core.config import get_settings
from app.core.text import best_match
from app.crud.city import CityRepository
from app.db.engine import get_session_factory
from app.exceptions import NotFoundError
from app.schemas.destination import (
    DestinationOverviewResponse,
    HotelSummary,
    PriceRange,
    StarRange,
)
from app.services import hotel_service, place_service, tip_service, weather_service

logger = logging.getLogger(__name__)

_ATTRIBUTION = "Weather data by Open-Meteo.com (CC BY 4.0)"

# City data is DB-backed; fuzzy resolution stays here (over the repo's distinct
# names). Not a FastAPI dependency, so tests repoint it via ``set_city_repo``.
_city_repo = CityRepository(get_session_factory(get_settings().database_url))


def set_city_repo(repo: CityRepository) -> None:
    """Point city reads at a different store — used by tests."""
    global _city_repo
    _city_repo = repo


async def get_overview(
    city: str,
    *,
    include: set[str],
    place_limit: int,
    tip_limit: int,
) -> DestinationOverviewResponse:
    """Return an aggregated destination overview for *city*.

    Parameters
    ----------
    city:
        Free-text city name (fuzzy-matched against the canonical city list).
    include:
        Set of section names to populate — ``"places"``, ``"tips"``,
        ``"hotels"``, ``"weather"``. Sections not in the set are omitted
        (empty list / ``None``).
    place_limit:
        Maximum number of top places to return.
    tip_limit:
        Maximum number of essential tips to return.

    Raises
    ------
    NotFoundError
        When *city* cannot be resolved to a known city (HTTP 404).
    """
    # 1. Resolve city locally — no network. Fuzzy-match over the distinct city
    #    names, then fetch the exact record for its coordinates / country.
    matched = best_match(city, _city_repo.distinct_names(), [lambda c: c])
    record = _city_repo.get(matched) if matched is not None else None
    if record is None:
        raise NotFoundError(
            f"City '{city}' not found",
            hint="Call GET /cities to list available cities.",
        )
    name: str = record.name
    country: str = record.country
    latitude: float = record.latitude
    longitude: float = record.longitude

    # 2. Places — sync, in-memory.
    places = []
    if "places" in include:
        results = place_service.search_places(city=name, sort="rating_desc")
        # Recommended places first, then by rating (search already sorted by
        # rating, so the tuple key keeps that order within each group).
        results.sort(key=lambda p: (not p.is_recommended, -p.rating))
        places = results[:place_limit]

    # 3. Tips — sync, in-memory.
    tips = []
    if "tips" in include:
        tips_response = tip_service.get_tips(city=name, essential_only=True)
        tips = tips_response.tips[:tip_limit]

    # 4. Hotels — sync, in-memory.
    hotel_summary: HotelSummary | None = None
    if "hotels" in include:
        hotels = hotel_service.search_hotels(name)
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

    # 5. Weather — async, real network I/O; degrade gracefully on upstream errors.
    weather = None
    if "weather" in include:
        try:
            weather = await weather_service.get_weather(name)
        except Exception:
            # Weather is best-effort enrichment: the destination already
            # resolved locally, so ANY weather failure — an upstream outage,
            # Open-Meteo not recognising the city name, or a malformed upstream
            # response — must degrade to weather: null rather than fail the
            # whole overview (its documented contract).
            logger.warning(
                "[destination_service] Weather unavailable for %s; returning null",
                name,
                exc_info=True,
            )

    # 6. Assemble and return.
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
