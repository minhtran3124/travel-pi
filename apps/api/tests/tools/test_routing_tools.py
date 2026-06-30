"""Routing tools tests (specs/agent-tools-mizumi-parity; agent-side-panel Task 1.2).

Run offline: no ORS key is configured, so RoutingService uses the haversine
estimate path (source == "estimate") — no network. The tools now use
``response_format="content_and_artifact"``: invoking with a ToolCall returns a
``ToolMessage`` whose ``.content`` is the model-facing summary and whose
``.artifact`` is the ``{"kind":"route","data":...}`` side-panel payload. Tools are
async, so we drive them via ``asyncio.run(tool.ainvoke(...))``.
"""

import asyncio

import pytest
from app.services.place_service import PlaceService
from app.tools._base import session_scope
from langchain_core.messages import ToolMessage
from langchain_core.tools import ToolException


def _two_place_ids(city: str) -> tuple[str, str]:
    """Return two distinct place ids in a city that both have coordinates."""
    with session_scope() as s:
        places = [
            p
            for p in PlaceService(s).search_places(city=city)
            if p.latitude is not None and p.longitude is not None
        ]
    assert len(places) >= 2, f"need >=2 placed-with-coords in {city}"
    return places[0].id, places[1].id


def _invoke(tool, args: dict) -> ToolMessage:
    """Invoke a content_and_artifact tool via a ToolCall → ToolMessage."""
    return asyncio.run(
        tool.ainvoke({"type": "tool_call", "id": "t1", "name": tool.name, "args": args})
    )


def _assert_route_message(msg: ToolMessage) -> None:
    assert isinstance(msg, ToolMessage)
    # Model-facing summary: a short non-empty string, not the full JSON dump.
    assert isinstance(msg.content, str) and msg.content.strip()
    # Side-panel artifact carries the rich route data.
    assert msg.artifact["kind"] == "route"
    data = msg.artifact["data"]
    assert data["source"] == "estimate"
    assert data["geometry"] is None  # estimate mode → no road line
    assert data["recommended_mode"] in {"walk", "bike", "car"}
    assert {leg["mode"] for leg in data["legs"]} == {"walk", "bike", "car"}
    assert data["gmaps_url"].startswith("https://www.google.com/maps/dir/")


def test_get_city_route_offline_estimate(agent_db):
    from app.tools.routing_tools import get_city_route

    msg = _invoke(get_city_route, {"origin_city": "Tokyo", "destination_city": "Kyoto"})
    _assert_route_message(msg)


def test_get_route_between_places_offline_estimate(agent_db):
    from app.tools.routing_tools import get_route

    origin, destination = _two_place_ids("Tokyo")
    msg = _invoke(
        get_route, {"origin_place_id": origin, "destination_place_id": destination}
    )
    _assert_route_message(msg)


def test_get_route_unknown_place_raises(agent_db):
    from app.tools.routing_tools import get_route

    with pytest.raises(ToolException):
        asyncio.run(
            get_route.ainvoke(
                {"origin_place_id": "PLC-NOPE", "destination_place_id": "PLC-NOPE2"}
            )
        )
