"""Agent-run metrics wiring for /agent/chat and /agent/stream (specs/agent-turn-metrics, SC-5).

Each agent turn returns a ``usage`` block and leaves exactly one ``agent_runs`` row
whose terminal ``status`` reflects the outcome (``completed`` / ``interrupted`` /
``failed``). Persistence is best-effort: a failing ``start`` must still return the
reply without a 500.
"""

from app.agents.graph import build_graph
from app.agents.supervisor import SupervisorIntent
from app.clients.llm import FakeLLM
from app.core.auth import AuthUser, get_current_user
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.session import get_session
from app.main import create_app
from app.repositories.agent_run import AgentRunRepository
from app.routers.agent import get_travel_graph
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore


def _db_url(tmp_path) -> str:
    return f"sqlite:///{tmp_path / 'agent_runs.db'}"


def _make_app(
    tmp_path,
    intent_target: str,
    answer: str,
    *,
    graph=None,
    premium_users: list[str] | None = None,
):
    from app.repositories.user import UserRepository

    url = _db_url(tmp_path)
    Base.metadata.create_all(get_engine(url), checkfirst=True)

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

    if graph is None:
        main = FakeLLM(
            structured_responses=[SupervisorIntent(target_agent=intent_target)] * 6,
            responses=[answer] * 6,
        )
        fast = FakeLLM(responses=["OK"] * 6)
        graph = build_graph(
            llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=InMemoryStore()
        )

    app.dependency_overrides[get_session] = _override_session
    _uid = premium_users[0] if premium_users else "u1"
    app.dependency_overrides[get_current_user] = lambda: AuthUser(
        id=_uid, email=None, role=None, claims={}
    )
    app.dependency_overrides[get_travel_graph] = lambda: graph
    app.state.test_graph = graph
    return app


def _runs(tmp_path) -> list:
    """Return all ``agent_runs`` rows for the test DB, newest first."""
    return AgentRunRepository(get_session_factory(_db_url(tmp_path))).list_recent()


def test_chat_turn_returns_usage_and_records_completed_run(tmp_path):
    app = _make_app(tmp_path, "concierge", "Visit Tokyo Tower at sunset.")
    with TestClient(app) as c:
        resp = c.post(
            "/agent/chat",
            json={"message": "What should I see in Tokyo?", "user_id": "u1"},
        )
    assert resp.status_code == 200
    usage = resp.json()["usage"]
    assert usage is not None
    assert usage["llm_calls"] >= 1
    assert usage["input_tokens"] > 0

    rows = _runs(tmp_path)
    assert len(rows) == 1
    row = rows[0]
    assert row.status == "completed"
    assert row.kind == "turn"
    assert row.channel == "chat"
    assert "supervisor" in (row.by_node or {})


def test_chat_graph_exception_returns_fallback_and_records_failed_run(tmp_path):
    from app.agents.constants import AGENT_ERROR_FALLBACK_MSG

    class _CrashingGraph:
        async def ainvoke(self, *args, **kwargs):
            raise RuntimeError("model provider down")

    app = _make_app(tmp_path, "concierge", "unused", graph=_CrashingGraph())
    with TestClient(app) as c:
        resp = c.post(
            "/agent/chat",
            json={"message": "plan a trip to Hanoi", "user_id": "u1"},
        )
    assert resp.status_code == 200
    assert resp.json()["reply"] == AGENT_ERROR_FALLBACK_MSG

    rows = _runs(tmp_path)
    assert len(rows) == 1
    assert rows[0].status == "failed"
    assert rows[0].kind == "turn"


def test_chat_interrupt_then_resume_records_two_rows(tmp_path):
    app = _make_app(tmp_path, "booking", "Hotel booked!", premium_users=["u1"])
    with TestClient(app) as c:
        resp1 = c.post(
            "/agent/chat",
            json={"message": "book me a hotel in Paris", "user_id": "u1"},
        )
        assert resp1.status_code == 200
        assert resp1.json()["interrupt_pending"] is True
        conv_id = resp1.json()["conversation_id"]

        resp2 = c.post(
            "/agent/chat",
            json={
                "user_id": "u1",
                "conversation_id": conv_id,
                "resume": {"approved": True},
            },
        )
        assert resp2.status_code == 200

    rows = _runs(tmp_path)
    assert len(rows) == 2
    kinds = {r.kind for r in rows}
    assert kinds == {"turn", "resume"}
    turn_row = next(r for r in rows if r.kind == "turn")
    resume_row = next(r for r in rows if r.kind == "resume")
    assert turn_row.status == "interrupted"
    assert resume_row.status == "completed"


def test_stream_turn_records_completed_run(tmp_path):
    app = _make_app(tmp_path, "concierge", "Visit Tokyo Tower at sunset.")
    with TestClient(app) as c:
        resp = c.post("/agent/stream", json={"message": "hi", "user_id": "u1"})
        assert resp.status_code == 200
        text = resp.text
    assert "event: done" in text

    rows = _runs(tmp_path)
    assert len(rows) == 1
    assert rows[0].status == "completed"
    assert rows[0].channel == "stream"


def test_chat_failing_start_still_returns_reply(tmp_path, monkeypatch):
    def _boom(self, *args, **kwargs):
        raise RuntimeError("start failed")

    monkeypatch.setattr(AgentRunRepository, "start", _boom)

    app = _make_app(tmp_path, "concierge", "Visit Tokyo Tower at sunset.")
    with TestClient(app) as c:
        resp = c.post(
            "/agent/chat",
            json={"message": "What should I see in Tokyo?", "user_id": "u1"},
        )
    assert resp.status_code == 200
    assert "Tokyo Tower" in resp.json()["reply"]

    # No row was inserted (start raised); finish on a missing id is a no-op.
    assert _runs(tmp_path) == []


def test_run_row_is_durable_without_the_request_session_commit(tmp_path):
    """The agent_runs row must not depend on the request session being committed.

    Found by a real-server UAT: writes flushed onto the request-scoped session
    *after* the graph await are not durable in the running app (the same reason
    the stream path persists its reply through an isolated factory), so a
    finish() flushed onto that session was lost and every /agent/chat turn stayed
    `running` forever — while this suite passed, because TestClient's dependency
    teardown does commit. Pinning the invariant with a NON-committing session
    override reproduces the production behaviour.
    """
    url = _db_url(tmp_path)
    app = _make_app(tmp_path, "concierge", "Visit Tokyo Tower at sunset.")

    def _no_commit_session():
        s = get_session_factory(url)()
        try:
            yield s  # deliberately never committed
        finally:
            s.close()

    app.dependency_overrides[get_session] = _no_commit_session

    with TestClient(app) as c:
        resp = c.post(
            "/agent/chat",
            json={"message": "What should I see in Tokyo?", "user_id": "u1"},
        )
    assert resp.status_code == 200

    rows = _runs(tmp_path)
    assert len(rows) == 1
    assert rows[0].status == "completed"
    assert rows[0].llm_calls >= 1
    assert rows[0].latency_ms is not None

    # The same commit also persists the assistant reply — the other half of the
    # symptom this UAT found. Pinning it here stops a future change that routes
    # only the run row through an isolated factory from re-losing the message.
    from app.db.models import Message

    with get_session_factory(url)() as s:
        roles = [m.role for m in s.query(Message).all()]
    assert "assistant" in roles
