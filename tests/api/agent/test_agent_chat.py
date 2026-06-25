"""Agent API: /agent/chat, /agent/stream, /agent/manifest (Task 6.1)."""

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
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore


@pytest.fixture
def client(tmp_path):
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

    def _override_graph():
        main = FakeLLM(
            structured_responses=[SupervisorIntent(target_agent="concierge")] * 5,
            responses=["Visit Tokyo Tower at sunset."] * 5,
        )
        fast = FakeLLM(responses=["OK"] * 5)
        return build_graph(
            llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=InMemoryStore()
        )

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_travel_graph] = _override_graph
    with TestClient(app) as c:
        yield c


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


def test_manifest_lists_tools_and_subagents(client):
    resp = client.get("/agent/manifest")
    assert resp.status_code == 200
    body = resp.json()
    assert "concierge" in body["subagents"]
    names = {t["name"] for t in body["tools"]}
    assert "get_trip_summary" in names
    book = next(t for t in body["tools"] if t["name"] == "book_hotel")
    assert book["destructive"] is True
