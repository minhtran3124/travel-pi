"""HTTP contract of /agent/chat and /agent/stream: ownership, id/resume validation, provider-failure mapping."""

import json
from uuid import uuid4

import pytest
from app.agents.graph import build_graph
from app.agents.supervisor import SupervisorIntent
from app.clients.llm import FakeLLM
from app.core.auth import AuthUser, get_current_user
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.session import get_session
from app.main import create_app
from app.routers.agent import get_travel_graph, get_travel_graph_optional
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

_USER = {"id": "u1"}


class _Graph:
    """Delegates to a real graph; ``ainvoke``/``astream_events`` can be made to raise."""

    def __init__(self, graph, exc=None):
        self._g = graph
        self._exc = exc

    async def ainvoke(self, *a, **k):
        if self._exc:
            raise self._exc
        return await self._g.ainvoke(*a, **k)

    def astream_events(self, *a, **k):
        if self._exc:
            exc = self._exc

            async def _boom():
                raise exc
                yield  # pragma: no cover

            return _boom()
        return self._g.astream_events(*a, **k)

    def astream(self, *a, **k):
        if self._exc:
            return self.astream_events()
        return self._g.astream(*a, **k)

    async def aget_state(self, *a, **k):
        return await self._g.aget_state(*a, **k)

    def __getattr__(self, name):
        return getattr(self._g, name)


def _app(tmp_path, exc=None):
    url = f"sqlite:///{tmp_path / 'contract.db'}"
    Base.metadata.create_all(get_engine(url), checkfirst=True)
    app = create_app()

    def _session():
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
        structured_responses=[SupervisorIntent(target_agent="concierge")] * 6,
        responses=["Hello there."] * 6,
    )
    graph = _Graph(
        build_graph(
            llm=main,
            fast_llm=FakeLLM(responses=["OK"] * 6),
            checkpointer=MemorySaver(),
            store=InMemoryStore(),
        ),
        exc,
    )
    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: AuthUser(
        id=_USER["id"], email=None, role=None, claims={}
    )
    app.dependency_overrides[get_travel_graph] = lambda: graph
    app.dependency_overrides[get_travel_graph_optional] = lambda: graph
    return app


@pytest.fixture
def client(tmp_path):
    _USER["id"] = "u1"
    with TestClient(_app(tmp_path)) as c:
        yield c


def test_chat_rejects_other_users_conversation(client):
    conv = client.post("/agent/chat", json={"message": "hi"}).json()["conversation_id"]
    _USER["id"] = "u2"
    resp = client.post("/agent/chat", json={"message": "hi", "conversation_id": conv})
    assert resp.status_code == 404
    _USER["id"] = "u1"
    msgs = client.get(f"/agent/conversations/{conv}/messages").json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]


def test_stream_rejects_other_users_conversation(client):
    conv = client.post("/agent/chat", json={"message": "hi"}).json()["conversation_id"]
    _USER["id"] = "u2"
    resp = client.post("/agent/stream", json={"message": "hi", "conversation_id": conv})
    assert resp.status_code == 404


@pytest.mark.parametrize("path", ["/agent/chat", "/agent/stream"])
def test_non_uuid_conversation_id_is_422(client, path):
    resp = client.post(path, json={"message": "hi", "conversation_id": "not-a-uuid"})
    assert resp.status_code == 422


@pytest.mark.parametrize("path", ["/agent/chat", "/agent/stream"])
def test_nul_byte_message_is_422(client, path):
    resp = client.post(path, json={"message": "hi\u0000there"})
    assert resp.status_code == 422


@pytest.mark.parametrize("path", ["/agent/chat", "/agent/stream"])
def test_resume_without_conversation_id_is_422(client, path):
    resp = client.post(path, json={"resume": {"approved": True}})
    assert resp.status_code == 422


@pytest.mark.parametrize("path", ["/agent/chat", "/agent/stream"])
def test_resume_without_pending_interrupt_is_409(client, path):
    conv = client.post("/agent/chat", json={"message": "hi"}).json()["conversation_id"]
    resp = client.post(
        path, json={"resume": {"approved": True}, "conversation_id": conv}
    )
    assert resp.status_code == 409


@pytest.mark.parametrize("path", ["/agent/chat", "/agent/stream"])
def test_resume_unknown_conversation_is_404(client, path):
    resp = client.post(
        path, json={"resume": {"approved": True}, "conversation_id": str(uuid4())}
    )
    assert resp.status_code == 404


_LEAK = "sk-ant-SECRET invalid x-api-key request_id req_123 set ANTHROPIC_API_KEY"


class AuthenticationError(Exception):
    """Same class name the anthropic/openai SDKs use for a 401."""


def test_chat_provider_auth_failure_is_502_and_sanitized(tmp_path):
    app = _app(tmp_path, exc=AuthenticationError(_LEAK))
    with TestClient(app) as c:
        resp = c.post("/agent/chat", json={"message": "hi"})
    assert resp.status_code == 502
    assert "SECRET" not in resp.text
    assert "req_123" not in resp.text


def test_stream_provider_auth_failure_event_is_sanitized(tmp_path):
    app = _app(tmp_path, exc=AuthenticationError(_LEAK))
    with TestClient(app) as c:
        resp = c.post("/agent/stream", json={"message": "hi"})
    assert "SECRET" not in resp.text
    assert "req_123" not in resp.text
    assert "ANTHROPIC_API_KEY" not in resp.text
    errs = [
        json.loads(line[5:])
        for line in resp.text.splitlines()
        if line.startswith("data:") and '"code"' in line
    ]
    assert errs and errs[-1]["code"] == "llm_auth"
