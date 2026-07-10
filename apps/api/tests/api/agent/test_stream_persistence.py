"""Stream persistence tests — Task 1.1 of specs/conversation-persistence.

Verifies that POST /agent/stream (the only path the FE calls) now creates a
Conversation row, a user Message, and an assistant Message in the DB, and that
the echoed conversation_id in the `start` event is the real DB uuid (not the
old `stream-<hex>` throwaway).
"""

from __future__ import annotations

import json

import pytest
from app.agents.grader import CriterionResult, GraderResponse
from app.agents.graph import build_graph
from app.agents.supervisor import SupervisorIntent
from app.clients.llm import FakeLLM
from app.core.auth import AuthUser, get_current_user_optional
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.session import get_session
from app.main import create_app
from app.repositories.conversation import ConversationRepository
from app.routers.agent import get_travel_graph
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_agent_config_cache():
    """Keep the process-wide config cache from leaking between tests."""
    yield
    from app.core.agent_config_cache import AgentConfigCache

    AgentConfigCache.clear()


def _force_grader_enabled():
    """Turn the rubric grader on for a test that scripts grader verdicts.

    The ``grader`` agent_config row seeds ``enabled=False`` (unmeasured prototype,
    gated off by default), so without this the grader delegates to ``reflection``
    and the scripted verdicts are never consumed. Must be called INSIDE the
    ``TestClient`` block — lifespan wires a DB loader that would overwrite the cache.
    """
    from app.core.agent_config_cache import AgentConfigCache, AgentModelOverride

    AgentConfigCache.sync_from_cache({"grader": AgentModelOverride(enabled=True)})


def _make_app(
    tmp_path,
    answer: str = "Here is your travel advice.",
    *,
    intent_target: str = "concierge",
    fast_responses: list[str] | None = None,
    premium_users: list[str] | None = None,
):
    url = f"sqlite:///{tmp_path / 'stream_persist.db'}"
    Base.metadata.create_all(get_engine(url), checkfirst=True)

    if premium_users:
        from app.repositories.user import UserRepository

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

    main_llm = FakeLLM(
        structured_responses=[SupervisorIntent(target_agent=intent_target)] * 6,
        responses=[answer] * 6,
    )
    fast_llm = FakeLLM(
        responses=fast_responses if fast_responses is not None else ["OK"] * 6,
        # concierge/booking turns are judged by the MIN-59 rubric grader, which
        # reads this structured queue rather than ``responses``.
        structured_responses=[
            GraderResponse(evaluations=[CriterionResult(name="grounding", passed=True)])
        ]
        * 6,
    )
    _graph = build_graph(
        llm=main_llm,
        fast_llm=fast_llm,
        checkpointer=MemorySaver(),
        store=InMemoryStore(),
    )

    def _override_graph():
        return _graph

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_travel_graph] = _override_graph
    # Test-only introspection hook (see tests/api/agent/test_agent_chat.py):
    # deliberately not `app.state.travel_graph` — the real lifespan would
    # clobber it with a production graph once TestClient triggers startup.
    app.state.test_graph = _graph

    # Premium requires authentication (hybrid identity — anonymous is always
    # free). Simulate being logged in as the first premium user so tier
    # resolves correctly (mirrors tests/api/agent/test_agent_chat.py).
    if premium_users:
        _puid = premium_users[0]
        app.dependency_overrides[get_current_user_optional] = lambda: AuthUser(
            id=_puid, email=None, role=None, claims={}
        )

    return app, url


def _parse_sse(text: str) -> list[dict]:
    events = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        current: dict = {}
        for line in block.splitlines():
            if line.startswith("event:"):
                current["event"] = line[6:].strip()
            elif line.startswith("data:"):
                current["data"] = line[5:].strip()
        if current:
            events.append(current)
    return events


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_stream_creates_conversation_and_messages(tmp_path):
    """After a fresh POST /agent/stream turn the DB must contain:
    - exactly 1 Conversation for the user
    - 1 user Message with the sent text
    - 1 assistant Message with the streamed reply
    And the `start` event's conversation_id must be the real DB uuid.
    """
    app, url = _make_app(tmp_path, answer="Here is your travel advice.")
    with TestClient(app) as client:
        resp = client.post(
            "/agent/stream",
            json={"message": "What should I visit in Kyoto?", "user_id": "user-42"},
        )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(resp.text)
    start_events = [e for e in events if e.get("event") == "start"]
    assert len(start_events) == 1, "expected exactly one start event"

    echoed_conv_id = json.loads(start_events[0]["data"])["conversation_id"]

    # Must be a real DB id (uuid4 hex), NOT the old `stream-<hex>` throwaway.
    assert not echoed_conv_id.startswith("stream-"), (
        f"conversation_id looks like the old throwaway: {echoed_conv_id!r}"
    )

    # Inspect the DB directly using an isolated factory session.
    factory = get_session_factory(url)
    repo = ConversationRepository(factory)

    conversations = repo.list_for_user("user-42")
    assert len(conversations) == 1, f"expected 1 conversation, got {len(conversations)}"
    conv = conversations[0]
    assert conv.id == echoed_conv_id

    messages = repo.list_messages(conv.id)
    assert len(messages) == 2, (
        f"expected 2 messages (user + assistant), got {len(messages)}"
    )

    user_msgs = [m for m in messages if m.role == "user"]
    assistant_msgs = [m for m in messages if m.role == "assistant"]
    assert len(user_msgs) == 1
    assert len(assistant_msgs) == 1
    assert user_msgs[0].content == "What should I visit in Kyoto?"
    assert "travel advice" in assistant_msgs[0].content


def test_stream_uses_existing_conversation_id(tmp_path):
    """When body.conversation_id is supplied, the same conversation row is reused
    (no new Conversation row is created for a follow-up turn).
    """
    app, url = _make_app(tmp_path)
    with TestClient(app) as client:
        # First turn — no conversation_id.
        resp1 = client.post(
            "/agent/stream",
            json={"message": "Plan my trip", "user_id": "user-99"},
        )
        assert resp1.status_code == 200
        events1 = _parse_sse(resp1.text)
        conv_id = json.loads(
            next(e for e in events1 if e.get("event") == "start")["data"]
        )["conversation_id"]

        # Second turn — supply the conversation_id.
        resp2 = client.post(
            "/agent/stream",
            json={
                "message": "Add some restaurants",
                "user_id": "user-99",
                "conversation_id": conv_id,
            },
        )
        assert resp2.status_code == 200

    factory = get_session_factory(url)
    repo = ConversationRepository(factory)
    conversations = repo.list_for_user("user-99")
    assert len(conversations) == 1, "second turn must not create a new conversation row"
    messages = repo.list_messages(conversations[0].id)
    # 2 turns × (1 user + 1 assistant) = 4 messages
    assert len(messages) == 4


def test_stream_retry_does_not_duplicate_user_message(tmp_path):
    """Retry (body.retry=True) re-answers a dangling user turn without saving a
    second copy of the question — it adds only the assistant reply.
    """
    app, url = _make_app(tmp_path, answer="The retried answer.")

    # Simulate an interrupted turn: a conversation with a user message but no
    # assistant reply (the previous stream was abandoned before persisting).
    factory = get_session_factory(url)
    repo = ConversationRepository(factory)
    conv = repo.create_conversation(user_id="user-55")
    repo.append_message(
        conversation_id=conv.id, role="user", content="Where to eat in Hue?"
    )

    with TestClient(app) as client:
        resp = client.post(
            "/agent/stream",
            json={
                "message": "Where to eat in Hue?",
                "user_id": "user-55",
                "conversation_id": conv.id,
                "retry": True,
            },
        )
    assert resp.status_code == 200

    messages = repo.list_messages(conv.id)
    user_msgs = [m for m in messages if m.role == "user"]
    assistant_msgs = [m for m in messages if m.role == "assistant"]
    assert len(user_msgs) == 1, "retry must not add a second user message"
    assert len(assistant_msgs) == 1, "retry must persist the assistant reply"
    assert "retried answer" in assistant_msgs[0].content


def test_stream_resume_does_not_append_user_message(tmp_path):
    """Resume turns (body.resume is not None) must NOT append a second user message."""

    app, url = _make_app(tmp_path)

    # Manually create a conversation so we have a valid id to resume.
    factory = get_session_factory(url)
    repo = ConversationRepository(factory)
    conv = repo.create_conversation(user_id="user-77")

    with TestClient(app) as client:
        resp = client.post(
            "/agent/stream",
            json={
                "user_id": "user-77",
                "conversation_id": conv.id,
                "resume": {"approved": True},
            },
        )
    assert resp.status_code == 200

    messages = repo.list_messages(conv.id)
    user_msgs = [m for m in messages if m.role == "user"]
    assert len(user_msgs) == 0, "resume turn must not add a user message row"


def test_stream_schedules_memory_extraction_after_drain(tmp_path):
    """A normal (non-resume, non-interrupted) /agent/stream turn must run memory
    extraction via the response's background task once the SSE stream fully
    drains, writing the scripted preference to the graph's store.

    ``extract_memory`` is a FAST_AGENTS member (app/agents/constants.py), so
    ``graph.extract_memory_llm`` resolves to the same fake fast_llm used by the
    grader — but the grader reads the *structured* queue, so this plain queue
    holds only the extraction JSON. TestClient consumes the full response body —
    including the Starlette `background` task — synchronously within
    `client.post`, so the store write is visible immediately after the call.
    """
    from app.memory.store import search_preferences

    app, _url = _make_app(
        tmp_path,
        fast_responses=[
            '{"preferences": [{"key": "seat_pref", "text": "prefers window seats"}], '
            '"instructions": [], "episodes": []}',
        ],
    )
    with TestClient(app) as client:
        _force_grader_enabled()
        resp = client.post(
            "/agent/stream",
            json={
                "message": "What should I visit in Kyoto?",
                "user_id": "user-extract",
            },
        )
    assert resp.status_code == 200

    prefs = search_preferences(app.state.test_graph.store, "user-extract")
    assert any(p["text"] == "prefers window seats" for p in prefs)


def test_stream_booking_interrupt_skips_memory_extraction(tmp_path):
    """A booking /agent/stream turn that emits a plan-approval interrupt must
    NOT run memory extraction — the graph is paused, not finished, so the
    background task's sink carries ``interrupt_pending=True`` and no-ops.
    """
    from app.memory.store import search_preferences

    app, _url = _make_app(
        tmp_path,
        intent_target="booking",
        premium_users=["user-book"],
    )
    with TestClient(app) as client:
        resp = client.post(
            "/agent/stream",
            json={"message": "book me a hotel in Paris", "user_id": "user-book"},
        )
    assert resp.status_code == 200
    assert "event: interrupt" in resp.text

    prefs = search_preferences(app.state.test_graph.store, "user-book")
    assert prefs == []
