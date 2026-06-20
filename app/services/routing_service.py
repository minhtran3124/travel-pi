"""Routing between two places or cities — distance, time, travel mode.

Backs ``GET /places/route`` and ``GET /cities/route``. Like
``weather_service`` this module can make a *real* outbound call, here to
OpenRouteService (ORS) for road distance and duration per travel mode. ORS
is free but needs an API key, so the feature degrades gracefully: with no
``ORS_API_KEY`` configured it falls back to an offline straight-line
(haversine) estimate, and the response says which via its ``source`` field.

Results are cached in-process keyed by the two endpoints — the seed data is
fixed, so a route never changes — which keeps the suite offline and protects
the ORS free-tier quota (2000 requests/day).

The outbound call is fully async (``httpx.AsyncClient``) so the routes can be
``async def``. Tests monkeypatch ``_fetch_json`` to avoid the network. City
data is read through a ``CityRepository`` bound to the request session, and
place resolution goes through a ``PlaceService`` on the same session.
"""

import asyncio
import logging
from typing import Annotated

import httpx
from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.geo import haversine_km
from app.core.text import best_match
from app.db.session import get_session
from app.exceptions import NotFoundError, RoutingUnavailableError
from app.repositories.city import CityRepository
from app.schemas.route import RouteEndpoint, RouteLeg, RouteResponse
from app.services.place_service import PlaceService

logger = logging.getLogger(__name__)

# Friendly mode label -> (ORS routing profile, fallback speed in km/h).
# The fallback speeds are rough city-travel averages, used only when no ORS
# key is configured.
_MODES: dict[str, tuple[str, float]] = {
    "walk": ("foot-walking", 4.5),
    "bike": ("cycling-regular", 15.0),
    "car": ("driving-car", 35.0),
}

# Straight-line distances under/over these thresholds (km) pick the
# recommended travel mode.
_WALK_MAX_KM = 1.5
_BIKE_MAX_KM = 8.0

# Roads are never straight — scale the haversine distance by this factor for
# the offline estimate so it is a little closer to real travel distance.
_DETOUR_FACTOR = 1.3

_ATTRIBUTION_ORS = (
    "Routing © openrouteservice.org by HeiGIT | Map data © OpenStreetMap contributors"
)
_ATTRIBUTION_ESTIMATE = (
    "Offline straight-line estimate (set ORS_API_KEY for real road routing)"
)

# Process-wide route cache. Keyed by both endpoints plus whether the ORS
# provider is enabled, so a cached offline estimate is never served after an
# API key is configured (or vice versa).
_route_cache: dict[tuple, RouteResponse] = {}


def clear_route_cache() -> None:
    """Empty the route cache. Used by tests to keep cases isolated."""
    _route_cache.clear()


def recommend_mode(distance_km: float) -> str:
    """Pick a sensible travel mode for a straight-line distance.

    Short hops are walkable, medium distances suit a bike/motorbike, and
    anything longer wants a car.
    """
    if distance_km <= _WALK_MAX_KM:
        return "walk"
    if distance_km <= _BIKE_MAX_KM:
        return "bike"
    return "car"


async def _fetch_json(url: str, params: dict) -> dict:
    """GET ``url`` with ``params`` and return parsed JSON.

    Any transport/HTTP error is normalised to :class:`RoutingUnavailableError`
    so callers never see raw ``httpx`` exceptions.
    """
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=settings.ors_timeout_seconds) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as exc:  # timeouts, connection + status errors
        logger.warning("OpenRouteService request to %s failed: %s", url, exc)
        raise RoutingUnavailableError(str(exc)) from exc


async def _ors_leg(
    mode: str, profile: str, origin: RouteEndpoint, destination: RouteEndpoint
) -> RouteLeg:
    """Fetch one travel mode's distance/duration from OpenRouteService."""
    settings = get_settings()
    url = f"{settings.ors_base_url}/v2/directions/{profile}"
    data = await _fetch_json(
        url,
        {
            "api_key": settings.ors_api_key,
            # ORS expects coordinates as "longitude,latitude".
            "start": f"{origin.longitude},{origin.latitude}",
            "end": f"{destination.longitude},{destination.latitude}",
        },
    )
    try:
        summary = data["features"][0]["properties"]["summary"]
        distance_m = float(summary["distance"])
        duration_s = float(summary["duration"])
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise RoutingUnavailableError(
            f"Unexpected OpenRouteService response for profile '{profile}'"
        ) from exc
    return RouteLeg(
        mode=mode,
        profile=profile,
        distance_km=round(distance_m / 1000, 2),
        duration_minutes=round(duration_s / 60, 1),
    )


def _estimate_leg(
    mode: str, profile: str, speed_kmh: float, straight_line_km: float
) -> RouteLeg:
    """Build one travel mode's leg from the offline haversine estimate."""
    distance_km = straight_line_km * _DETOUR_FACTOR
    duration_minutes = (distance_km / speed_kmh) * 60 if speed_kmh else 0.0
    return RouteLeg(
        mode=mode,
        profile=profile,
        distance_km=round(distance_km, 2),
        duration_minutes=round(duration_minutes, 1),
    )


class RoutingService:
    """Routing between two places or cities, bound to the request session."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._city = CityRepository(session)
        self._places = PlaceService(session)

    def _place_endpoint(self, place_id: str, label: str) -> RouteEndpoint:
        """Resolve a place ID to a :class:`RouteEndpoint`.

        Raises :class:`NotFoundError` if the ID is unknown or the place has no
        coordinates (so it cannot take part in a route).
        """
        place = self._places.get_place(place_id)
        if place is None:
            raise NotFoundError(
                f"{label} place '{place_id}' not found",
                hint=(
                    "Use GET /places/search?city=<city> to find a valid place_id "
                    "(or pass the short PLC-XXXX code)."
                ),
            )
        if place.latitude is None or place.longitude is None:
            raise NotFoundError(
                f"{label} place '{place_id}' has no coordinates",
                hint=(
                    "This place is missing latitude/longitude in the seed data "
                    "and cannot take part in a route. Pick another place from "
                    "GET /places/search."
                ),
            )
        return RouteEndpoint(
            kind="place",
            id=place.id,
            name=place.name,
            latitude=place.latitude,
            longitude=place.longitude,
        )

    def _city_endpoint(self, city_name: str, label: str) -> RouteEndpoint:
        """Resolve a city name to a :class:`RouteEndpoint`, fuzzily.

        The lookup is forgiving — case-insensitive and typo/spacing tolerant
        (e.g. "danang" → "Da Nang") — using the same fuzzy matcher as
        ``GET /cities?q=``, so callers need not know the exact spelling. Raises
        :class:`NotFoundError` if nothing matches or the matched city has no
        coordinates in the seed data.
        """
        matched = best_match(city_name, self._city.distinct_names(), [lambda c: c])
        record = self._city.get(matched) if matched is not None else None
        if record is None:
            raise NotFoundError(
                f"{label} city '{city_name}' not found",
                hint=(
                    "Use GET /cities?q=<partial-name> to find the canonical "
                    "city name (the lookup is fuzzy / typo-tolerant)."
                ),
            )
        if record.latitude is None or record.longitude is None:
            raise NotFoundError(
                f"{label} city '{record.name}' has no coordinates",
                hint=(
                    "This city is missing latitude/longitude in the seed data "
                    "and cannot take part in a route."
                ),
            )
        return RouteEndpoint(
            kind="city",
            id=record.name,
            name=record.name,
            latitude=record.latitude,
            longitude=record.longitude,
        )

    async def get_route_between(
        self, origin: RouteEndpoint, destination: RouteEndpoint
    ) -> RouteResponse:
        """Return distance/time per travel mode between two resolved endpoints.

        Calls OpenRouteService for real road routing when ``ORS_API_KEY`` is set,
        otherwise falls back to an offline straight-line estimate. Results are
        cached per endpoint pair. Raises :class:`RoutingUnavailableError` if a
        configured ORS provider is unreachable.
        """
        settings = get_settings()
        provider_enabled = settings.routing_provider_enabled
        cache_key = (
            origin.kind,
            origin.id,
            destination.kind,
            destination.id,
            provider_enabled,
        )
        cached = _route_cache.get(cache_key)
        if cached is not None:
            return cached

        straight_line_km = round(
            haversine_km(
                origin.latitude,
                origin.longitude,
                destination.latitude,
                destination.longitude,
            ),
            2,
        )

        if provider_enabled:
            # Fetch every travel mode concurrently — one round-trip's latency
            # instead of three back to back. ``return_exceptions=True`` so a
            # single failing leg (rare — all three call the same ORS host)
            # falls back to the offline estimate for that mode instead of
            # taking the whole response down with it.
            results = await asyncio.gather(
                *(
                    _ors_leg(mode, profile, origin, destination)
                    for mode, (profile, _speed) in _MODES.items()
                ),
                return_exceptions=True,
            )
            legs = []
            any_ors = False
            any_fallback = False
            for (mode, (profile, speed)), result in zip(
                _MODES.items(), results, strict=True
            ):
                if isinstance(result, BaseException):
                    logger.warning(
                        "ORS leg %s failed (%s) — falling back to offline estimate",
                        mode,
                        result,
                    )
                    legs.append(_estimate_leg(mode, profile, speed, straight_line_km))
                    any_fallback = True
                else:
                    legs.append(result)
                    any_ors = True
            # If at least one leg came from ORS, keep ``source="openrouteservice"``
            # so the response still flags real routing as the primary source; if
            # every leg fell back, surface that honestly to the caller.
            if any_ors:
                source = "openrouteservice"
                attribution = (
                    _ATTRIBUTION_ORS
                    if not any_fallback
                    else _ATTRIBUTION_ORS + " (some modes estimated offline)"
                )
            else:
                source = "estimate"
                attribution = _ATTRIBUTION_ESTIMATE
        else:
            legs = [
                _estimate_leg(mode, profile, speed, straight_line_km)
                for mode, (profile, speed) in _MODES.items()
            ]
            source = "estimate"
            attribution = _ATTRIBUTION_ESTIMATE

        response = RouteResponse(
            origin=origin,
            destination=destination,
            straight_line_km=straight_line_km,
            recommended_mode=recommend_mode(straight_line_km),
            legs=legs,
            source=source,
            attribution=attribution,
        )
        _route_cache[cache_key] = response
        return response

    async def get_place_route(
        self, origin_id: str, destination_id: str
    ) -> RouteResponse:
        """Route between two places, by place ID (404 if unknown / no coords)."""
        origin = self._place_endpoint(origin_id, "Origin")
        destination = self._place_endpoint(destination_id, "Destination")
        return await self.get_route_between(origin, destination)

    async def get_city_route(
        self, origin_name: str, destination_name: str
    ) -> RouteResponse:
        """Route between two cities, by city name (404 if unknown / no coords)."""
        origin = self._city_endpoint(origin_name, "Origin")
        destination = self._city_endpoint(destination_name, "Destination")
        return await self.get_route_between(origin, destination)


def get_routing_service(
    session: Annotated[Session, Depends(get_session)],
) -> RoutingService:
    """FastAPI dependency: a routing service bound to the request session."""
    return RoutingService(session)
