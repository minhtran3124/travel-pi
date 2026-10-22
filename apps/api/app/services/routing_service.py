"""Routing between two places or cities via OpenRouteService, with an offline haversine fallback when no ORS key is set."""

import asyncio
import logging
from typing import Annotated

import httpx
from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.geo import haversine_km
from app.core.text import best_match, match_score
from app.db.session import get_session
from app.exceptions import NotFoundError, RoutingUnavailableError
from app.repositories.city import CityRepository
from app.schemas.route import RouteEndpoint, RouteLeg, RouteResponse
from app.services.place_service import PlaceService
from app.services.weather_service import geocode_city

logger = logging.getLogger(__name__)

# Weak seed matches (short proper nouns collide — "Phu Yen" ~0.62 vs "Phuket") defer to the geocoder rather than routing to the wrong city.
_SEED_MATCH_CONFIDENT = 0.8

# Friendly mode label -> (ORS routing profile, offline fallback speed in km/h).
_MODES: dict[str, tuple[str, float]] = {
    "walk": ("foot-walking", 4.5),
    "bike": ("cycling-regular", 15.0),
    "car": ("driving-car", 35.0),
}

_WALK_MAX_KM = 1.5
_BIKE_MAX_KM = 8.0

# Roads are never straight — scale the haversine estimate toward real travel distance.
_DETOUR_FACTOR = 1.3

_ATTRIBUTION_ORS = (
    "Routing © openrouteservice.org by HeiGIT | Map data © OpenStreetMap contributors"
)
_ATTRIBUTION_ESTIMATE = (
    "Offline straight-line estimate (set ORS_API_KEY for real road routing)"
)

# Keyed on provider-enabled too, so a cached offline estimate is never served after an API key is configured (or vice versa).
_route_cache: dict[tuple, RouteResponse] = {}


def clear_route_cache() -> None:
    """Empty the route cache."""
    _route_cache.clear()


def recommend_mode(distance_km: float) -> str:
    """Pick a sensible travel mode for a straight-line distance."""
    if distance_km <= _WALK_MAX_KM:
        return "walk"
    if distance_km <= _BIKE_MAX_KM:
        return "bike"
    return "car"


async def _fetch_json(url: str, params: dict) -> dict:
    """GET ``url`` and return parsed JSON; transport/HTTP errors become :class:`RoutingUnavailableError`."""
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
) -> tuple[RouteLeg, list[list[float]] | None]:
    """Fetch one mode's distance/duration and best-effort road geometry from OpenRouteService (geometry is ``None`` if absent/malformed)."""
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
    geometry = None
    try:
        coords = data["features"][0]["geometry"]["coordinates"]
        if isinstance(coords, list) and coords:
            geometry = [[float(pt[0]), float(pt[1])] for pt in coords]
    except (KeyError, IndexError, TypeError, ValueError):
        geometry = None  # metrics still valid; just no map line for this mode
    leg = RouteLeg(
        mode=mode,
        profile=profile,
        distance_km=round(distance_m / 1000, 2),
        duration_minutes=round(duration_s / 60, 1),
    )
    return leg, geometry


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
        """Resolve a place ID to a :class:`RouteEndpoint` (404 if unknown or missing coordinates)."""
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

    async def _city_endpoint(self, city_name: str, label: str) -> RouteEndpoint:
        """Resolve a city name to a :class:`RouteEndpoint` — a confident seed match first, else the Open-Meteo geocoder."""
        matched = best_match(city_name, self._city.distinct_names(), [lambda c: c])
        if (
            matched is not None
            and match_score(city_name, matched) >= _SEED_MATCH_CONFIDENT
        ):
            record = self._city.get(matched)
            if (
                record is not None
                and record.latitude is not None
                and record.longitude is not None
            ):
                return RouteEndpoint(
                    kind="city",
                    id=record.name,
                    name=record.name,
                    latitude=record.latitude,
                    longitude=record.longitude,
                )

        # Keyless Open-Meteo geocoder — handles diacritics / non-English names and cities not in the seed.
        geo = await geocode_city(city_name)
        if geo is not None:
            return RouteEndpoint(
                kind="city",
                id=geo["name"],
                name=geo["name"],
                latitude=geo["latitude"],
                longitude=geo["longitude"],
            )

        raise NotFoundError(
            f"{label} city '{city_name}' not found",
            hint=(
                "Use GET /cities?q=<partial-name> to find a known city, or try a "
                "more specific name — routing also geocodes via Open-Meteo."
            ),
        )

    async def get_route_between(
        self, origin: RouteEndpoint, destination: RouteEndpoint
    ) -> RouteResponse:
        """Return distance/time per travel mode between two endpoints, cached per pair (ORS when keyed, else offline estimate)."""
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
            # Concurrent per-mode fetch; return_exceptions so one failing leg falls back to the offline estimate, not the whole response.
            results = await asyncio.gather(
                *(
                    _ors_leg(mode, profile, origin, destination)
                    for mode, (profile, _speed) in _MODES.items()
                ),
                return_exceptions=True,
            )
            legs = []
            geometries: dict[str, list[list[float]] | None] = {}
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
                    leg, geometry = result
                    legs.append(leg)
                    geometries[mode] = geometry
                    any_ors = True
            # Keep source="openrouteservice" if any leg is real; mark "estimate" only when every leg fell back.
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
            geometries = {}
            source = "estimate"
            attribution = _ATTRIBUTION_ESTIMATE

        # Only the recommended mode's geometry — clients draw one route; carrying all three would triple the payload.
        recommended = recommend_mode(straight_line_km)
        response = RouteResponse(
            origin=origin,
            destination=destination,
            straight_line_km=straight_line_km,
            recommended_mode=recommended,
            legs=legs,
            source=source,
            geometry=geometries.get(recommended),
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
        origin = await self._city_endpoint(origin_name, "Origin")
        destination = await self._city_endpoint(destination_name, "Destination")
        return await self.get_route_between(origin, destination)


def get_routing_service(
    session: Annotated[Session, Depends(get_session)],
) -> RoutingService:
    """FastAPI dependency: a routing service bound to the request session."""
    return RoutingService(session)
