"""Admin tier endpoint tests — specs/agent-identity-tier Task 2.2.

Verifies:
- admin (role="admin") → 200, tier persisted.
- authenticated non-admin (role="user") → 403.
- no auth (dependency raises AuthError) → 401.
- invalid tier value → 422.

Uses dependency_overrides to inject fake AuthUser (no real JWT minted).
"""

from __future__ import annotations

from app.core.auth import AuthUser, get_current_user
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.session import get_session
from app.exceptions import AuthError
from app.main import create_app
from app.repositories.user import UserRepository
from fastapi.testclient import TestClient


def _make_app(tmp_path):
    url = f"sqlite:///{tmp_path}/admin_test.db"
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
    return app, url


def _auth_override(auth_user: AuthUser):
    def _dep():
        return auth_user

    return _dep


def _unauth_override():
    def _dep():
        raise AuthError("Missing or malformed Authorization header.")

    return _dep


# ---------------------------------------------------------------------------
# Admin → 200
# ---------------------------------------------------------------------------


def test_admin_set_tier_success(tmp_path):
    app, url = _make_app(tmp_path)
    admin_user = AuthUser(
        id="admin-uid", email="admin@example.com", role="admin", claims={}
    )
    app.dependency_overrides[get_current_user] = _auth_override(admin_user)

    with TestClient(app) as client:
        resp = client.patch(
            "/admin/users/target-user-123/tier",
            json={"tier": "premium"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == "target-user-123"
    assert body["tier"] == "premium"

    # Verify persisted
    session_factory = get_session_factory(url)
    with session_factory() as s:
        stored = UserRepository(s).get_tier("target-user-123")
    assert stored == "premium"


def test_admin_set_tier_free(tmp_path):
    app, url = _make_app(tmp_path)
    admin_user = AuthUser(
        id="admin-uid", email="admin@example.com", role="admin", claims={}
    )
    app.dependency_overrides[get_current_user] = _auth_override(admin_user)

    with TestClient(app) as client:
        # first set premium
        client.patch("/admin/users/uid-456/tier", json={"tier": "premium"})
        # then downgrade
        resp = client.patch("/admin/users/uid-456/tier", json={"tier": "free"})

    assert resp.status_code == 200
    assert resp.json()["tier"] == "free"


# ---------------------------------------------------------------------------
# Non-admin authenticated → 403
# ---------------------------------------------------------------------------


def test_non_admin_forbidden(tmp_path):
    app, url = _make_app(tmp_path)
    regular_user = AuthUser(
        id="user-uid", email="user@example.com", role="user", claims={}
    )
    app.dependency_overrides[get_current_user] = _auth_override(regular_user)

    with TestClient(app) as client:
        resp = client.patch(
            "/admin/users/target-user-123/tier",
            json={"tier": "premium"},
        )

    assert resp.status_code == 403


def test_none_role_forbidden(tmp_path):
    app, url = _make_app(tmp_path)
    no_role_user = AuthUser(
        id="norole-uid", email="norole@example.com", role=None, claims={}
    )
    app.dependency_overrides[get_current_user] = _auth_override(no_role_user)

    with TestClient(app) as client:
        resp = client.patch(
            "/admin/users/target-user-123/tier",
            json={"tier": "premium"},
        )

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# No auth → 401
# ---------------------------------------------------------------------------


def test_unauthenticated_returns_401(tmp_path):
    app, url = _make_app(tmp_path)
    app.dependency_overrides[get_current_user] = _unauth_override()

    with TestClient(app) as client:
        resp = client.patch(
            "/admin/users/target-user-123/tier",
            json={"tier": "premium"},
        )

    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Invalid tier → 422
# ---------------------------------------------------------------------------


def test_invalid_tier_value(tmp_path):
    app, url = _make_app(tmp_path)
    admin_user = AuthUser(
        id="admin-uid", email="admin@example.com", role="admin", claims={}
    )
    app.dependency_overrides[get_current_user] = _auth_override(admin_user)

    with TestClient(app) as client:
        resp = client.patch(
            "/admin/users/target-user-123/tier",
            json={"tier": "enterprise"},
        )

    assert resp.status_code == 422
