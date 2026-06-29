"""Typed agent SSE protocol — event factories + stream mapper.

Covers app.streaming.events (JSON shapes) and app.streaming.mapper (ordered
emission from a scripted ``astream``, tool dedup, reset, interrupt).
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from app.schemas.route import RouteEndpoint, RouteLeg, RouteResponse
from app.streaming import events
from app.streaming.mapper import stream_agent_events
from app.streaming.panels import RoutePanel
from langchain_core.messages import AIMessageChunk, ToolMessage

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
    ev = events.done(conversation_id="c1", current_flow="booking")
    assert ev.event == "done"
    assert _payload(ev) == {"conversation_id": "c1", "current_flow": "booking"}


# --- mapper ----------------------------------------------------------------


class _FakeGraph:
    """A graph whose astream replays scripted (ns, mode, data) tuples."""

    def __init__(self, items, *, interrupts=(), values=None):
        self._items = items
        self._interrupts = interrupts
        self._values = values or {}

    async def astream(self, stream_input, cfg, *, stream_mode, subgraphs, context=None):
        for item in self._items:
            yield item

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


def test_mapper_suppresses_non_subagent_tokens():
    # Top-level nodes (supervisor/summarize) must not leak tokens.
    items = [
        (("supervisor",), "messages", (AIMessageChunk(content="route", id="s1"), {}))
    ]
    out = _run(_FakeGraph(items))
    assert [n for n, _ in out] == ["start", "done"]


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
    assert _payload(ev) == {"tool_call_id": "tc1", "kind": "route", "data": {"x": 1}}


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
    }


def test_mapper_no_panel_for_plain_tool():
    ns = ("planner:1",)
    tm = ToolMessage(content="ok", tool_call_id="tc9", status="success")
    items = [(ns, "updates", {"tools": {"messages": [tm]}})]
    out = _run(_FakeGraph(items))
    assert "panel" not in [n for n, _ in out]
