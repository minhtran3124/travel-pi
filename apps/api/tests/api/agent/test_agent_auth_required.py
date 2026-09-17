"""Every /agent/* route except /manifest requires a JWT; identity is the token sub, so a forged body/query user_id is ignored and the daily quota keys on the sub."""

from __future__ import annotations

from app.agents.graph import build_graph
from app.agents.supervisor import SupervisorIntent
from app.clients.llm import FakeLLM
from app.core.auth import AuthUser, get_current_user
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.session import get_session
from app.main import create_app
from app.repositories.user import UserRepository
from app.routers.agent import get_travel_graph
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

_FAKE_RESPONSES = ["Sure, happy to help!"] * 20
_FAKE_STRUCTURED = [SupervisorIntent(target_agent="concierge")] * 20

_SUPABASE_UID = "supabase-uid-abc123"
_FORGED_UID = "forged-other-user"


def _make_app(tmp_path, *, auth_user_id: str | None = None, db_name: str = "auth.db"):
    """auth_user_id given → authenticated as that user; None → real auth gate runs (401)."""
    url = f"sqlite:///{tmp_path / db_name}"
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
            structured_responses=_FAKE_STRUCTURED,
            responses=_FAKE_RESPONSES,
        ),
        fast_llm=FakeLLM(responses=["OK"] * 20),
        checkpointer=MemorySaver(),
        store=InMemoryStore(),
    )
    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_travel_graph] = lambda: graph
    if auth_user_id is not None:
        app.dependency_overrides[get_current_user] = lambda: AuthUser(
            id=auth_user_id, email="user@test.com", role=None, claims={}
        )
    return app, url


def test_chat_without_token_is_401(tmp_path):
    app, _ = _make_app(tmp_path, db_name="chat_401.db")
    with TestClient(app) as client:
        resp = client.post("/agent/chat", json={"message": "Hello"})
    assert resp.status_code == 401


def test_stream_without_token_is_401(tmp_path):
    app, _ = _make_app(tmp_path, db_name="stream_401.db")
    with TestClient(app) as client:
        resp = client.post("/agent/stream", json={"message": "Hello"})
    assert resp.status_code == 401


def test_list_conversations_without_token_is_401(tmp_path):
    app, _ = _make_app(tmp_path, db_name="conv_401.db")
    with TestClient(app) as client:
        resp = client.get("/agent/conversations")
    assert resp.status_code == 401


def test_list_messages_without_token_is_401(tmp_path):
    app, _ = _make_app(tmp_path, db_name="msgs_401.db")
    with TestClient(app) as client:
        resp = client.get("/agent/conversations/whatever/messages")
    assert resp.status_code == 401


def test_manifest_stays_public(tmp_path):
    """/manifest is the one /agent/* route that answers without a JWT."""
    app, _ = _make_app(tmp_path, db_name="manifest_public.db")
    with TestClient(app) as client:
        resp = client.get("/agent/manifest")
    assert resp.status_code == 200


def test_authed_chat_uses_jwt_sub_not_body_user_id(tmp_path):
    """The conversation is keyed by the JWT sub even when body.user_id differs."""
    app, _ = _make_app(tmp_path, auth_user_id=_SUPABASE_UID, db_name="authed_sub.db")
    with TestClient(app) as client:
        resp = client.post(
            "/agent/chat", json={"message": "Hello", "user_id": _FORGED_UID}
        )
        assert resp.status_code == 200

        conv_resp = client.get("/agent/conversations")
        assert conv_resp.status_code == 200
        convs = conv_resp.json()
        assert len(convs) == 1
        assert convs[0]["user_id"] == _SUPABASE_UID


def test_forged_body_user_id_never_keys_conversation(tmp_path):
    """A forged body.user_id must not create any conversation under that id."""
    from app.db import models

    app, url = _make_app(tmp_path, auth_user_id=_SUPABASE_UID, db_name="antispoof.db")
    with TestClient(app) as client:
        resp = client.post(
            "/agent/chat", json={"message": "Hello", "user_id": _FORGED_UID}
        )
        assert resp.status_code == 200

    sf = get_session_factory(url)
    with sf() as s:
        real = (
            s.query(models.Conversation)
            .filter(models.Conversation.user_id == _SUPABASE_UID)
            .all()
        )
        forged = (
            s.query(models.Conversation)
            .filter(models.Conversation.user_id == _FORGED_UID)
            .all()
        )
    assert len(real) == 1, "conversation must exist under the JWT sub"
    assert forged == [], "forged body.user_id must not create any conversation"


def test_authed_list_ignores_query_user_id(tmp_path):
    """GET /agent/conversations?user_id=<forged> lists only the JWT sub's rows."""
    app, _ = _make_app(tmp_path, auth_user_id=_SUPABASE_UID, db_name="query_ignored.db")
    with TestClient(app) as client:
        post = client.post("/agent/chat", json={"message": "hi"})
        assert post.status_code == 200
        resp = client.get("/agent/conversations", params={"user_id": _FORGED_UID})
        assert resp.status_code == 200
        convs = resp.json()
        assert len(convs) == 1
        assert convs[0]["user_id"] == _SUPABASE_UID


def _seed_turns_today(url, user_id, n):
    """Seed n user-role messages today for user_id (drives the daily quota)."""
    from app.repositories.conversation import ConversationRepository

    sf = get_session_factory(url)
    repo = ConversationRepository(sf)
    conv = repo.create_conversation(user_id=user_id)
    for i in range(n):
        repo.append_message(conversation_id=conv.id, role="user", content=f"t{i}")


def test_free_quota_enforced_by_jwt_sub(tmp_path):
    """A free user over the daily limit gets 429 — keyed by the JWT sub, even
    though the body carries a different (forged) user_id."""
    from app.core.config import get_settings

    app, url = _make_app(tmp_path, auth_user_id=_SUPABASE_UID, db_name="free_quota.db")
    limit = get_settings().agent_free_daily_turn_limit
    _seed_turns_today(url, _SUPABASE_UID, limit)

    with TestClient(app) as client:
        resp = client.post(
            "/agent/chat", json={"message": "again", "user_id": _FORGED_UID}
        )
    assert resp.status_code == 429, "quota must be keyed on the JWT sub"


def test_premium_quota_bypass_keyed_by_jwt_sub(tmp_path):
    """A premium (JWT sub) user over the free limit is NOT rate-limited."""
    from app.core.config import get_settings

    app, url = _make_app(
        tmp_path, auth_user_id=_SUPABASE_UID, db_name="premium_quota.db"
    )
    limit = get_settings().agent_free_daily_turn_limit
    sf = get_session_factory(url)
    with sf() as s:
        UserRepository(s).upsert_tier(_SUPABASE_UID, "premium")
        s.commit()
    _seed_turns_today(url, _SUPABASE_UID, limit)

    with TestClient(app) as client:
        resp = client.post("/agent/chat", json={"message": "again"})
    assert resp.status_code == 200, "premium must bypass the daily quota"
