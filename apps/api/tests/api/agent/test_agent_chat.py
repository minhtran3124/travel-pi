"""Agent API: /agent/chat, /agent/stream, /agent/manifest (Task 6.1).

Includes HITL stream tests (feat/agent-stream-hitl):
- test_stream_booking_emits_interrupt_event
- test_stream_booking_resume_approved
- test_stream_booking_resume_rejected
"""

import json

import pytest
from app.agents.graph import build_graph
from app.agents.supervisor import SupervisorIntent
from app.clients.llm import FakeLLM
from app.core.auth import AuthUser, get_current_user_optional
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.session import get_session
from app.main import create_app
from app.routers.agent import get_travel_graph
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_app(
    tmp_path,
    intent_target: str,
    answer: str,
    *,
    responses=None,
    fast_responses=None,
    premium_users: list[str] | None = None,
):
    from app.repositories.user import UserRepository

    url = f"sqlite:///{tmp_path / 'agent_api.db'}"
    Base.metadata.create_all(get_engine(url), checkfirst=True)

    # Seed any users that need premium tier before the app handles requests.
    if premium_users:
        s = get_session_factory(url)()
        try:
            for uid in premium_users:
                UserRepository(s).upsert_tier(uid, "premium")
            s.commit()
        finally:
            s.close()

    app = create_app()

    def _override_session():
        s = get_session_factory(url)()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    # Build the graph ONCE per app instance so the MemorySaver checkpointer
    # survives across requests within a test. Per-request rebuild loses checkpoint
    # state and breaks HITL resume (second request gets a fresh graph with no
    # interrupt checkpoint, so plan_node fires again instead of resuming).
    main = FakeLLM(
        structured_responses=[SupervisorIntent(target_agent=intent_target)] * 6,
        responses=responses if responses is not None else [answer] * 6,
    )
    fast = FakeLLM(
        responses=fast_responses if fast_responses is not None else ["OK"] * 6
    )
    _graph = build_graph(
        llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=InMemoryStore()
    )

    def _override_graph():
        return _graph

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_travel_graph] = _override_graph
    # Test-only introspection hook: lets tests reach the same store/llm the
    # request handler sees. Deliberately NOT named `app.state.travel_graph` —
    # the real lifespan (app/core/lifespan.py) sets that attribute on startup
    # with a production (Postgres-backed) graph, which would clobber this one
    # once `TestClient(app)` triggers the ASGI startup event.
    app.state.test_graph = _graph

    # Premium requires authentication (hybrid identity — anonymous is always free).
    # Simulate being logged in as the first premium user so tier resolves correctly.
    if premium_users:
        _puid = premium_users[0]
        app.dependency_overrides[get_current_user_optional] = lambda: AuthUser(
            id=_puid, email=None, role=None, claims={}
        )

    return app


@pytest.fixture
def client(tmp_path):
    app = _make_app(tmp_path, "concierge", "Visit Tokyo Tower at sunset.")
    with TestClient(app) as c:
        yield c


@pytest.fixture
def booking_client(tmp_path):
    # D.1: booking is premium-only; seed "u1" as premium so HITL tests still pass.
    app = _make_app(tmp_path, "booking", "Hotel booked!", premium_users=["u1"])
    with TestClient(app) as c:
        yield c


@pytest.fixture
def planner_client(tmp_path):
    # Hotel/flight *search* (not booking) routes to the planner sub-agent, which
    # owns the trip/flight/hotel tools. planner is free-tier and non-interrupting,
    # so the turn completes and returns follow-up suggestions.
    app = _make_app(tmp_path, "planner", "Here are some options for your trip.")
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_sse(text: str) -> list[dict]:
    """Parse raw SSE text into a list of {event?, data} dicts.

    SSE event blocks are separated by blank lines (double newline).
    """
    events = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        current: dict[str, str] = {}
        for line in block.splitlines():
            if line.startswith("event:"):
                current["event"] = line[6:].strip()
            elif line.startswith("data:"):
                current["data"] = line[5:].strip()
        if current:
            events.append(current)
    return events


# ---------------------------------------------------------------------------
# Existing tests (non-booking, regression guards)
# ---------------------------------------------------------------------------


def test_chat_returns_reply_and_persists(client):
    resp = client.post(
        "/agent/chat",
        json={"message": "What should I see in Tokyo?", "user_id": "u1"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "Tokyo Tower" in body["reply"]
    assert body["current_flow"] == "concierge"
    assert body["conversation_id"]

    # continuing the same conversation persists more messages
    resp2 = client.post(
        "/agent/chat",
        json={
            "message": "and the food?",
            "user_id": "u1",
            "conversation_id": body["conversation_id"],
        },
    )
    assert resp2.status_code == 200
    assert resp2.json()["conversation_id"] == body["conversation_id"]


def test_chat_multi_intent_turn_returns_both_subagent_answers(tmp_path):
    """Regression (ce-code-review finding): a multi-intent turn (MIN-65
    dispatch_next) must not silently drop the first sub-agent's answer from
    the non-streaming REST reply — both answers must be present."""
    url = f"sqlite:///{tmp_path / 'agent_api.db'}"
    Base.metadata.create_all(get_engine(url), checkfirst=True)

    app = create_app()

    def _override_session():
        s = get_session_factory(url)()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    main = FakeLLM(
        structured_responses=[
            SupervisorIntent(target_agent="planner", secondary_agent="concierge")
        ]
        * 6,
        responses=["flights found", "here's what to see"] * 3,
    )
    fast = FakeLLM(responses=["OK"] * 6)
    graph = build_graph(
        llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=InMemoryStore()
    )

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_travel_graph] = lambda: graph
    app.state.test_graph = graph

    with TestClient(app) as c:
        resp = c.post(
            "/agent/chat",
            json={
                "message": "flights to Tokyo and things to do there",
                "user_id": "u1",
            },
        )
    assert resp.status_code == 200
    reply = resp.json()["reply"]
    assert "flights found" in reply
    assert "here's what to see" in reply


def test_chat_returns_flow_scoped_suggestions(client):
    """A completed turn returns a `suggestions` list of keys prefixed by the flow.

    The `client` fixture routes to `concierge`, so every suggestion key must start
    with `concierge.` and the list must be non-empty (MIN-55, Task 2.1).
    """
    resp = client.post(
        "/agent/chat",
        json={"message": "What should I see in Tokyo?", "user_id": "u1"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["current_flow"] == "concierge"
    suggestions = body["suggestions"]
    assert isinstance(suggestions, list)
    assert suggestions  # non-empty for a known flow
    assert all(s.startswith("concierge.") for s in suggestions)


def test_chat_returns_no_suggestions_when_interrupt_pending(booking_client):
    """An interrupt-pending turn yields an empty `suggestions` list — no chips
    surface while the user is being asked to approve a plan.
    """
    resp = booking_client.post(
        "/agent/chat",
        json={"message": "book me a hotel in Paris", "user_id": "u1"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["interrupt_pending"] is True
    assert body["suggestions"] == []


def test_chat_response_suggestions_match_flow_map():
    """Focused unit check: ChatResponse carries the flow-scoped keys verbatim."""
    from app.agents.suggestions import suggestions_for_flow
    from app.schemas.agent import ChatResponse

    resp = ChatResponse(
        conversation_id="c",
        reply="r",
        suggestions=suggestions_for_flow("booking"),
    )
    assert resp.suggestions == [
        "booking.otherOptions",
        "booking.bookThis",
        "booking.comparePrices",
    ]


def test_chat_hotel_search_returns_flow_scoped_suggestions(planner_client):
    """MIN-55 e2e — a literal hotel-search message drives the full
    message→route→flow→suggestions path. Flow-agnostic: the assertion couples the
    suggestion keys to whatever flow the router actually picked, so it holds no
    matter which sub-agent handles the search.
    """
    resp = planner_client.post(
        "/agent/chat",
        json={"message": "Find me a cheap hotel in Da Nang", "user_id": "u1"},
    )
    assert resp.status_code == 200
    body = resp.json()
    flow = body["current_flow"]
    assert flow  # non-null known flow
    suggestions = body["suggestions"]
    assert isinstance(suggestions, list)
    assert suggestions  # non-empty for a known flow
    assert all(s.startswith(flow + ".") for s in suggestions)


def test_chat_flight_search_returns_flow_scoped_suggestions(planner_client):
    """MIN-55 e2e — a literal flight-search message drives the full
    message→route→flow→suggestions path. Same flow-agnostic assertion as the
    hotel case: suggestion keys must be scoped to the flow the router chose.
    """
    resp = planner_client.post(
        "/agent/chat",
        json={"message": "Find flights to Tokyo next month", "user_id": "u1"},
    )
    assert resp.status_code == 200
    body = resp.json()
    flow = body["current_flow"]
    assert flow  # non-null known flow
    suggestions = body["suggestions"]
    assert isinstance(suggestions, list)
    assert suggestions  # non-empty for a known flow
    assert all(s.startswith(flow + ".") for s in suggestions)


def test_stream_emits_sse_events(client):
    resp = client.post(
        "/agent/stream",
        json={"message": "hi", "user_id": "u1"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    text = resp.text
    assert "data:" in text
    assert "event: done" in text
    # The concierge answer streams; the reflection critic's verdict ("OK", scripted
    # in the fixture's fast LLM) must NOT leak into the SSE feed (REVIEW.md C4).
    assert "Visit Tokyo Tower" in text
    assert "OK" not in text
    # Non-booking flow must NOT emit an interrupt event.
    assert "event: interrupt" not in text


def test_stream_emits_reset_on_revised_answer(tmp_path):
    """When reflection revises (re-runs the sub-agent), a `reset` event must
    separate the superseded draft from the final answer so the FE can drop it.

    fast LLM says REVISE once (then OK), so the concierge answers twice with two
    distinct message ids; the stream must carry exactly one `event: reset`.
    """
    app = _make_app(
        tmp_path,
        "concierge",
        "unused",
        responses=[
            AIMessage(content="DRAFT answer", id="m1"),
            AIMessage(content="FINAL answer", id="m2"),
        ],
        fast_responses=["REVISE", "OK"],
    )
    with TestClient(app) as c:
        resp = c.post("/agent/stream", json={"message": "weather?", "user_id": "u1"})
    text = resp.text
    assert "DRAFT answer" in text
    assert "FINAL answer" in text
    assert text.count("event: reset") == 1
    # The reset must come between the draft and the final answer.
    assert text.index("DRAFT") < text.index("event: reset") < text.index("FINAL")


def test_chat_reply_excludes_reflection_rejected_draft(tmp_path):
    """Regression (ce-code-review P1): when reflection REVISEs, the graph keeps
    both the superseded draft and the revised answer in state (add_messages
    appends; nothing removes the draft). The non-streaming REST reply must
    return ONLY the final answer — not the rejected draft glued to it — mirroring
    the SSE path's `reset`. Same fixture as the SSE reset test, asserted on the
    /agent/chat JSON reply instead of the stream."""
    app = _make_app(
        tmp_path,
        "concierge",
        "unused",
        responses=[
            AIMessage(content="DRAFT answer", id="m1"),
            AIMessage(content="FINAL answer", id="m2"),
        ],
        fast_responses=["REVISE", "OK"],
    )
    with TestClient(app) as c:
        resp = c.post("/agent/chat", json={"message": "weather?", "user_id": "u1"})
    assert resp.status_code == 200
    reply = resp.json()["reply"]
    assert "FINAL answer" in reply
    assert "DRAFT answer" not in reply


def test_stream_drops_tool_json_output(tmp_path, monkeypatch):
    """Structured weather data must ride the `panel` channel, never the NL tokens.

    Regression for the "chatbot shows json/dict" bug: a sub-agent's ToolNode runs
    inside the same `langgraph_node` as its assistant, so the tool's JSON result
    rode through the node filter into the stream. Now get_weather is panel-capable
    (specs/agent-side-panel): its structured payload reaches the FE via an
    `event: panel`, and the user-facing reply is the natural-language answer once.
    The marker (carried in the weather data) must show up in a `panel` event but
    never in a `token` event.
    """
    from app.schemas.weather import CurrentWeather, WeatherLocation, WeatherResponse
    from app.services import weather_service

    marker = "WEATHER_JSON_LEAK_MARKER"

    async def _fake_get_weather(city, days=None):
        return WeatherResponse(
            location=WeatherLocation(
                name=city, latitude=-8.4, longitude=115.2, timezone="Asia/Makassar"
            ),
            current=CurrentWeather(
                time="2026-06-30T00:00",
                temperature_c=30.0,
                apparent_temperature_c=33.0,
                relative_humidity=80,
                wind_speed_kmh=6.0,
                weather_code=0,
                description=marker,
            ),
            daily=[],
        )

    monkeypatch.setattr(weather_service, "get_weather", _fake_get_weather)

    tool_call = AIMessage(
        content="",
        tool_calls=[{"name": "get_weather", "args": {"city": "Bali"}, "id": "c1"}],
    )
    app = _make_app(
        tmp_path,
        "concierge",
        answer="",
        responses=[tool_call, "Sunny and warm in Bali."],
    )
    with TestClient(app) as c:
        resp = c.post(
            "/agent/stream",
            json={"message": "weather in Bali?", "user_id": "u1"},
        )

    assert resp.status_code == 200
    text = resp.text
    blocks = text.split("\n\n")
    token_blocks = [b for b in blocks if "event: token" in b]
    panel_blocks = [b for b in blocks if "event: panel" in b]
    assert all(marker not in b for b in token_blocks)  # not in the NL answer tokens
    assert any(marker in b for b in panel_blocks)  # rode the side-panel channel
    assert text.count("Sunny and warm in Bali.") == 1  # answer once, not duplicated


def test_stream_survives_tool_upstream_failure(tmp_path, monkeypatch):
    """A tool's upstream outage must not 500 the stream.

    Regression: langgraph's default tool-error handler re-raises our ToolException
    (raised when e.g. Open-Meteo times out), which propagated out of `astream` and
    crashed `/agent/stream`. The sub-agent now turns tool errors into a ToolMessage
    so the model can answer gracefully.
    """
    from app.exceptions import WeatherUnavailableError
    from app.services import weather_service

    async def _boom(city, days=None):
        raise WeatherUnavailableError("Upstream service unavailable")

    monkeypatch.setattr(weather_service, "get_weather", _boom)

    tool_call = AIMessage(
        content="",
        tool_calls=[{"name": "get_weather", "args": {"city": "Bali"}, "id": "c1"}],
    )
    app = _make_app(
        tmp_path,
        "concierge",
        answer="",
        responses=[tool_call, "Sorry, the weather service is unavailable right now."],
    )
    with TestClient(app) as c:
        resp = c.post(
            "/agent/stream",
            json={"message": "weather in Bali?", "user_id": "u1"},
        )

    assert resp.status_code == 200
    text = resp.text
    assert "Sorry, the weather service is unavailable right now." in text
    assert "Traceback" not in text  # no crash leaked into the stream


def test_chat_returns_fallback_when_graph_raises(tmp_path):
    """/agent/chat must always return a readable reply, even when the graph run
    itself crashes (LLM outage, recursion-limit exhaustion on a tool-retry loop).

    Regression for "we should always return messages for user even have any
    error": the endpoint wraps ``graph.ainvoke`` so a failure degrades to the
    fallback reply (persisted) instead of an empty 500.
    """
    from app.agents.constants import AGENT_ERROR_FALLBACK_MSG
    from app.repositories.conversation import ConversationRepository

    url = f"sqlite:///{tmp_path / 'agent_chat_fallback.db'}"
    Base.metadata.create_all(get_engine(url), checkfirst=True)

    app = create_app()

    def _override_session():
        s = get_session_factory(url)()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    class _CrashingGraph:
        async def ainvoke(self, *args, **kwargs):
            raise RuntimeError("model provider down")

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_travel_graph] = lambda: _CrashingGraph()

    with TestClient(app) as c:
        resp = c.post(
            "/agent/chat",
            json={"message": "plan a trip to Hanoi", "user_id": "u1"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == AGENT_ERROR_FALLBACK_MSG
    assert body["current_flow"] is None
    assert body["interrupt_pending"] is False
    assert body["interrupt_payload"] is None

    # The fallback reply was persisted as an assistant message.
    s = get_session_factory(url)()
    try:
        msgs = ConversationRepository(s).list_messages(body["conversation_id"])
    finally:
        s.close()
    assistant_contents = [m.content for m in msgs if m.role == "assistant"]
    assert AGENT_ERROR_FALLBACK_MSG in assistant_contents


def test_chat_schedules_memory_extraction_background_task(tmp_path):
    """After a normal (non-interrupted) turn, /agent/chat must run memory
    extraction as a FastAPI BackgroundTask and write the result to the store.

    ``extract_memory`` is a FAST_AGENTS member (app/agents/constants.py), so
    ``graph.extract_memory_llm`` resolves to the same fake `fast_llm` instance
    used by `summarize`/`reflection`. On a brand-new conversation, `summarize`
    skips its LLM call (history too short — see make_summarize_node), so the
    fast-response queue is consumed as: reflection ("OK"), then extraction
    (scripted JSON) — in that order. TestClient runs BackgroundTasks
    synchronously after the response, so the store write is visible immediately.
    """
    from app.memory.store import search_preferences

    app = _make_app(
        tmp_path,
        "concierge",
        "Visit Tokyo Tower at sunset.",
        fast_responses=[
            "OK",
            '{"preferences": [{"key": "seat_pref", "text": "prefers window seats"}], '
            '"instructions": [], "episodes": []}',
        ],
    )
    with TestClient(app) as c:
        resp = c.post(
            "/agent/chat",
            json={"message": "What should I see in Tokyo?", "user_id": "u1"},
        )
    assert resp.status_code == 200
    assert resp.json()["interrupt_pending"] is False

    prefs = search_preferences(app.state.test_graph.store, "u1")
    assert any(p["text"] == "prefers window seats" for p in prefs)


def test_chat_skips_memory_extraction_when_interrupt_pending(tmp_path):
    """A turn that pauses at the plan-approval interrupt must NOT run memory
    extraction — the reply is empty ("" — no assistant turn to extract from)
    and the flow hasn't been approved yet.
    """
    from app.memory.store import search_preferences

    app = _make_app(tmp_path, "booking", "Hotel booked!", premium_users=["u1"])
    with TestClient(app) as c:
        resp = c.post(
            "/agent/chat",
            json={"message": "book me a hotel in Paris", "user_id": "u1"},
        )
    assert resp.status_code == 200
    assert resp.json()["interrupt_pending"] is True

    prefs = search_preferences(app.state.test_graph.store, "u1")
    assert prefs == []


def test_manifest_lists_tools_and_subagents(client):
    resp = client.get("/agent/manifest")
    assert resp.status_code == 200
    body = resp.json()
    assert "concierge" in body["subagents"]
    names = {t["name"] for t in body["tools"]}
    assert "get_trip_summary" in names
    book = next(t for t in body["tools"] if t["name"] == "book_hotel")
    assert book["destructive"] is True


# ---------------------------------------------------------------------------
# HITL stream tests (feat/agent-stream-hitl)
# ---------------------------------------------------------------------------


def test_stream_booking_emits_interrupt_event(booking_client):
    """Booking stream must pause with a named 'interrupt' SSE event, not hang silently."""
    resp = booking_client.post(
        "/agent/stream",
        json={"message": "book me a hotel in Paris", "user_id": "u1"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    text = resp.text
    assert "event: done" in text
    assert "event: interrupt" in text

    events = _parse_sse(text)
    interrupt_events = [e for e in events if e.get("event") == "interrupt"]
    assert len(interrupt_events) == 1, "exactly one interrupt event expected"

    data = json.loads(interrupt_events[0]["data"])
    assert "conversation_id" in data
    assert data["payload"]["type"] == "plan_approval"
    assert "book me a hotel" in data["payload"]["draft"]


def test_stream_booking_resume_approved(booking_client):
    """Resume-approved over stream: booking sub-agent tokens stream normally."""
    # Initial turn — triggers interrupt.
    resp1 = booking_client.post(
        "/agent/stream",
        json={"message": "book me a hotel in Paris", "user_id": "u1"},
    )
    events = _parse_sse(resp1.text)
    intr = next(e for e in events if e.get("event") == "interrupt")
    conv_id = json.loads(intr["data"])["conversation_id"]

    # Resume with approval — booking sub-agent answer streams.
    resp2 = booking_client.post(
        "/agent/stream",
        json={
            "user_id": "u1",
            "conversation_id": conv_id,
            "resume": {"approved": True},
        },
    )
    assert resp2.status_code == 200
    text = resp2.text
    assert "event: done" in text
    assert "event: interrupt" not in text, "no second interrupt after approval"
    assert "Hotel booked" in text


def test_stream_booking_resume_rejected(booking_client):
    """Resume-rejected over stream: ends cleanly without booking tokens."""
    # Initial turn.
    resp1 = booking_client.post(
        "/agent/stream",
        json={"message": "book me a hotel in Paris", "user_id": "u1"},
    )
    events = _parse_sse(resp1.text)
    intr = next(e for e in events if e.get("event") == "interrupt")
    conv_id = json.loads(intr["data"])["conversation_id"]

    # Resume with rejection.
    resp2 = booking_client.post(
        "/agent/stream",
        json={
            "user_id": "u1",
            "conversation_id": conv_id,
            "resume": {"approved": False},
        },
    )
    assert resp2.status_code == 200
    text = resp2.text
    assert "event: done" in text
    assert "event: interrupt" not in text
    assert "Hotel booked" not in text
