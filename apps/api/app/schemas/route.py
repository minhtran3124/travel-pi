"""Route schemas — the response shape for the routing endpoints."""

from typing import Literal

from pydantic import Field

from app.schemas.base import AppBaseModel

# Closed sets exposed in OpenAPI so FE codegen produces real TS unions, not plain strings.
EndpointKind = Literal["place", "city"]
TravelMode = Literal["walk", "bike", "car"]
ORSProfile = Literal["foot-walking", "cycling-regular", "driving-car"]
RouteSource = Literal["openrouteservice", "estimate"]


class RouteEndpoint(AppBaseModel):
    """One end of a route — a resolved place or city with its coordinates."""

    kind: EndpointKind = Field(
        description="What `id` refers to: a place (UUID) or a city (name).",
        examples=["place"],
    )
    id: str = Field(
        description="Place ID (or short code) for places, canonical city name for cities.",
        examples=["56f5b6d7-f0e2-5867-a9dd-087a98cff34c"],
    )
    name: str = Field(description="Display name of the place or city.")
    latitude: float = Field(description="Latitude, decimal degrees (WGS-84).")
    longitude: float = Field(description="Longitude, decimal degrees (WGS-84).")


class RouteLeg(AppBaseModel):
    """Distance and time for one travel mode between the two endpoints."""

    mode: TravelMode = Field(description="Travel mode.", examples=["car"])
    profile: ORSProfile = Field(
        description="OpenRouteService routing profile this leg used.",
        examples=["driving-car"],
    )
    distance_km: float = Field(description="Route distance in kilometres.")
    duration_minutes: float = Field(description="Route duration in minutes.")


class RouteResponse(AppBaseModel):
    """Response body for the routing endpoints."""

    origin: RouteEndpoint
    destination: RouteEndpoint
    straight_line_km: float = Field(
        description="Great-circle (haversine) distance between the endpoints, km."
    )
    recommended_mode: TravelMode = Field(
        description="Sensible default mode for the distance: walk < ~1.5 km, bike < ~8 km, car otherwise."
    )
    legs: list[RouteLeg] = Field(
        description="One leg per travel mode (walk, bike, car) for comparison."
    )
    source: RouteSource = Field(
        description=(
            "'openrouteservice' for real road routing, 'estimate' for the "
            "offline straight-line fallback when no ORS_API_KEY is set."
        ),
        examples=["estimate"],
    )
    geometry: list[list[float]] | None = Field(
        default=None,
        description=(
            "Road-path polyline for the recommended mode as GeoJSON [longitude, "
            "latitude] coordinate pairs, when real ORS routing is used; null in "
            "estimate mode (no ORS_API_KEY), where clients should draw a straight "
            "line between the endpoints."
        ),
    )
    attribution: str = Field(
        description="Required attribution string for the data source."
    )
