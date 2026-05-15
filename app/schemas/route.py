"""Route schemas — the response shape for the routing endpoints.

Shared by ``GET /places/route`` (place → place) and ``GET /cities/route``
(city → city).
"""

from app.schemas.base import AppBaseModel


class RouteEndpoint(AppBaseModel):
    """One end of a route — a resolved place or city with its coordinates."""

    kind: str  # "place" | "city"
    id: str  # the place ID, or the city name
    name: str
    latitude: float
    longitude: float


class RouteLeg(AppBaseModel):
    """Distance and time for one travel mode between the two endpoints."""

    mode: str  # walk | bike | car — the friendly label
    profile: str  # ORS routing profile, e.g. "foot-walking"
    distance_km: float
    duration_minutes: float


class RouteResponse(AppBaseModel):
    """Response body for the routing endpoints.

    ``legs`` carries one entry per travel mode (walk / bike / car) so a
    client can compare them; ``recommended_mode`` is the sensible default
    for the distance involved. ``source`` says where the numbers came from:
    ``"openrouteservice"`` for real road routing, or ``"estimate"`` for the
    offline straight-line fallback used when no ORS API key is configured.
    """

    origin: RouteEndpoint
    destination: RouteEndpoint
    straight_line_km: float
    recommended_mode: str
    legs: list[RouteLeg]
    source: str  # "openrouteservice" | "estimate"
    attribution: str
