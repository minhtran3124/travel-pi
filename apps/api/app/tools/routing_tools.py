"""Routing / directions tools (specs/agent-tools-mizumi-parity).

Wrap ``RoutingService`` as LLM tools so the agent can answer distance/duration
questions between two places or two cities. Like ``weather_tools`` these wrap a
*real* outbound call (OpenRouteService); with no ORS key configured the service
degrades to an offline straight-line (haversine) estimate, so the tools work
offline too. The service is async, so the tools are async. Each opens its own
session via ``session_scope`` (tools run in the graph, not a request) and maps
domain errors to ``ToolException`` so the agent can self-correct.
"""

from __future__ import annotations

from langchain_core.tools import ToolException, tool

from app.exceptions import AppError
from app.schemas.route import RouteResponse
from app.services.routing_service import RoutingService
from app.streaming.panels import RoutePanel
from app.tools._base import panel_result, session_scope


def _route_panel(r: RouteResponse) -> tuple[str, dict]:
    """One-line summary for the model + a route panel artifact for the drawer.

    response_format="content_and_artifact": the model only needs the headline
    distance/time; the full route (endpoints, geometry, all modes, gmaps link)
    rides on the artifact to the side-panel, not into the model's context.
    """
    leg = next((leg for leg in r.legs if leg.mode == r.recommended_mode), r.legs[0])
    summary = (
        f"{r.origin.name} → {r.destination.name}: {leg.distance_km} km, "
        f"~{leg.duration_minutes:.0f} min by {r.recommended_mode}."
    )
    return panel_result(summary, kind="route", data=RoutePanel.from_route_response(r))


@tool(response_format="content_and_artifact")
async def get_route(origin_place_id: str, destination_place_id: str):
    """Get distance and travel time between two places (by id or PLC-XXXX code).

    Returns distance + duration per travel mode (walk / bike / car), a
    recommended mode for the distance, and the straight-line km. Accepts full
    place ids or the short PLC-XXXX codes. An unknown place id, or one without
    coordinates in the seed data, raises an error — use the search_places tool
    to find a valid place_id first.
    """
    with session_scope() as s:
        try:
            r = await RoutingService(s).get_place_route(
                origin_place_id, destination_place_id
            )
        except AppError as e:
            raise ToolException(str(e)) from e
    return _route_panel(r)


@tool(response_format="content_and_artifact")
async def get_city_route(origin_city: str, destination_city: str):
    """Get distance and travel time between two cities by name.

    Returns distance + duration per travel mode (walk / bike / car), a
    recommended mode, and the straight-line km. City names are fuzzy /
    typo-tolerant (e.g. 'danang' -> 'Da Nang'). An unknown city, or one without
    coordinates in the seed data, raises an error.
    """
    with session_scope() as s:
        try:
            r = await RoutingService(s).get_city_route(origin_city, destination_city)
        except AppError as e:
            raise ToolException(str(e)) from e
    return _route_panel(r)


ROUTING_TOOLS = [get_route, get_city_route]
