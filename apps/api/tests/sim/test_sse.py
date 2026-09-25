"""Tests for the SSE stream client (offline; httpx.MockTransport)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
from sim.sse import HttpStatusError, SseEvent, parse, stream_turn, to_ui_events

FIXTURE = Path(__file__).parent / "fixtures" / "stream_all_events.txt"

EXPECTED_NAMES = [
    "start",
    "subagent",
    "tool_call",
    "tool_result",
    "panel",
    "token",
    "reset",
    "token",
    "interrupt",
    "done",
    "error",
]


def _fixture_events() -> list[SseEvent]:
    return list(parse(FIXTURE.read_text().splitlines()))


def test_parse_yields_the_full_event_sequence():
    events = _fixture_events()
    assert [ev.name for ev in events] == EXPECTED_NAMES
    tool_call = next(ev for ev in events if ev.name == "tool_call")
    assert tool_call.data["name"] == "search_flights"
    reset = next(ev for ev in events if ev.name == "reset")
    assert reset.data == {}


def test_to_ui_events_maps_interrupt_to_bot_interrupt():
    interrupt = next(ev for ev in _fixture_events() if ev.name == "interrupt")
    ui = to_ui_events("p1", interrupt)
    assert ui == [
        {"type": "bot_interrupt", "persona_id": "p1", "kind": "plan_approval"}
    ]


def test_to_ui_events_maps_the_fixture_in_order():
    # Map every fixture event in order and flatten, so both `token` events
    # (before and after `reset`) are asserted in sequence.
    ui = [u for ev in _fixture_events() for u in to_ui_events("p1", ev)]
    assert ui == [
        {"type": "bot_subagent", "persona_id": "p1", "name": "planner"},
        {
            "type": "bot_tool",
            "persona_id": "p1",
            "name": "search_flights",
            "status": "running",
            "id": "call-1",
        },
        {"type": "bot_tool", "persona_id": "p1", "status": "ok", "id": "call-1"},
        {"type": "bot_token", "persona_id": "p1", "text": "Here "},
        {
            "type": "bot_token",
            "persona_id": "p1",
            "text": "Here are your flight options.",
        },
        {"type": "bot_interrupt", "persona_id": "p1", "kind": "plan_approval"},
        {"type": "bot_done", "persona_id": "p1", "usage": {"total_tokens": 42}},
        {
            "type": "bot_error",
            "persona_id": "p1",
            "code": "internal",
            "message": "boom",
        },
    ]


def test_to_ui_events_ignores_non_ui_events():
    # start, panel, and reset carry no lobby animation.
    events = {ev.name: ev for ev in _fixture_events()}
    assert to_ui_events("p1", events["start"]) == []
    assert to_ui_events("p1", events["panel"]) == []
    assert to_ui_events("p1", events["reset"]) == []


def _run_stream(handler, token="tok"):
    async def _go():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return [
                ev
                async for ev in stream_turn(
                    client,
                    "http://api-sim:8001",
                    token,
                    {"message": "hi"},
                )
            ]

    return asyncio.run(_go())


def test_stream_turn_parses_the_stream_and_sends_bearer():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            content=FIXTURE.read_bytes(),
            headers={"content-type": "text/event-stream"},
        )

    events = _run_stream(handler)
    assert [ev.name for ev in events] == EXPECTED_NAMES
    assert seen["auth"] == "Bearer tok"
    assert seen["url"].endswith("/agent/stream")


@pytest.mark.parametrize("status", [401, 429])
def test_stream_turn_raises_on_non_200(status):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"detail": "no"})

    with pytest.raises(HttpStatusError) as exc:
        _run_stream(handler)
    assert exc.value.status == status
