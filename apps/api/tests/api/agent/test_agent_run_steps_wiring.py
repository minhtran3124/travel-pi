"""Both channels persist their per-step call chain alongside the run row (SC-8).

A ``/agent/chat`` turn writes its steps on the request session before that
handler's explicit commit; a ``/agent/stream`` turn writes them in
``record_agent_run``'s finalizer on the isolated factory. Neither writes from a
background task (that deadlocked the parent branch).
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
    return f"sqlite:///{tmp_path / 'agent_run_steps.db'}"


def _make_app(tmp_path):
    url = _db_url(tmp_path)
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

    graph = build_graph(
        llm=FakeLLM(
            structured_responses=[SupervisorIntent(target_agent="concierge")] * 6,
            responses=["Visit Tokyo Tower at sunset."] * 6,
        ),
        fast_llm=FakeLLM(responses=["OK"] * 6),
        checkpointer=MemorySaver(),
        store=InMemoryStore(),
    )

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_current_user] = lambda: AuthUser(
        id="u1", email=None, role=None, claims={}
    )
    app.dependency_overrides[get_travel_graph] = lambda: graph
    app.state.test_graph = graph
    return app


def _repo(tmp_path) -> AgentRunRepository:
    return AgentRunRepository(get_session_factory(_db_url(tmp_path)))


def _assert_trace_persisted(tmp_path, channel: str):
    repo = _repo(tmp_path)
    rows = repo.list_recent()
    assert len(rows) == 1
    run = rows[0]
    assert run.channel == channel
    assert run.status == "completed"
    # The build-time snapshot reached the run row.
    assert run.prompt_versions
    assert run.prompt_versions.get("supervisor")

    steps = repo.steps_for(run.id)
    assert steps, "no step rows persisted"
    # Ordered by seq, ascending and gapless from 0 (assigned at step start).
    assert [s.seq for s in steps] == list(range(len(steps)))

    llm_steps = [s for s in steps if s.kind == "llm"]
    assert llm_steps, "no llm step persisted"
    assert all(s.node for s in llm_steps)

    node_steps = [s for s in steps if s.kind == "node"]
    assert node_steps, "no node step persisted"
    supervisor = next(s for s in node_steps if s.node == "supervisor")
    # Prompt attribution came from the graph's snapshot.
    assert supervisor.prompts == [
        {"name": "supervisor", "version": run.prompt_versions["supervisor"]}
    ]


def test_chat_turn_persists_ordered_steps_and_prompt_versions(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as c:
        resp = c.post(
            "/agent/chat",
            json={"message": "What should I see in Tokyo?", "user_id": "u1"},
        )
    assert resp.status_code == 200
    _assert_trace_persisted(tmp_path, "chat")


def test_stream_turn_persists_ordered_steps_and_prompt_versions(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as c:
        resp = c.post("/agent/stream", json={"message": "hi", "user_id": "u1"})
        assert resp.status_code == 200
        assert "event: done" in resp.text
    _assert_trace_persisted(tmp_path, "stream")
