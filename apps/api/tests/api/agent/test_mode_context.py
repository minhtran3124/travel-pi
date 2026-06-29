"""Router wires per-run AgentContext (specs/runtime-context-config A.2).

Asserts the router resolves `mode` from the client but `tier` server-side
(never from the request body), and passes a context= to the graph. Nothing
reads the context yet, so these tests guard the wiring + the security property.
"""

from __future__ import annotations

import app.routers.agent as agent_router
from app.agents.graph import build_graph
from app.agents.supervisor import SupervisorIntent
from app.clients.llm import FakeLLM
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.session import get_session
from app.main import create_app
from app.routers.agent import get_travel_graph
from app.schemas.agent import ChatRequest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore


def _make_app(tmp_path):
    url = f"sqlite:///{tmp_path / 'mode_ctx.db'}"
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
            structured_responses=[SupervisorIntent(target_agent="concierge")] * 4,
            responses=["Sure."] * 4,
        ),
        fast_llm=FakeLLM(responses=["OK"] * 4),
        checkpointer=MemorySaver(),
        store=InMemoryStore(),
    )
    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_travel_graph] = lambda: graph
    return app


def test_chat_request_ignores_client_supplied_tier():
    # Security: tier is not part of the request contract — a forged field is
    # silently ignored by Pydantic (extra='ignore'), never bound.
    req = ChatRequest.model_validate(
        {"message": "hi", "user_id": "u1", "mode": "deep", "tier": "premium"}
    )
    assert req.mode == "deep"
    assert not hasattr(req, "tier")


def test_router_resolves_tier_serverside_not_from_body(tmp_path, monkeypatch):
    calls = []
    real = agent_router.resolve_agent_context

    def spy(*, tier, mode):
        calls.append({"tier": tier, "mode": mode})
        return real(tier=tier, mode=mode)

    monkeypatch.setattr(agent_router, "resolve_agent_context", spy)

    app = _make_app(tmp_path)
    with TestClient(app) as client:
        resp = client.post(
            "/agent/chat",
            json={
                "message": "Plan Kyoto",
                "user_id": "u1",
                "mode": "deep",
                "tier": "premium",  # forged — must be ignored
            },
        )
    assert resp.status_code == 200
    assert calls, "router must resolve an AgentContext"
    assert calls[-1]["mode"] == "deep", "mode comes from the client body"
    assert calls[-1]["tier"] == "free", (
        "tier is BE-resolved, never the forged body value"
    )


def test_missing_mode_defaults(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        agent_router,
        "resolve_agent_context",
        lambda *, tier, mode: (
            calls.append({"tier": tier, "mode": mode}) or agent_router.AgentContext()
        ),
    )
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        resp = client.post("/agent/chat", json={"message": "hi", "user_id": "u1"})
    assert resp.status_code == 200
    assert calls[-1] == {"tier": "free", "mode": None}
