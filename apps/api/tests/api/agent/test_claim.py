"""Claim-history endpoint tests — specs/agent-identity-tier Task 5.1.

POST /agent/conversations/claim reassigns conversations owned by an anonymous
localStorage id to the authenticated user's Supabase id.

Verifies:
- Authed claim: 2 anon conversations → claimed=2; appear under sub, gone from anon.
- Idempotent second claim: → claimed=0.
- No-op when anonymous_user_id == sub: → claimed=0.
- Source is a registered account (has a users row): → 403.
- Unauthenticated request: → 401.

Uses FakeLLM graph + dependency_overrides (mirrors test_identity_hybrid.py harness).
No real JWT minted — get_current_user is overridden to inject a fake AuthUser.
"""

from __future__ import annotations

from app.core.auth import AuthUser, get_current_user
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.session import get_session
from app.main import create_app
from app.repositories.conversation import ConversationRepository
from app.repositories.user import UserRepository
from app.routers.agent import get_travel_graph
from fastapi.testclient import TestClient

_SUPABASE_UID = "supabase-claim-uid"
_ANON_UID = "anon-local-uuid-claim"
_OTHER_REGISTERED_UID = "other-registered-user-uid"


def _make_app(tmp_path, *, db_name: str):
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

    # No graph needed for the claim endpoint, but the router dependency is
    # registered; override it to avoid startup errors.
    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_travel_graph] = lambda: None
    return app, url


def _auth_override(auth_user: AuthUser):
    """Dependency override that returns a fixed AuthUser (simulates a valid JWT)."""

    def _dep():
        return auth_user

    return _dep


def _seed_conversations(url: str, user_id: str, n: int) -> list[str]:
    """Seed *n* conversations for *user_id*; return their ids."""
    sf = get_session_factory(url)
    repo = ConversationRepository(sf)
    return [repo.create_conversation(user_id=user_id).id for _ in range(n)]


# ---------------------------------------------------------------------------
# Authed claim — happy path
# ---------------------------------------------------------------------------


def test_authed_claim_reassigns_anon_conversations(tmp_path):
    """Authed claim: 2 anon conversations become owned by the JWT sub."""
    app, url = _make_app(tmp_path, db_name="claim_happy.db")
    fake_auth = AuthUser(id=_SUPABASE_UID, email="u@test.com", role=None, claims={})
    app.dependency_overrides[get_current_user] = _auth_override(fake_auth)

    _seed_conversations(url, _ANON_UID, 2)

    with TestClient(app) as client:
        resp = client.post(
            "/agent/conversations/claim",
            json={"anonymous_user_id": _ANON_UID},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["claimed"] == 2

    # Verify DB: conversations now under sub, none under anon.
    sf = get_session_factory(url)
    repo = ConversationRepository(sf)
    assert len(repo.list_for_user(_SUPABASE_UID)) == 2
    assert repo.list_for_user(_ANON_UID) == []


# ---------------------------------------------------------------------------
# Idempotent second claim
# ---------------------------------------------------------------------------


def test_idempotent_second_claim(tmp_path):
    """Second claim after the first returns claimed=0 (no conversations left under anon)."""
    app, url = _make_app(tmp_path, db_name="claim_idempotent.db")
    fake_auth = AuthUser(id=_SUPABASE_UID, email="u@test.com", role=None, claims={})
    app.dependency_overrides[get_current_user] = _auth_override(fake_auth)

    _seed_conversations(url, _ANON_UID, 1)

    with TestClient(app) as client:
        first = client.post(
            "/agent/conversations/claim",
            json={"anonymous_user_id": _ANON_UID},
        )
        assert first.status_code == 200
        assert first.json()["claimed"] == 1

        second = client.post(
            "/agent/conversations/claim",
            json={"anonymous_user_id": _ANON_UID},
        )
        assert second.status_code == 200
        assert second.json()["claimed"] == 0


# ---------------------------------------------------------------------------
# No-op when anonymous_user_id == sub
# ---------------------------------------------------------------------------


def test_noop_when_anon_equals_sub(tmp_path):
    """anonymous_user_id == JWT sub → claimed=0 (no self-claim needed)."""
    app, url = _make_app(tmp_path, db_name="claim_noop.db")
    fake_auth = AuthUser(id=_SUPABASE_UID, email="u@test.com", role=None, claims={})
    app.dependency_overrides[get_current_user] = _auth_override(fake_auth)

    with TestClient(app) as client:
        resp = client.post(
            "/agent/conversations/claim",
            json={"anonymous_user_id": _SUPABASE_UID},
        )

    assert resp.status_code == 200
    assert resp.json()["claimed"] == 0


# ---------------------------------------------------------------------------
# Source is a registered account → 403
# ---------------------------------------------------------------------------


def test_claim_from_registered_account_is_forbidden(tmp_path):
    """Source id has a users row (registered account) → 403 to prevent history theft."""
    app, url = _make_app(tmp_path, db_name="claim_403.db")
    fake_auth = AuthUser(id=_SUPABASE_UID, email="u@test.com", role=None, claims={})
    app.dependency_overrides[get_current_user] = _auth_override(fake_auth)

    # Seed a users row for the source id — makes it a registered account.
    sf = get_session_factory(url)
    with sf() as s:
        UserRepository(s).upsert_tier(_OTHER_REGISTERED_UID, "free")
        s.commit()

    with TestClient(app) as client:
        resp = client.post(
            "/agent/conversations/claim",
            json={"anonymous_user_id": _OTHER_REGISTERED_UID},
        )

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Unauthenticated → 401
# ---------------------------------------------------------------------------


def test_unauthenticated_claim_is_401(tmp_path):
    """No auth override → the required get_current_user dep raises AuthError → 401."""
    app, url = _make_app(tmp_path, db_name="claim_401.db")
    # Do NOT override get_current_user; the required dep will raise AuthError (401).

    with TestClient(app) as client:
        resp = client.post(
            "/agent/conversations/claim",
            json={"anonymous_user_id": _ANON_UID},
        )

    assert resp.status_code == 401
