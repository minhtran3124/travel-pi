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
        "assistant_message_id": None,
        "agent_run_id": None,
        "current_flow": "booking",
        "suggestions": ["booking.bookThis"],
        "language": "en",
        "trip_id": None,
        "usage": None,
    }


def test_done_factory_empty_suggestions():
    ev = events.done(conversation_id="c1", current_flow=None, suggestions=[])
    assert _payload(ev) == {
        "conversation_id": "c1",
        "assistant_message_id": None,
        "agent_run_id": None,
        "current_flow": None,
        "suggestions": [],
        "language": "en",
        "trip_id": None,
        "usage": None,
    }


def test_done_factory_usage_key_present_and_none_by_default():
    """The ``usage`` key is ALWAYS present on the done payload, null when unknown."""
    ev = events.done(conversation_id="c1", current_flow=None, suggestions=[])
    body = _payload(ev)
    assert "usage" in body
    assert body["usage"] is None


def test_done_factory_carries_answer_identity():
    """``done`` names the persisted answer (specs/user-feedback-v1 §4.3)."""
    ev = events.done(
        conversation_id="c1",
        current_flow=None,
        suggestions=[],
        assistant_message_id="m1",
        agent_run_id="r1",
    )
    body = _payload(ev)
    assert body["assistant_message_id"] == "m1"
    assert body["agent_run_id"] == "r1"


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


def test_mapper_emits_reset_on_subagent_handoff():
    """Regression (#117): when the supervisor queues multiple sub-agents in one
    turn, the mapper must reset the accumulator on handoff so only the last
    specialist's answer survives — matching the REST "last answer wins" rule."""
    items = [
        (
            ("planner:1",),
            "messages",
            (AIMessageChunk(content="flights found", id="m1"), {}),
        ),
        (
            ("concierge:1",),
            "messages",
            (AIMessageChunk(content="sights found", id="m2"), {}),
        ),
    ]
    out = _run(_FakeGraph(items, values={"current_flow": "concierge"}))
    names = [n for n, _ in out]
    assert names == [
        "start",
        "subagent",
        "token",
        "reset",
        "subagent",
        "token",
        "done",
    ]
    # The reset must come between the two sub-agent answers.
    first_token_idx = names.index("token")
    reset_idx = names.index("reset")
    second_token_idx = names.index("token", reset_idx)
    assert first_token_idx < reset_idx < second_token_idx


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


def test_mapper_multi_intent_streams_single_synthesized_answer():
    """A two-slice multi-intent turn (planner + concierge → synthesize) emits a
    single final answer (specs/multi-intent-single-path, SC-5).

    In the single-path parallel model the specialists run as blind
    ``synthesis_worker`` subgraphs, so their prose must never reach the client;
    the top-level ``synthesize`` node is the sole source of user-facing tokens.
    The observable contract: no worker prose token, ONE synthesized answer, no
    reset, and exactly one ``done``. Because the workers stream under the
    ``synthesis_worker`` namespace root (never a specialist name), no
    ``subagent`` handoff is announced for this turn.

    **Corrected for #179.** This case previously scripted the synthesized answer
    as a single chunk arriving twice under the SAME message id, and asserted
    ``names.count("token") == 1``. That shape does not occur: every model is built
    with ``streaming=True``, so the node's answer arrives as MANY
    ``AIMessageChunk`` items sharing one id, and the duplicate the mapper must
    suppress is a separate aggregated ``AIMessage`` with a DIFFERENT id. Measured
    on a live fan-out turn: 73 chunks under one id, plus one ``AIMessage`` under
    another. The old expectation is what let the mapper ship a one-character
    reply, so the fixture now mirrors the measured stream and the assertion is on
    the reassembled answer rather than on the token count.
    """
    items = [
        # Supervisor persists the turn language (top level, no prose).
        ((), "updates", {"supervisor": {"language": "en"}}),
        # Two parallel worker slices produce prose inside the synthesis_worker
        # subgraph — both MUST be suppressed (planner slice, then concierge).
        (
            ("synthesis_worker:abc",),
            "messages",
            (AIMessageChunk(content="flights + hotel found", id="w1"), {}),
        ),
        (
            ("synthesis_worker:def",),
            "messages",
            (AIMessageChunk(content="local tips", id="w2"), {}),
        ),
        # The synthesize node combines them into the final answer, which streams
        # as chunks sharing one message id.
        (
            (),
            "messages",
            (
                AIMessageChunk(content="Here is ", id="s1"),
                {"langgraph_node": "synthesize"},
            ),
        ),
        (
            (),
            "messages",
            (
                AIMessageChunk(content="your trip.", id="s1"),
                {"langgraph_node": "synthesize"},
            ),
        ),
        # The aggregated message for the same node execution — a DIFFERENT id.
        # This is the duplicate the mapper must suppress.
        (
            (),
            "messages",
            (
                AIMessage(content="Here is your trip.", id="s1-aggregate"),
                {"langgraph_node": "synthesize"},
            ),
        ),
    ]
    out = _run(_FakeGraph(items, values={"current_flow": "synthesize"}))
    names = [n for n, _ in out]
    tokens = [data["content"] for name, data in out if name == "token"]
    # The whole answer reaches the client, and the aggregate duplicate does not
    # double it.
    assert "".join(tokens) == "Here is your trip."
    assert names.count("reset") == 0
    assert names.count("done") == 1
    assert "subagent" not in names
    # No worker prose leaked: every token came from the synthesize node.
    assert "flights + hotel found" not in "".join(tokens)
    assert "local tips" not in "".join(tokens)


# --- done.usage from a live TurnMetricsHandler (specs/agent-turn-metrics) ------


def test_mapper_done_carries_usage_from_metrics_handler():
    """Running a FakeLLM graph through ``stream_agent_events(..., metrics=handler)``
    attaches the handler's client-facing ``usage`` subset to the ``done`` event.

    ``llm_calls >= 1`` is loose on purpose: ``FakeLLM.with_structured_output``
    returns a ``RunnableLambda`` so supervisor/reflection structured calls never
    fire ``on_llm_end`` offline — only the concierge ``_generate`` reply counts.
    """
    from app.agents.graph import build_graph
    from app.agents.metrics import TurnMetricsHandler
    from app.agents.supervisor import SupervisorIntent
    from app.clients.llm import FakeLLM
    from langchain_core.messages import HumanMessage
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.store.memory import InMemoryStore

    main_llm = FakeLLM(
        structured_responses=[SupervisorIntent(target_agent="concierge")] * 4,
        responses=["Here is your travel advice."] * 4,
    )
    fast_llm = FakeLLM(responses=["OK"] * 4)
    graph = build_graph(
        llm=main_llm,
        fast_llm=fast_llm,
        checkpointer=MemorySaver(),
        store=InMemoryStore(),
    )

    handler = TurnMetricsHandler()
    cfg = {"configurable": {"thread_id": "t-metrics"}, "callbacks": [handler]}

    async def collect():
        out = []
        async for ev in stream_agent_events(
            graph,
            {"messages": [HumanMessage(content="What should I visit in Kyoto?")]},
            cfg=cfg,
            conversation_id="c1",
            metrics=handler,
        ):
            out.append((ev.event, json.loads(ev.data)))
        return out

    out = asyncio.run(collect())
    done = [d for n, d in out if n == "done"]
    assert done, "expected a done event"
    usage = done[0]["usage"]
    assert usage is not None
    assert usage["llm_calls"] >= 1
    assert {
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "cached_tokens",
        "llm_calls",
        "latency_ms",
        "cost_usd",
        "models",
    } <= usage.keys()


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
    ``error`` so the chat bubble is never empty. ``persist_assistant_turn``
    saves that fallback text under the turn's pre-minted ``assistant_message_id``
    *because* the ``error`` arrives with non-empty accumulated text (an ``error``
    with no text writes no row); the run still ends ``failed``, so the saved row
    is in history but is not rateable.
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


def test_mapper_does_not_reset_after_a_silent_plan_approval():
    """Approving a plan emits no message from the ``plan`` node, so the booking
    sub-agent's handoff must NOT emit ``reset`` (nothing to supersede) and its
    reply is the turn's only bubble text (specs/plan-approved-line-reset).
    """
    items = [
        ((), "updates", {"plan": {"plan_approved": True}}),
        (
            ("booking:abc",),
            "messages",
            (
                AIMessageChunk(content="Need passenger details.", id="m1"),
                {"langgraph_node": "agent"},
            ),
        ),
    ]
    out = _run(_FakeGraph(items))
    assert [n for n, _ in out] == ["start", "subagent", "token", "done"]
    assert out[2][1] == {"content": "Need passenger details."}


# --- HITL resume: identity on the resumed stream's `done` ---------------------


def test_stream_resume_done_carries_persisted_answer_identity(tmp_path):
    """Approve-then-resume (``kind=resume``, ``Command(resume=...)``): the
    resumed stream ends with ``done`` carrying a non-null
    ``assistant_message_id`` and the matching row exists, linked to the
    resume run (specs/user-feedback-v1 §4.3 on the HITL path).
    """
    from app.db.engine import get_session_factory
    from app.db.models import AgentRun, Message
    from fastapi.testclient import TestClient
    from test_agent_chat import _make_app, _parse_sse

    app = _make_app(tmp_path, "booking", "Hotel booked!", premium_users=["u1"])
    with TestClient(app) as client:
        first = _parse_sse(
            client.post(
                "/agent/stream",
                json={"message": "book me a hotel in Paris", "user_id": "u1"},
            ).text
        )
        intr = next(e for e in first if e.get("event") == "interrupt")
        conv_id = json.loads(intr["data"])["conversation_id"]
        first_done = next(
            json.loads(e["data"]) for e in first if e.get("event") == "done"
        )
        assert first_done["assistant_message_id"] is None  # interrupt turn

        resumed = _parse_sse(
            client.post(
                "/agent/stream",
                json={
                    "user_id": "u1",
                    "conversation_id": conv_id,
                    "resume": {"approved": True},
                },
            ).text
        )
    assert "interrupt" not in [e.get("event") for e in resumed]
    done = next(json.loads(e["data"]) for e in resumed if e.get("event") == "done")
    assert done["assistant_message_id"]
    assert done["agent_run_id"]
    assert done["agent_run_id"] != first_done["agent_run_id"]

    s = get_session_factory(f"sqlite:///{tmp_path / 'agent_api.db'}")()
    try:
        row = s.get(Message, done["assistant_message_id"])
        assert row is not None
        assert row.conversation_id == conv_id
        assert row.role == "assistant"
        assert "Hotel booked" in row.content
        assert row.agent_run_id == done["agent_run_id"]
        run = s.get(AgentRun, done["agent_run_id"])
        assert run is not None
        assert run.kind == "resume"
        assert run.status == "completed"
    finally:
        s.close()
