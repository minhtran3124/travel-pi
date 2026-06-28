"""Hybrid identity tests — specs/agent-identity-tier Task 1.1.

Verifies:
- Anonymous (no token): turn works, conversation keyed by body.user_id, tier free.
- Authenticated: conversation + messages keyed by JWT sub (not body.user_id); a
  users row is lazy-created on first call.
- Forged body.user_id is ignored when a valid token is present.
- Tier resolves from the authed id (seed a premium row → premium).

Uses FakeLLM graph + dependency_overrides for get_session / get_travel_graph.
The authenticated "token" is simulated by overriding get_current_user_optional
to return a fixed AuthUser — no real JWT minted.
"""

from __future__ import annotations

from app.agents.graph import build_graph
from app.agents.supervisor import SupervisorIntent
from app.clients.llm import FakeLLM
from app.core.auth import AuthUser, get_current_user_optional
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
_ANON_UID = "anon-local-uuid-xyz"
_FORGED_UID = "forged-other-user"


def _make_app(tmp_path, *, db_name: str = "identity.db"):
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
    return app, url


def _auth_override(auth_user: AuthUser):
    """Return a dependency override that always yields the given AuthUser."""

    def _dep():
        return auth_user

    return _dep


# ---------------------------------------------------------------------------
# Anonymous path
# ---------------------------------------------------------------------------


def test_anonymous_turn_works_as_free(tmp_path):
    """No token → turn succeeds, conversation is keyed by body.user_id, tier free."""
    app, _ = _make_app(tmp_path, db_name="anon.db")

    with TestClient(app) as client:
        resp = client.post(
            "/agent/chat",
            json={"message": "Hello", "user_id": _ANON_UID},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["reply"]  # non-empty reply


def test_anonymous_conversation_keyed_by_body_user_id(tmp_path):
    """Anonymous: conversations listed under body.user_id, not some other id."""
    app, _ = _make_app(tmp_path, db_name="anon_conv.db")

    with TestClient(app) as client:
        post_resp = client.post(
            "/agent/chat",
            json={"message": "Hello", "user_id": _ANON_UID},
        )
        assert post_resp.status_code == 200

        conv_resp = client.get("/agent/conversations", params={"user_id": _ANON_UID})
        assert conv_resp.status_code == 200
        convs = conv_resp.json()
        assert len(convs) == 1
        assert convs[0]["user_id"] == _ANON_UID


# ---------------------------------------------------------------------------
# Authenticated path
# ---------------------------------------------------------------------------


def test_authed_turn_uses_jwt_sub(tmp_path):
    """Authenticated: conversation is keyed by JWT sub, not body.user_id."""
    app, url = _make_app(tmp_path, db_name="authed.db")
    fake_auth = AuthUser(id=_SUPABASE_UID, email="user@test.com", role=None, claims={})
    app.dependency_overrides[get_current_user_optional] = _auth_override(fake_auth)

    with TestClient(app) as client:
        resp = client.post(
            "/agent/chat",
            # body.user_id is the anonymous fallback; must be ignored when authed
            json={"message": "Hello", "user_id": _ANON_UID},
        )
        assert resp.status_code == 200

        conv_resp = client.get(
            "/agent/conversations", params={"user_id": _SUPABASE_UID}
        )
        assert conv_resp.status_code == 200
        convs = conv_resp.json()
        assert len(convs) == 1
        assert convs[0]["user_id"] == _SUPABASE_UID


def test_authed_turn_lazy_creates_users_row(tmp_path):
    """Authenticated call must insert a users row for the Supabase id."""
    app, url = _make_app(tmp_path, db_name="lazy_create.db")
    fake_auth = AuthUser(id=_SUPABASE_UID, email="user@test.com", role=None, claims={})
    app.dependency_overrides[get_current_user_optional] = _auth_override(fake_auth)

    with TestClient(app) as client:
        resp = client.post(
            "/agent/chat",
            json={"message": "Hello", "user_id": _ANON_UID},
        )
        assert resp.status_code == 200

    # Inspect the DB directly — the users row must exist after the turn.
    sf = get_session_factory(url)
    with sf() as s:
        tier = UserRepository(s).get_tier(_SUPABASE_UID)
    assert tier == "free"


def test_forged_body_user_id_ignored_when_authed(tmp_path):
    """When a valid JWT is present, body.user_id is ignored (anti-spoof).

    The POST sends body.user_id=forged-uid but the router must use the JWT sub.
    Verified by inspecting the conversation's user_id in the DB directly (avoids
    the auth override affecting the GET query as well).
    """
    from app.db import models

    app, url = _make_app(tmp_path, db_name="antispoof.db")
    fake_auth = AuthUser(id=_SUPABASE_UID, email="user@test.com", role=None, claims={})
    app.dependency_overrides[get_current_user_optional] = _auth_override(fake_auth)

    with TestClient(app) as client:
        resp = client.post(
            "/agent/chat",
            # attempt to forge a different user's id
            json={"message": "Hello", "user_id": _FORGED_UID},
        )
        assert resp.status_code == 200

    # Inspect the DB directly: conversation must be keyed by JWT sub, not forged id.
    sf = get_session_factory(url)
    with sf() as s:
        real_convs = (
            s.query(models.Conversation)
            .filter(models.Conversation.user_id == _SUPABASE_UID)
            .all()
        )
        forged_convs = (
            s.query(models.Conversation)
            .filter(models.Conversation.user_id == _FORGED_UID)
            .all()
        )

    assert len(real_convs) == 1, "conversation must exist under the JWT sub"
    assert forged_convs == [], "forged body.user_id must not create any conversation"


def test_tier_resolves_from_authed_id(tmp_path):
    """Seed a premium row for the JWT sub → tier resolves to premium."""
    app, url = _make_app(tmp_path, db_name="tier.db")

    # Pre-seed a premium tier for the Supabase user.
    sf = get_session_factory(url)
    with sf() as s:
        UserRepository(s).upsert_tier(_SUPABASE_UID, "premium")
        s.commit()

    fake_auth = AuthUser(id=_SUPABASE_UID, email="user@test.com", role=None, claims={})
    app.dependency_overrides[get_current_user_optional] = _auth_override(fake_auth)

    import app.routers.agent as agent_router

    calls: list[dict] = []
    real_resolve = agent_router.resolve_agent_context

    def spy(*, tier, mode):
        calls.append({"tier": tier, "mode": mode})
        return real_resolve(tier=tier, mode=mode)

    # Patch resolve_agent_context to capture the tier passed by the router.
    original = agent_router.resolve_agent_context
    agent_router.resolve_agent_context = spy
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/agent/chat",
                json={"message": "Hello", "user_id": _ANON_UID},
            )
        assert resp.status_code == 200
    finally:
        agent_router.resolve_agent_context = original

    assert calls, "resolve_agent_context must be called"
    assert calls[-1]["tier"] == "premium", (
        "tier must come from the DB row for the JWT sub, not default free"
    )


# ---------------------------------------------------------------------------
# Cross-cutting: tier + quota by authenticated identity (Task 4.1)
# ---------------------------------------------------------------------------


def _seed_turns_today(url, user_id, n):
    """Seed n user-role messages today for user_id (drives the daily quota)."""
    from app.repositories.conversation import ConversationRepository

    sf = get_session_factory(url)
    repo = ConversationRepository(sf)
    conv = repo.create_conversation(user_id=user_id)
    for i in range(n):
        repo.append_message(conversation_id=conv.id, role="user", content=f"t{i}")


def test_authed_premium_bypasses_quota(tmp_path):
    """A premium (logged-in) user over the free daily limit is NOT rate-limited."""
    from app.core.config import get_settings

    app, url = _make_app(tmp_path, db_name="premium_quota.db")
    limit = get_settings().agent_free_daily_turn_limit
    sf = get_session_factory(url)
    with sf() as s:
        UserRepository(s).upsert_tier(_SUPABASE_UID, "premium")
        s.commit()
    _seed_turns_today(url, _SUPABASE_UID, limit)  # at/over the free limit

    fake_auth = AuthUser(id=_SUPABASE_UID, email="u@test.com", role=None, claims={})
    app.dependency_overrides[get_current_user_optional] = _auth_override(fake_auth)

    with TestClient(app) as client:
        resp = client.post(
            "/agent/chat", json={"message": "again", "user_id": _ANON_UID}
        )
    assert resp.status_code == 200, "premium must bypass the daily quota"


def test_authed_free_quota_enforced_by_jwt_sub(tmp_path):
    """A free (logged-in) user over the daily limit gets 429, keyed by JWT sub."""
    from app.core.config import get_settings

    app, url = _make_app(tmp_path, db_name="free_quota.db")
    limit = get_settings().agent_free_daily_turn_limit
    _seed_turns_today(url, _SUPABASE_UID, limit)  # no premium row → free

    fake_auth = AuthUser(id=_SUPABASE_UID, email="u@test.com", role=None, claims={})
    app.dependency_overrides[get_current_user_optional] = _auth_override(fake_auth)

    with TestClient(app) as client:
        resp = client.post(
            "/agent/chat", json={"message": "again", "user_id": _ANON_UID}
        )
    assert resp.status_code == 429, "free user over the limit must be rate-limited"
