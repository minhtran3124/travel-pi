"""Side-panel artifact projections (specs/agent-side-panel).

A panel-capable tool returns ``(summary, artifact)`` via
``response_format="content_and_artifact"``; the artifact is
``{"kind": <PanelKind>, "data": <projection>}``. The mapper forwards it as a
``panel`` SSE event and the FE renders by ``kind``. Projections are deliberately
lean — only what the drawer draws, not the full tool result (which would bloat
the persisted checkpoint).

Only ``RoutePanel`` exists today (the route tool is the first panel-capable one);
``places`` / ``weather`` projections land alongside their tool conversions.
"""

from __future__ import annotations

from typing import Literal

from app.schemas.base import AppBaseModel
from app.schemas.route import RouteResponse

PanelKind = Literal["route", "places", "weather"]


def _gmaps_dir_url(o_lat: float, o_lng: float, d_lat: float, d_lng: float) -> str:
    """Keyless Google Maps directions deep-link (no API key required)."""
    return (
        "https://www.google.com/maps/dir/?api=1"
        f"&origin={o_lat},{o_lng}&destination={d_lat},{d_lng}"
    )


class RoutePanelEndpoint(AppBaseModel):
    name: str
    lat: float
    lng: float


class RoutePanelLeg(AppBaseModel):
    mode: str
    distance_km: float
    duration_minutes: float


class RoutePanel(AppBaseModel):
    """``data`` payload for a ``kind="route"`` panel — the map drawer's model."""

    origin: RoutePanelEndpoint
    destination: RoutePanelEndpoint
    recommended_mode: str
    legs: list[RoutePanelLeg]
    straight_line_km: float
    source: str
    geometry: list[list[float]] | None = None
    gmaps_url: str

    @classmethod
    def from_route_response(cls, r: RouteResponse) -> RoutePanel:
        """Project a service ``RouteResponse`` into the route panel render model."""
        return cls(
            origin=RoutePanelEndpoint(
                name=r.origin.name, lat=r.origin.latitude, lng=r.origin.longitude
            ),
            destination=RoutePanelEndpoint(
                name=r.destination.name,
                lat=r.destination.latitude,
                lng=r.destination.longitude,
            ),
            recommended_mode=r.recommended_mode,
            legs=[
                RoutePanelLeg(
                    mode=leg.mode,
                    distance_km=leg.distance_km,
                    duration_minutes=leg.duration_minutes,
                )
                for leg in r.legs
            ],
            straight_line_km=r.straight_line_km,
            source=r.source,
            geometry=r.geometry,
            gmaps_url=_gmaps_dir_url(
                r.origin.latitude,
                r.origin.longitude,
                r.destination.latitude,
                r.destination.longitude,
            ),
        )
