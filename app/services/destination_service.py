"""Destination overview — read-only composition over existing services.

Fans out to the place, tip, hotel, airport, and weather services and stitches
their results into one :class:`DestinationOverview`. No new storage and no new
data — just an agent-friendly aggregate so a trip planner can size up a city
in a single round-trip instead of four or five.

Weather is the only piece that makes a live outbound call, so it is
best-effort: if Open-Meteo is unreachable the overview still returns with
``weather: null`` rather than failing the whole request.
"""

import logging

from app.core.text import best_match
from app.data.cities import CITIES
from app.exceptions import NotFoundError, UpstreamError
from app.schemas.destination import DestinationOverview
from app.services import (
    airport_service,
    hotel_service,
    place_service,
    tip_service,
    weather_service,
)

logger = logging.getLogger(__name__)

_ALL_CITIES: list[dict] = list(CITIES)

# Default number of top-rated places to surface in the overview.
DEFAULT_TOP_PLACES = 5


async def get_overview(
    city_name: str, *, top_places: int = DEFAULT_TOP_PLACES
) -> DestinationOverview:
    """Return a one-call snapshot of ``city_name``.

    Raises :class:`NotFoundError` if the city can't be resolved. Weather is
    best-effort — an upstream failure leaves ``weather`` null and logs a
    warning, but never fails the request.
    """
    record = best_match(city_name, _ALL_CITIES, [lambda c: c["name"]])
    if record is None:
        raise NotFoundError(
            f"Destination city {city_name!r} not found",
            hint="Use GET /cities?q=<partial-name> to find a supported city.",
        )

    city = record["name"]
    country = record["country"]

    places = place_service.search_places(city=city, sort="rating_desc")[:top_places]
    tips = tip_service.get_tips(city=city, essential_only=True).tips
    hotel_count = len(hotel_service.search_hotels(city))
    airports = [
        airport
        for code in record.get("airport_codes", [])
        if (airport := airport_service.get_airport(code)) is not None
    ]

    weather = None
    try:
        weather = await weather_service.get_weather(city)
    except UpstreamError as exc:
        # 502-class failure (Open-Meteo down / unexpected shape) — degrade.
        logger.warning("Weather unavailable for destination overview %s: %s", city, exc)
    except NotFoundError as exc:
        # Geocoding couldn't place the city — odd for a seeded city, but the
        # overview is still useful without weather.
        logger.warning("Weather geocoding failed for %s: %s", city, exc)

    summary = (
        f"{city}, {country} · {hotel_count} hotel(s) · "
        f"{len(places)} top place(s) · {len(tips)} essential tip(s)"
    )

    return DestinationOverview(
        city=city,
        country=country,
        latitude=record.get("latitude"),
        longitude=record.get("longitude"),
        airports=airports,
        hotel_count=hotel_count,
        top_places=places,
        essential_tips=tips,
        weather=weather,
        summary=summary,
    )
