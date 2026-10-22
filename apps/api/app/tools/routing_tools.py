"""Routing / directions tools wrapping ``RoutingService``; with no ORS key the service degrades to an
offline haversine estimate, so the tools work offline too."""

from __future__ import annotations

from langchain_core.tools import tool
from pydantic import Field

from app.exceptions import AppError, UpstreamError
from app.schemas.base import AppBaseModel
from app.schemas.route import RouteResponse
from app.services.routing_service import RoutingService
from app.streaming.panels import RoutePanel
from app.tools._base import log_tool_call, panel_result, session_scope, tool_error


class GetRouteArgs(AppBaseModel):
    origin_place_id: str = Field(
        ..., description="The origin place's id or PLC-XXXX short code."
    )
    destination_place_id: str = Field(
        ..., description="The destination place's id or PLC-XXXX short code."
    )


class GetCityRouteArgs(AppBaseModel):
    origin_city: str = Field(..., description="The origin city name.")
    destination_city: str = Field(..., description="The destination city name.")


def _route_panel(r: RouteResponse) -> tuple[str, dict]:
    """One-line summary for the model plus a route panel artifact: the model gets only the headline
    distance/time while the full route rides on the artifact to the side-panel."""
    leg = next((leg for leg in r.legs if leg.mode == r.recommended_mode), r.legs[0])
    summary = (
        f"{r.origin.name} → {r.destination.name}: {leg.distance_km} km, "
        f"~{leg.duration_minutes:.0f} min by {r.recommended_mode}."
    )
    return panel_result(summary, kind="route", data=RoutePanel.from_route_response(r))


@tool(args_schema=GetRouteArgs, response_format="content_and_artifact")
async def get_route(origin_place_id: str, destination_place_id: str):
    """Get distance and travel time between two places (by id or PLC-XXXX code).

    Accepts full place ids or the short PLC-XXXX codes. An unknown place id, or
    one without coordinates in the seed data, raises an error — use the
    search_places tool to find a valid place_id first.

    :param origin_place_id: The origin place's id or PLC-XXXX short code.
    :param destination_place_id: The destination place's id or PLC-XXXX short code.
    :return: Distance + duration per travel mode (walk / bike / car), a
        recommended mode for the distance, and the straight-line km.
    """
    log_tool_call("get_route", locals())
    with session_scope() as s:
        try:
            r = await RoutingService(s).get_place_route(
                origin_place_id, destination_place_id
            )
        except UpstreamError:
            raise  # transient — let RetryPolicy retry the node
        except AppError as e:
            raise tool_error(e) from e
    return _route_panel(r)


@tool(args_schema=GetCityRouteArgs, response_format="content_and_artifact")
async def get_city_route(origin_city: str, destination_city: str):
    """Get distance and travel time between two cities by name.

    City names are fuzzy / typo-tolerant (e.g. 'danang' -> 'Da Nang'). An
    unknown city, or one without coordinates in the seed data, raises an error.

    :param origin_city: The origin city name.
    :param destination_city: The destination city name.
    :return: Distance + duration per travel mode (walk / bike / car), a
        recommended mode, and the straight-line km.
    """
    log_tool_call("get_city_route", locals())
    with session_scope() as s:
        try:
            r = await RoutingService(s).get_city_route(origin_city, destination_city)
        except UpstreamError:
            raise  # transient — let RetryPolicy retry the node
        except AppError as e:
            raise tool_error(e) from e
    return _route_panel(r)


ROUTING_TOOLS = [get_route, get_city_route]
