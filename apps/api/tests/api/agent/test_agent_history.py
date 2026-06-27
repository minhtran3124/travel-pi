"""History read endpoints — Task 2.1 of specs/conversation-persistence.

Verifies:
- GET /agent/conversations?user_id=... returns the user's conversations (newest first).
- GET /agent/conversations/{id}/messages returns ordered messages for a conversation.
- Both endpoints return 200 with [] for unknown user/conversation ids.
"""

from __future__ import annotations

from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.session import get_session
from app.main import create_app
from app.repositories.conversation import ConversationRepository
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app(tmp_path):
    url = f"sqlite:///{tmp_path / 'history.db'}"
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

    app.dependency_overrides[get_session] = _override_session
    return app, get_session_factory(url)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_list_conversations_returns_user_conversations(tmp_path):
    """GET /agent/conversations?user_id=... returns the user's conversations."""
    app, factory = _make_app(tmp_path)
    repo = ConversationRepository(factory)

    conv1 = repo.create_conversation(user_id="user-history-1", trip_id="trip-a")
    conv2 = repo.create_conversation(user_id="user-history-1")

    with TestClient(app) as client:
        resp = client.get("/agent/conversations", params={"user_id": "user-history-1"})

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    ids = [d["id"] for d in data]
    assert conv1.id in ids
    assert conv2.id in ids
    # newest first (list_for_user orders by created_at desc)
    assert data[0]["id"] == conv2.id


def test_list_conversations_unknown_user_returns_empty(tmp_path):
    """GET /agent/conversations for an unknown user_id returns 200 with []."""
    app, _ = _make_app(tmp_path)

    with TestClient(app) as client:
        resp = client.get(
            "/agent/conversations", params={"user_id": "nonexistent-user"}
        )

    assert resp.status_code == 200
    assert resp.json() == []


def test_list_messages_returns_ordered_messages(tmp_path):
    """GET /agent/conversations/{id}/messages returns messages oldest-first."""
    app, factory = _make_app(tmp_path)
    repo = ConversationRepository(factory)

    conv = repo.create_conversation(user_id="user-msgs-1")
    repo.append_message(conversation_id=conv.id, role="user", content="Hello agent")
    repo.append_message(
        conversation_id=conv.id, role="assistant", content="Hello traveller"
    )

    with TestClient(app) as client:
        resp = client.get(f"/agent/conversations/{conv.id}/messages")

    assert resp.status_code == 200
    msgs = resp.json()
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "Hello agent"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["content"] == "Hello traveller"


def test_list_messages_unknown_conversation_returns_empty(tmp_path):
    """GET /agent/conversations/{id}/messages for an unknown id returns 200 with []."""
    app, _ = _make_app(tmp_path)

    with TestClient(app) as client:
        resp = client.get("/agent/conversations/does-not-exist/messages")

    assert resp.status_code == 200
    assert resp.json() == []


def test_list_conversations_scoped_to_user(tmp_path):
    """Conversations for user-A are not returned when querying for user-B."""
    app, factory = _make_app(tmp_path)
    repo = ConversationRepository(factory)

    repo.create_conversation(user_id="user-a")

    with TestClient(app) as client:
        resp = client.get("/agent/conversations", params={"user_id": "user-b"})

    assert resp.status_code == 200
    assert resp.json() == []
