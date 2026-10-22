"""The research model sees the ids its proposal must cite (research-proposal-validity SC-1).

The shared chat tools put ``place_id`` / ``offer_id`` / ``hotel_id`` only in the side-panel
``artifact``; the model reads names and flight numbers. A live run therefore wrote a proposal
with no place or hotel ids and flight numbers as offer ids. ``_ToolIdsToContent`` appends the
ids from the artifact to what the research model reads — the tools themselves are untouched.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from app.research.agent import _subagents, _ToolIdsToContent
from app.tools.flight_tools import search_flights
from app.tools.place_tools import search_places
from langchain_core.messages import ToolMessage


def _request(name: str) -> SimpleNamespace:
    return SimpleNamespace(tool_call={"name": name, "id": "c1", "args": {}})


def _message(
    content: str,
    artifact: dict | None,
    status: str = "success",
) -> ToolMessage:
    return ToolMessage(
        content=content,
        tool_call_id="c1",
        artifact=artifact,
        status=status,
    )


PLACES = {
    "kind": "places",
    "data": {
        "places": [
            {"id": "pl-1", "name": "Sao Beach", "category": "attraction"},
            {"id": "pl-2", "name": "Dinh Cau Night Market", "category": "nightlife"},
        ]
    },
}
FLIGHTS = {
    "kind": "flights",
    "data": {
        "flights": [
            {
                "id": "FL_SGN_PQC_20270325_02",
                "flight_number": "VN1823",
                "origin": "SGN",
                "destination": "PQC",
                "departure_time": "2027-03-25T07:10:00",
                "price": 42.0,
                "currency": "USD",
            }
        ]
    },
}
HOTELS = {
    "kind": "hotels",
    "data": {
        "hotels": [
            {
                "id": "ht-9",
                "name": "Salinda Resort",
                "star_rating": 5,
                "price_per_night": 195.0,
                "currency": "USD",
                "available": True,
            }
        ]
    },
}


@pytest.mark.parametrize(
    ("tool", "artifact", "expected"),
    [
        (
            "search_places",
            PLACES,
            [
                "- Sao Beach (attraction) → place_id pl-1",
                "- Dinh Cau Night Market (nightlife) → place_id pl-2",
            ],
        ),
        (
            "search_flights",
            FLIGHTS,
            [
                "- VN1823 SGN→PQC 2027-03-25 07:10, USD 42 → offer_id "
                "FL_SGN_PQC_20270325_02"
            ],
        ),
        (
            "search_hotels",
            HOTELS,
            ["- Salinda Resort (5★, USD 195/night, available) → hotel_id ht-9"],
        ),
    ],
)
def test_ids_are_appended_from_the_artifact(tool, artifact, expected) -> None:
    out = _ToolIdsToContent().wrap_tool_call(
        _request(tool), lambda _r: _message("summary text", artifact)
    )

    lines = out.content.splitlines()
    assert lines[0] == "summary text"
    assert lines[-len(expected) :] == expected
    # The panel payload is left as it was.
    assert out.artifact is artifact


def test_async_path_appends_ids_too() -> None:
    async def handler(_r):
        return _message("summary text", PLACES)

    out = asyncio.run(
        _ToolIdsToContent().awrap_tool_call(_request("search_places"), handler)
    )

    assert "→ place_id pl-1" in out.content


@pytest.mark.parametrize(
    "message",
    [
        _message("No places matched those filters.", None),
        _message("boom", PLACES, status="error"),
        _message("summary", {"kind": "weather", "data": {}}),
    ],
    ids=["no-artifact", "error", "other-panel"],
)
def test_other_results_pass_through_untouched(message) -> None:
    out = _ToolIdsToContent().wrap_tool_call(
        _request("search_places"), lambda _r: message
    )

    assert out is message


def test_every_subagent_binds_the_ids_middleware() -> None:
    for spec in _subagents():
        assert any(isinstance(m, _ToolIdsToContent) for m in spec["middleware"]), spec[
            "name"
        ]


def test_shared_tools_are_unchanged() -> None:
    """The fix lives in the research middleware: the chat's tools still hide ids."""
    assert search_places.response_format == "content_and_artifact"
    assert search_flights.response_format == "content_and_artifact"
