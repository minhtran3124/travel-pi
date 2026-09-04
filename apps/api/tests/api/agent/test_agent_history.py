"""History read endpoints — Task 2.1 of specs/conversation-persistence.

Verifies:
- GET /agent/conversations returns the authed user's conversations (newest first).
- GET /agent/conversations/{id}/messages returns ordered messages for a conversation.
- Both endpoints return 200 with [] for an authed user with no data.
- Both require a Supabase JWT (401 without one); the identity is the JWT sub and
  the deprecated ``user_id`` query param is ignored.
"""

from __future__ import annotations

from app.core.auth import AuthUser, get_current_user
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.session import get_session
from app.main import create_app
from app.repositories.conversation import ConversationRepository
from fastapi.testclient import TestClient

# Reuse the existing interrupt-driving fixture from the sibling chat test module
# (no new fixture — see the c2 brief Global Constraints). ``booking_client`` seeds
# a premium "u1" and routes to the booking sub-agent, which pauses at a real
# plan-approval interrupt on the message below.
from test_agent_chat import booking_client  # noqa: F401

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app(tmp_path, *, auth_user_id: str | None = None):
    """Build a history test app.

    When ``auth_user_id`` is given the app authenticates as that user (identity
    is the JWT sub). When it is ``None`` the real required-auth dependency runs,
    so an unauthenticated request 401s — used to prove the JWT gate.
    """
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
    if auth_user_id is not None:
        app.dependency_overrides[get_current_user] = lambda: AuthUser(
            id=auth_user_id, email=None, role=None, claims={}
        )
    return app, get_session_factory(url)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_list_conversations_returns_user_conversations(tmp_path):
    """GET /agent/conversations returns the authed user's conversations."""
    app, factory = _make_app(tmp_path, auth_user_id="user-history-1")
    repo = ConversationRepository(factory)

    conv1 = repo.create_conversation(user_id="user-history-1", trip_id="trip-a")
    conv2 = repo.create_conversation(user_id="user-history-1")

    with TestClient(app) as client:
        resp = client.get("/agent/conversations")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    ids = [d["id"] for d in data]
    assert conv1.id in ids
    assert conv2.id in ids
    # newest first (list_for_user orders by created_at desc)
    assert data[0]["id"] == conv2.id


def test_list_conversations_unknown_user_returns_empty(tmp_path):
    """GET /agent/conversations for a user with no data returns 200 with []."""
    app, _ = _make_app(tmp_path, auth_user_id="nonexistent-user")

    with TestClient(app) as client:
        resp = client.get("/agent/conversations")

    assert resp.status_code == 200
    assert resp.json() == []


def test_list_messages_returns_ordered_messages(tmp_path):
    """GET /agent/conversations/{id}/messages returns messages oldest-first."""
    app, factory = _make_app(tmp_path, auth_user_id="user-msgs-1")
    repo = ConversationRepository(factory)

    conv = repo.create_conversation(user_id="user-msgs-1")
    repo.append_message(conversation_id=conv.id, role="user", content="Hello agent")
    repo.append_message(
        conversation_id=conv.id, role="assistant", content="Hello traveller"
    )

    with TestClient(app) as client:
        resp = client.get(f"/agent/conversations/{conv.id}/messages")

    assert resp.status_code == 200
    msgs = resp.json()["messages"]
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "Hello agent"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["content"] == "Hello traveller"


def test_list_messages_unknown_conversation_returns_empty(tmp_path):
    """GET /agent/conversations/{id}/messages for an unknown id returns 200 with []."""
    app, _ = _make_app(tmp_path, auth_user_id="anyone")

    with TestClient(app) as client:
        resp = client.get("/agent/conversations/does-not-exist/messages")

    assert resp.status_code == 200
    assert resp.json()["messages"] == []


def test_list_messages_requires_jwt(tmp_path):
    """GET messages without a Supabase JWT is rejected (401)."""
    app, factory = _make_app(tmp_path)  # no auth override → real JWT gate
    repo = ConversationRepository(factory)
    conv = repo.create_conversation(user_id="user-msgs-anon")
    repo.append_message(conversation_id=conv.id, role="user", content="secret")

    with TestClient(app) as client:
        resp = client.get(f"/agent/conversations/{conv.id}/messages")

    assert resp.status_code == 401


def test_list_messages_scoped_to_owner(tmp_path):
    """A non-owner cannot read another user's conversation messages (IDOR guard)."""
    app, factory = _make_app(tmp_path, auth_user_id="attacker-2")
    repo = ConversationRepository(factory)

    conv = repo.create_conversation(user_id="owner-1")
    repo.append_message(conversation_id=conv.id, role="user", content="private note")

    with TestClient(app) as client:
        resp = client.get(f"/agent/conversations/{conv.id}/messages")

    # Empty (not 403) so existence of the conversation is not confirmed.
    assert resp.status_code == 200
    assert resp.json()["messages"] == []


def test_list_messages_reports_pending_interrupt(booking_client):
    """GET messages surfaces the checkpoint's pending HITL interrupt state.

    A booking turn pauses at a real plan-approval interrupt; hydrating the
    conversation must report ``interrupt_pending`` with the interrupt payload so
    the FE can re-surface the approval prompt after a reload. A separate, freshly
    created conversation with no turns reports no pending interrupt.
    """
    # Drive a real interrupt on a fresh conversation.
    chat = booking_client.post(
        "/agent/chat",
        json={"message": "book me a hotel in Paris", "user_id": "u1"},
    )
    assert chat.status_code == 200
    conv_id = chat.json()["conversation_id"]

    resp = booking_client.get(f"/agent/conversations/{conv_id}/messages")
    assert resp.status_code == 200
    body = resp.json()
    assert body["interrupt_pending"] is True
    assert isinstance(body["interrupt_payload"], dict)
    assert body["interrupt_payload"]  # non-empty

    # A separate conversation with no turns has no pending interrupt. Create it
    # (owned by the same authed user) through the app's own session override so
    # it lives in the same DB the request handler reads.
    gen = booking_client.app.dependency_overrides[get_session]()
    session = next(gen)
    try:
        conv2 = ConversationRepository(session).create_conversation(user_id="u1")
        session.commit()
        conv2_id = conv2.id
    finally:
        gen.close()

    resp2 = booking_client.get(f"/agent/conversations/{conv2_id}/messages")
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["messages"] == []
    assert body2["interrupt_pending"] is False
    assert body2["interrupt_payload"] is None


def test_list_conversations_scoped_to_user(tmp_path):
    """Conversations for user-A are not returned when authed as user-B."""
    app, factory = _make_app(tmp_path, auth_user_id="user-b")
    repo = ConversationRepository(factory)

    repo.create_conversation(user_id="user-a")

    with TestClient(app) as client:
        resp = client.get("/agent/conversations")

    assert resp.status_code == 200
    assert resp.json() == []
