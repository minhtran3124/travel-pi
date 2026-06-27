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
from app.services.routing_service import RoutingService
from app.tools._base import dump, session_scope


@tool
async def get_route(origin_place_id: str, destination_place_id: str) -> dict:
    """Get distance and travel time between two places (by id or PLC-XXXX code).

    Returns distance + duration per travel mode (walk / bike / car), a
    recommended mode for the distance, and the straight-line km. Accepts full
    place ids or the short PLC-XXXX codes. An unknown place id, or one without
    coordinates in the seed data, raises an error — use the search_places tool
    to find a valid place_id first.
    """
    with session_scope() as s:
        try:
            return dump(
                await RoutingService(s).get_place_route(
                    origin_place_id, destination_place_id
                )
            )
        except AppError as e:
            raise ToolException(str(e)) from e


@tool
async def get_city_route(origin_city: str, destination_city: str) -> dict:
    """Get distance and travel time between two cities by name.

    Returns distance + duration per travel mode (walk / bike / car), a
    recommended mode, and the straight-line km. City names are fuzzy /
    typo-tolerant (e.g. 'danang' -> 'Da Nang'). An unknown city, or one without
    coordinates in the seed data, raises an error.
    """
    with session_scope() as s:
        try:
            return dump(
                await RoutingService(s).get_city_route(origin_city, destination_city)
            )
        except AppError as e:
            raise ToolException(str(e)) from e


ROUTING_TOOLS = [get_route, get_city_route]
