"""Typed agent SSE protocol — event factories + stream mapper.

Covers app.streaming.events (JSON shapes) and app.streaming.mapper (ordered
emission from a scripted ``astream``, tool dedup, reset, interrupt).
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from app.schemas.air_quality import AirQualityDay, AirQualityResponse
from app.schemas.route import RouteEndpoint, RouteLeg, RouteResponse
from app.schemas.weather import (
    CurrentWeather,
    DailyForecast,
    WeatherLocation,
    WeatherResponse,
)
from app.streaming import events
from app.streaming.mapper import stream_agent_events
from app.streaming.panels import AirQualityPanel, RoutePanel, WeatherPanel
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

# --- event factories -------------------------------------------------------


def _payload(ev):
    return json.loads(ev.data)


def test_token_factory_shape():
    ev = events.token("Your trip")
    assert ev.event == "token"
    assert _payload(ev) == {"content": "Your trip"}


def test_tool_call_truncates_args_preview():
    ev = events.tool_call(
        id="tc1", name="search_flights", args={"note": "x" * 500}, subagent="booking"
    )
    body = _payload(ev)
    assert ev.event == "tool_call"
    assert body["id"] == "tc1"
    assert body["name"] == "search_flights"
    assert body["subagent"] == "booking"
    assert body["args_preview"].endswith("…")
    assert len(body["args_preview"]) <= events.ARGS_PREVIEW_LIMIT + 1


def test_done_factory_shape():
    ev = events.done(
        conversation_id="c1", current_flow="booking", suggestions=["booking.bookThis"]
    )
    assert ev.event == "done"
    assert _payload(ev) == {
        "conversation_id": "c1",
        "current_flow": "booking",
        "suggestions": ["booking.bookThis"],
        "language": "en",
        "trip_id": None,
    }


def test_done_factory_empty_suggestions():
    ev = events.done(conversation_id="c1", current_flow=None, suggestions=[])
    assert _payload(ev) == {
        "conversation_id": "c1",
        "current_flow": None,
        "suggestions": [],
        "language": "en",
        "trip_id": None,
    }


def test_done_factory_carries_trip_id():
    ev = events.done(
        conversation_id="c1", current_flow=None, suggestions=[], trip_id="trip-1"
    )
    assert _payload(ev)["trip_id"] == "trip-1"


# --- mapper ----------------------------------------------------------------


class _FakeGraph:
    """A graph whose astream replays scripted (ns, mode, data) tuples.

    ``raise_after``/``exc`` simulate a crashed run: the graph yields the first
    ``raise_after`` items, then raises ``exc`` (or raises immediately when
    ``raise_after == 0``). Used to exercise the stream's fallback-message path.
    """

    def __init__(
        self, items, *, interrupts=(), values=None, raise_after=None, exc=None
    ):
        self._items = items
        self._interrupts = interrupts
        self._values = values or {}
        self._raise_after = raise_after
        self._exc = exc

    async def astream(self, stream_input, cfg, *, stream_mode, subgraphs, context=None):
        if self._raise_after is not None and self._raise_after == 0:
            raise self._exc
        for i, item in enumerate(self._items):
            yield item
            if self._raise_after is not None and i + 1 == self._raise_after:
                raise self._exc

    async def aget_state(self, cfg):
        return SimpleNamespace(interrupts=self._interrupts, values=self._values)


def _run(graph):
    async def collect():
        out = []
        async for ev in stream_agent_events(
            graph, {"messages": []}, cfg={}, conversation_id="c1"
        ):
            out.append((ev.event, json.loads(ev.data)))
        return out

    return asyncio.run(collect())


def test_mapper_emits_ordered_protocol():
    ns = ("planner:1",)
    ai_tc = AIMessageChunk(
        content="",
        tool_calls=[{"id": "tc1", "name": "search_flights", "args": {"city": "Paris"}}],
    )
    items = [
        (ns, "updates", {"agent": {"messages": [ai_tc]}}),
        (ns, "messages", (AIMessageChunk(content="Your", id="m1"), {})),
        (ns, "messages", (AIMessageChunk(content=" trip", id="m1"), {})),
        (
            ns,
            "updates",
            {
                "tools": {
                    "messages": [
                        ToolMessage(content="ok", tool_call_id="tc1", status="success")
                    ]
                }
            },
        ),
    ]
    out = _run(_FakeGraph(items, values={"current_flow": "planner"}))
    names = [name for name, _ in out]
    assert names == [
        "start",
        "subagent",
        "tool_call",
        "token",
        "token",
        "tool_result",
        "done",
    ]
    assert out[1][1] == {"name": "planner"}
    assert out[2][1]["id"] == "tc1"
    assert out[3][1] == {"content": "Your"}
    assert out[5][1] == {"id": "tc1", "status": "ok"}
    assert out[6][1]["current_flow"] == "planner"
    # done carries flow-prefixed follow-up suggestion keys for a known flow.
    suggestions = out[6][1]["suggestions"]
    assert isinstance(suggestions, list) and suggestions
    assert all(s.startswith("planner.") for s in suggestions)


def test_mapper_dedupes_tool_calls():
    ns = ("booking:1",)
    tc = {"id": "dup", "name": "book_hotel", "args": {}}
    items = [
        (
            ns,
            "updates",
            {"agent": {"messages": [AIMessageChunk(content="", tool_calls=[tc])]}},
        ),
        (
            ns,
            "updates",
            {"agent": {"messages": [AIMessageChunk(content="", tool_calls=[tc])]}},
        ),
    ]
    out = _run(_FakeGraph(items))
    assert [n for n, _ in out].count("tool_call") == 1


def test_mapper_emits_reset_on_new_message_id():
    ns = ("planner:1",)
    items = [
        (ns, "messages", (AIMessageChunk(content="draft", id="m1"), {})),
        (ns, "messages", (AIMessageChunk(content="final", id="m2"), {})),
    ]
    out = _run(_FakeGraph(items))
    names = [n for n, _ in out]
    assert names == ["start", "subagent", "token", "reset", "token", "done"]


def test_mapper_emits_interrupt_before_done():
    snapshot_interrupt = SimpleNamespace(value={"plan": "approve?"})
    out = _run(_FakeGraph([], interrupts=(snapshot_interrupt,)))
    names = [n for n, _ in out]
    assert names == ["start", "interrupt", "done"]
    assert out[1][1] == {"conversation_id": "c1", "payload": {"plan": "approve?"}}
    # A pending interrupt suppresses suggestions (the turn isn't complete).
    assert out[2][1]["suggestions"] == []


def test_mapper_suppresses_non_subagent_tokens():
    # Top-level nodes (supervisor/summarize) must not leak tokens.
    items = [
        (("supervisor",), "messages", (AIMessageChunk(content="route", id="s1"), {}))
    ]
    out = _run(_FakeGraph(items))
    assert [n for n, _ in out] == ["start", "done"]


# --- terminal supervisor/plan messages (specs/agent-flight-routing-stream-gate) ---


def test_mapper_emits_token_for_terminal_supervisor_message():
    """A tier-gate / unknown-intent turn ends at the main-graph ``supervisor``
    node with a content AIMessage (no tool_calls). It never streams via the
    ``messages`` mode (only sub-agent prose does), so the mapper must surface it
    as a ``token`` so the chat bubble is never blank.
    """
    from app.agents.constants import BOOKING_UPGRADE_MSG

    items = [
        (
            (),
            "updates",
            {"supervisor": {"messages": [AIMessage(content=BOOKING_UPGRADE_MSG)]}},
        )
    ]
    out = _run(_FakeGraph(items))
    names = [n for n, _ in out]
    assert names == ["start", "token", "done"]
    assert out[1][1] == {"content": BOOKING_UPGRADE_MSG}


def test_mapper_emits_token_for_plan_node_message():
    """A plan-node cancel/approve ends the turn at the main-graph ``plan`` node
    with a content AIMessage; surface it as a token so the bubble isn't blank.
    """
    items = [
        (
            (),
            "updates",
            {
                "plan": {
                    "messages": [AIMessage(content="Booking cancelled as requested.")]
                }
            },
        )
    ]
    out = _run(_FakeGraph(items))
    names = [n for n, _ in out]
    assert names == ["start", "token", "done"]
    assert out[1][1] == {"content": "Booking cancelled as requested."}


def test_mapper_does_not_double_emit_subagent_updates_content():
    """Sub-agent assistant prose already streams via the ``messages`` mode, so a
    content AIMessage arriving on a sub-agent's ``agent`` node update must NOT be
    re-emitted as a token — the terminal-text-node gate is keyed on the main-graph
    node name (``supervisor``/``plan``), not the sub-agent's internal node names.
    """
    ns = ("planner:1",)
    items = [
        (ns, "updates", {"agent": {"messages": [AIMessage(content="planner reply")]}}),
    ]
    out = _run(_FakeGraph(items))
    assert [n for n, _ in out] == ["start", "subagent", "done"]


# --- panels (specs/agent-side-panel) ---------------------------------------


def _route_response() -> RouteResponse:
    return RouteResponse(
        origin=RouteEndpoint(
            kind="place", id="A", name="Hotel", latitude=16.06, longitude=108.22
        ),
        destination=RouteEndpoint(
            kind="place", id="B", name="Dragon Bridge", latitude=16.07, longitude=108.23
        ),
        straight_line_km=1.9,
        recommended_mode="car",
        legs=[
            RouteLeg(
                mode="car", profile="driving-car", distance_km=2.4, duration_minutes=7.0
            )
        ],
        source="openrouteservice",
        geometry=[[108.22, 16.06], [108.23, 16.07]],
        attribution="© ORS",
    )


def test_panel_factory_shape():
    ev = events.panel(tool_call_id="tc1", kind="route", data={"x": 1})
    assert ev.event == "panel"
    assert _payload(ev) == {
        "tool_call_id": "tc1",
        "kind": "route",
        "data": {"x": 1},
        "language": "en",
    }


def test_route_panel_projection():
    panel = RoutePanel.from_route_response(_route_response())
    assert panel.origin.name == "Hotel"
    assert panel.origin.lat == 16.06 and panel.origin.lng == 108.22
    assert panel.recommended_mode == "car"
    assert panel.geometry == [[108.22, 16.06], [108.23, 16.07]]
    assert panel.gmaps_url == (
        "https://www.google.com/maps/dir/?api=1"
        "&origin=16.06,108.22&destination=16.07,108.23"
    )


def _weather_response() -> WeatherResponse:
    return WeatherResponse(
        location=WeatherLocation(
            name="Da Nang",
            country="Vietnam",
            latitude=16.06,
            longitude=108.22,
            timezone="Asia/Ho_Chi_Minh",
        ),
        current=CurrentWeather(
            time="2026-06-30T00:00",
            temperature_c=28.4,
            apparent_temperature_c=36.1,
            relative_humidity=95,
            wind_speed_kmh=5.2,
            weather_code=95,
            description="Thunderstorm",
        ),
        daily=[
            DailyForecast(
                date="2026-06-30",
                temp_min_c=28.0,
                temp_max_c=34.0,
                precipitation_probability_max=92,
                weather_code=99,
                description="Thunderstorm with heavy hail",
            )
        ],
    )


def test_weather_panel_projection():
    panel = WeatherPanel.from_weather_response(_weather_response())
    assert panel.location_name == "Da Nang"
    assert panel.country == "Vietnam"
    assert panel.timezone == "Asia/Ho_Chi_Minh"
    # current: emoji + sky-mood bucket derived from the WMO code (95 → storm)
    assert panel.current.condition == "storm"
    assert panel.current.emoji == "⛈️"
    assert panel.current.apparent_temperature_c == 36.1
    # daily: code 99 → storm, precip carried through
    assert panel.daily[0].condition == "storm"
    assert panel.daily[0].precipitation_probability_max == 92


def _air_quality_response() -> AirQualityResponse:
    return AirQualityResponse(
        location=WeatherLocation(
            name="Hanoi",
            country="Vietnam",
            latitude=21.03,
            longitude=105.85,
            timezone="Asia/Bangkok",
        ),
        time="2026-06-30T14:00",
        us_aqi=120,
        category="Unhealthy for Sensitive Groups",
        pm2_5=42.3,
        pm10=70.1,
        ozone=None,
        attribution="Air quality data by Open-Meteo.com (CC BY 4.0)",
        forecast=[
            AirQualityDay(
                date="2026-06-30",
                max_us_aqi=120,
                category="Unhealthy for Sensitive Groups",
            ),
            AirQualityDay(date="2026-07-01", max_us_aqi=None, category="Unknown"),
        ],
    )


def test_air_quality_panel_projection():
    panel = AirQualityPanel.from_air_quality_response(_air_quality_response())
    assert panel.location_name == "Hanoi"
    assert panel.us_aqi == 120
    # category → band + emoji + advice pre-computed on the BE
    assert panel.band == "usg"
    assert panel.emoji == "😷"
    assert "Sensitive groups" in panel.advice
    # all six pollutants projected, in order, nulls preserved
    assert [p.label for p in panel.pollutants] == [
        "PM2.5",
        "PM10",
        "Ozone",
        "NO₂",
        "SO₂",
        "CO",
    ]
    assert panel.pollutants[2].value is None  # ozone unavailable
    # forecast: unknown band falls back, null AQI carried through
    assert panel.forecast[1].band == "unknown"
    assert panel.forecast[1].max_us_aqi is None


def test_mapper_emits_panel_before_tool_result():
    ns = ("concierge:1",)
    tm = ToolMessage(
        content="Hotel → Dragon Bridge: 2.4 km, ~7 min by car.",
        tool_call_id="tc1",
        status="success",
        artifact={"kind": "route", "data": {"recommended_mode": "car"}},
    )
    items = [(ns, "updates", {"tools": {"messages": [tm]}})]
    out = _run(_FakeGraph(items))
    names = [n for n, _ in out]
    assert names == ["start", "subagent", "panel", "tool_result", "done"]
    assert out[2][1] == {
        "tool_call_id": "tc1",
        "kind": "route",
        "data": {"recommended_mode": "car"},
        "language": "en",
    }


def test_mapper_no_panel_for_plain_tool():
    ns = ("planner:1",)
    tm = ToolMessage(content="ok", tool_call_id="tc9", status="success")
    items = [(ns, "updates", {"tools": {"messages": [tm]}})]
    out = _run(_FakeGraph(items))
    assert "panel" not in [n for n, _ in out]


# --- fallback message on failure (tool/LLM/recursion errors) ---------------


def test_mapper_emits_fallback_message_when_stream_fails_with_no_tokens():
    """A crashed run that produced no assistant token must still return a
    readable fallback message to the user, not just a bare error event.

    Regression for "when the tool call failed, we can not return message to end
    user": the stream now emits a friendly ``token`` before the terminal
    ``error`` so the chat bubble is never empty and the turn is persisted.
    """
    from app.agents.constants import AGENT_ERROR_FALLBACK_MSG

    graph = _FakeGraph([], raise_after=0, exc=RuntimeError("upstream blew up"))
    out = _run(graph)
    names = [n for n, _ in out]
    assert names == ["start", "token", "error"]
    assert out[1][1] == {"content": AGENT_ERROR_FALLBACK_MSG}
    assert out[2][1]["code"] == "internal"


def test_mapper_no_duplicate_fallback_when_tokens_already_streamed():
    """If a partial answer was already streamed, don't append a second fallback
    token — the user already has a message; just signal the terminal error."""
    from app.agents.constants import AGENT_ERROR_FALLBACK_MSG

    ns = ("planner:1",)
    items = [(ns, "messages", (AIMessageChunk(content="partial answer", id="m1"), {}))]
    graph = _FakeGraph(items, raise_after=1, exc=RuntimeError("kaboom"))
    out = _run(graph)
    names = [n for n, _ in out]
    assert names == ["start", "subagent", "token", "error"]
    assert out[2][1] == {"content": "partial answer"}
    # The fallback must NOT have been emitted alongside the partial answer.
    assert AGENT_ERROR_FALLBACK_MSG not in json.dumps([d for _, d in out])
