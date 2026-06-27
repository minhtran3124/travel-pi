"""Routing tools tests (specs/agent-tools-mizumi-parity).

Run offline: no ORS key is configured, so RoutingService uses the haversine
estimate path (source == "estimate") — no network. Tools are async, so we drive
them via asyncio.run(tool.ainvoke(...)).
"""

import asyncio

import pytest
from app.services.place_service import PlaceService
from app.tools._base import session_scope
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


def _assert_route_shape(out: dict) -> None:
    assert isinstance(out, dict)
    assert out["source"] == "estimate"
    assert "straight_line_km" in out
    assert out["recommended_mode"] in {"walk", "bike", "car"}
    modes = {leg["mode"] for leg in out["legs"]}
    assert modes == {"walk", "bike", "car"}


def test_get_city_route_offline_estimate(agent_db):
    from app.tools.routing_tools import get_city_route

    out = asyncio.run(
        get_city_route.ainvoke({"origin_city": "Tokyo", "destination_city": "Kyoto"})
    )
    _assert_route_shape(out)


def test_get_route_between_places_offline_estimate(agent_db):
    from app.tools.routing_tools import get_route

    origin, destination = _two_place_ids("Tokyo")
    out = asyncio.run(
        get_route.ainvoke(
            {"origin_place_id": origin, "destination_place_id": destination}
        )
    )
    _assert_route_shape(out)


def test_get_route_unknown_place_raises(agent_db):
    from app.tools.routing_tools import get_route

    with pytest.raises(ToolException):
        asyncio.run(
            get_route.ainvoke(
                {"origin_place_id": "PLC-NOPE", "destination_place_id": "PLC-NOPE2"}
            )
        )
