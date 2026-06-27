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


def _make_app(tmp_path, intent_target: str, answer: str, *, responses=None):
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

    # Build the graph ONCE per app instance so the MemorySaver checkpointer
    # survives across requests within a test. Per-request rebuild loses checkpoint
    # state and breaks HITL resume (second request gets a fresh graph with no
    # interrupt checkpoint, so plan_node fires again instead of resuming).
    main = FakeLLM(
        structured_responses=[SupervisorIntent(target_agent=intent_target)] * 6,
        responses=responses if responses is not None else [answer] * 6,
    )
    fast = FakeLLM(responses=["OK"] * 6)
    _graph = build_graph(
        llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=InMemoryStore()
    )

    def _override_graph():
        return _graph

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_travel_graph] = _override_graph
    return app


@pytest.fixture
def client(tmp_path):
    app = _make_app(tmp_path, "concierge", "Visit Tokyo Tower at sunset.")
    with TestClient(app) as c:
        yield c


@pytest.fixture
def booking_client(tmp_path):
    app = _make_app(tmp_path, "booking", "Hotel booked!")
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


def test_stream_emits_sse_events(client):
    resp = client.post(
        "/agent/stream",
        json={"message": "hi", "user_id": "u1"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    text = resp.text
    assert "data:" in text
    assert "[DONE]" in text
    # The concierge answer streams; the reflection critic's verdict ("OK", scripted
    # in the fixture's fast LLM) must NOT leak into the SSE feed (REVIEW.md C4).
    assert "Visit Tokyo Tower" in text
    assert "OK" not in text
    # Non-booking flow must NOT emit an interrupt event.
    assert "event: interrupt" not in text


def test_stream_drops_tool_json_output(tmp_path, monkeypatch):
    """Raw tool output (a weather dict) must not leak into the SSE feed.

    Regression for the "chatbot shows json/dict" bug: a sub-agent's ToolNode runs
    inside the same `langgraph_node` as its assistant, so the tool's JSON result
    rode through the node filter into the stream. Only the natural-language reply
    is user-facing, and it must appear exactly once (no per-loop duplication).
    """
    from app.services import weather_service

    marker = "WEATHER_JSON_LEAK_MARKER"

    async def _fake_get_weather(city, days=None):
        return {"location": {"name": city}, "marker": marker}

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
    assert marker not in text  # raw tool JSON must NOT reach the user
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
    assert "[DONE]" in text
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
    assert "[DONE]" in text
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
    assert "[DONE]" in text
    assert "event: interrupt" not in text
    assert "Hotel booked" not in text
