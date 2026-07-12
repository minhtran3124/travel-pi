"""``panel_result`` registry-backed validation (specs/streaming-panels-split Task 2.2)."""

import pytest
from app.streaming.panels import panel_kinds
from app.tools._base import panel_result

# The kinds the real tools emit, one per panel-emitting tool module. Read from
# app/tools/{weather,flight,hotel,place,routing}_tools.py — if a tool starts
# emitting a different kind, or a panel module registers without a tool (or
# vice versa), this literal set drifts from panel_kinds() and this test fails.
REAL_TOOL_PANEL_KINDS = {
    "weather",  # weather_tools.get_weather
    "air_quality",  # weather_tools.get_air_quality
    "flights",  # flight_tools.search_flights
    "hotels",  # hotel_tools.browse_hotels / search_hotels
    "places",  # place_tools.search_places
    "route",  # routing_tools.get_route
}


@pytest.mark.parametrize("kind", panel_kinds())
def test_panel_result_round_trips_registered_kind(kind):
    summary, artifact = panel_result("s", kind=kind, data={})
    assert summary == "s"
    assert artifact == {"kind": kind, "data": {}}


def test_panel_result_rejects_unregistered_kind():
    with pytest.raises(ValueError, match="unknown panel kind"):
        panel_result("s", kind="not_a_real_kind", data={})


def test_real_tool_kinds_match_registry():
    """Drift guard: every kind a tool emits must be registered, and vice versa.

    If this fails, one side drifted from the other: either a tool started
    emitting a kind with no panel module registered for it (an unrenderable
    panel would ship to the FE), or a panel module was added/removed without
    updating REAL_TOOL_PANEL_KINDS above to match the tools that use it.
    """
    registered = set(panel_kinds())
    assert registered == REAL_TOOL_PANEL_KINDS, (
        f"kinds only in REAL_TOOL_PANEL_KINDS (tool emits, no panel registered): "
        f"{REAL_TOOL_PANEL_KINDS - registered}; "
        f"kinds only in panel_kinds() (panel registered, no tool emits it): "
        f"{registered - REAL_TOOL_PANEL_KINDS}"
    )
