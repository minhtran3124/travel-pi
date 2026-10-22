"""specs/dashboard-auth-required: the cookie-session guard on /dashboard/*.

Ten cases (design.md -> Tests):

1. test_unconfigured_* (SC-5) - any of the three vars missing, or a <32-byte
   secret, locks the dashboard: GET /dashboard -> 303 to login; POST /login ->
   401 with the not-configured notice; GET /login -> 200 shows the notice.
   Asserted under warnings-as-errors so no InsecureKeyLengthWarning leaks.
2. test_unauth_* (SC-2) - credentials configured, no cookie: HTML request
   redirects with next=; a non-HTML request (Accept: application/json) gets
   the 401 JSON envelope instead.
3. test_login_* (SC-3) - correct login sets the session cookie (HttpOnly,
   SameSite=Lax, Path=/dashboard, Max-Age) and unlocks the dashboard; the
   login page itself redirects away once a valid cookie is present.
4. test_reject_* (SC-4) - wrong credentials, and every kind of bad cookie
   (wrong key, expired, wrong sub, malformed) are all rejected.
5. test_next_* (SC-4) - open-redirect next values collapse to /dashboard; a
   same-site next with a query string is preserved.
6. test_logout_* (SC-6) - logout clears the cookie.
7. test_secure_* (SC-6) - the Secure cookie attribute tracks environment.

This module builds a fresh app + Settings per test (per design.md, D10):
every settings read for this feature goes through
``app.core.dashboard_auth.get_settings``, so monkeypatching that seam (and
``app.main.get_settings`` for docs gating) controls guard, login and logout
alike.
"""

import warnings
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from app.core.auth import AuthUser, get_current_user
from app.core.config import Settings
from app.core.dashboard_auth import SESSION_COOKIE, create_session_token
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.seed import seed_all
from app.db.session import get_session
from app.main import create_app
from fastapi.testclient import TestClient

_USER = "ops"
_PW = "s3cret"
_SECRET = "a" * 64  # 64 hex chars = 32 bytes, PyJWT's minimum before it warns.
_ALGORITHM = "HS256"

_NOT_CONFIGURED_NOTICE = "Dashboard login is not configured on this server"


def _configured_settings(**overrides) -> Settings:
    """A ``Settings`` with dashboard login configured (D4), fields overridable."""
    kwargs = {
        "dashboard_basic_user": _USER,
        "dashboard_basic_password": _PW,
        "dashboard_secret_key": _SECRET,
    }
    kwargs.update(overrides)
    return Settings(**kwargs)


def _build_client(tmp_db, monkeypatch, settings: Settings) -> TestClient:
    """Build a TestClient whose dashboard guard reads ``settings``.

    No lifespan (``TestClient(app)``, not a ``with`` block): these settings
    are sometimes deliberately mis-configured (unconfigured-credentials
    cases), and lifespan startup is not what's under test here.
    """
    Base.metadata.create_all(get_engine(tmp_db), checkfirst=True)
    seed_all(get_session_factory(tmp_db))

    monkeypatch.setattr("app.core.dashboard_auth.get_settings", lambda: settings)
    monkeypatch.setattr("app.main.get_settings", lambda: settings)

    app = create_app()

    def _override_get_session():
        session = get_session_factory(tmp_db)()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_session] = _override_get_session
    app.dependency_overrides[get_current_user] = lambda: AuthUser(
        id="test-user-1", email="test@example.com", role=None, claims={}
    )
    return TestClient(app)


def _forge_token(secret: str, sub: str, now: datetime | None = None) -> str:
    """Build a session JWT directly with ``jwt.encode`` (bypassing create_session_token)."""
    issued = now or datetime.now(UTC)
    claims = {"sub": sub, "iat": issued, "exp": issued + timedelta(hours=12)}
    return jwt.encode(claims, secret, algorithm=_ALGORITHM)


# ---------------------------------------------------------------------------
# SC-5: credentials not configured
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"dashboard_basic_user": None},
        {"dashboard_basic_password": None},
        {"dashboard_secret_key": None},
        {"dashboard_secret_key": "b" * 10},  # 10 bytes, below the 32-byte floor
    ],
    ids=["no-user", "no-password", "no-secret", "short-secret"],
)
def test_unconfigured_locks_dashboard_and_login(tmp_db, monkeypatch, overrides):
    settings = _configured_settings(**overrides)
    client = _build_client(tmp_db, monkeypatch, settings)

    with warnings.catch_warnings():
        warnings.simplefilter("error")

        resp = client.get(
            "/dashboard", headers={"accept": "text/html"}, follow_redirects=False
        )
        assert resp.status_code == 303
        assert resp.headers["location"].startswith("/dashboard/login?next=")

        login_resp = client.post(
            "/dashboard/login",
            data={"username": _USER, "password": _PW},
            follow_redirects=False,
        )
        assert login_resp.status_code == 401
        assert _NOT_CONFIGURED_NOTICE in login_resp.text

        form_resp = client.get("/dashboard/login")
        assert form_resp.status_code == 200
        assert _NOT_CONFIGURED_NOTICE in form_resp.text


# ---------------------------------------------------------------------------
# SC-2: configured, no cookie
# ---------------------------------------------------------------------------


def test_unauth_html_request_redirects_with_next(tmp_db, monkeypatch):
    settings = _configured_settings()
    client = _build_client(tmp_db, monkeypatch, settings)

    resp = client.get(
        "/dashboard/prompts", headers={"accept": "text/html"}, follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard/login?next=%2Fdashboard%2Fprompts"


def test_unauth_json_request_gets_401_envelope(tmp_db, monkeypatch):
    settings = _configured_settings()
    client = _build_client(tmp_db, monkeypatch, settings)

    resp = client.get(
        "/dashboard/_search.json",
        headers={"accept": "application/json"},
        follow_redirects=False,
    )
    assert resp.status_code == 401
    body = resp.json()
    assert body["error"] == "DashboardLoginRequired"
    assert body["status_code"] == 401


# ---------------------------------------------------------------------------
# SC-3: successful login
# ---------------------------------------------------------------------------


def test_login_sets_cookie_and_unlocks_dashboard(tmp_db, monkeypatch):
    settings = _configured_settings()
    client = _build_client(tmp_db, monkeypatch, settings)

    resp = client.post(
        "/dashboard/login",
        data={"username": _USER, "password": _PW},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard"

    set_cookie = resp.headers["set-cookie"]
    assert SESSION_COOKIE in set_cookie
    assert "HttpOnly" in set_cookie
    assert "samesite=lax" in set_cookie.lower()
    assert "Path=/dashboard" in set_cookie
    assert "Max-Age=" in set_cookie

    assert client.get("/dashboard").status_code == 200
    assert client.get("/dashboard/prompts").status_code == 200


def test_login_page_redirects_when_already_signed_in(tmp_db, monkeypatch):
    settings = _configured_settings()
    client = _build_client(tmp_db, monkeypatch, settings)
    client.cookies[SESSION_COOKIE] = create_session_token(_USER)

    resp = client.get("/dashboard/login", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard"


# ---------------------------------------------------------------------------
# SC-4: rejected credentials / cookies
# ---------------------------------------------------------------------------


def test_reject_wrong_password(tmp_db, monkeypatch):
    settings = _configured_settings()
    client = _build_client(tmp_db, monkeypatch, settings)

    resp = client.post(
        "/dashboard/login",
        data={"username": _USER, "password": "wrong"},
        follow_redirects=False,
    )
    assert resp.status_code == 401
    assert "set-cookie" not in resp.headers


def test_reject_wrong_username(tmp_db, monkeypatch):
    settings = _configured_settings()
    client = _build_client(tmp_db, monkeypatch, settings)

    resp = client.post(
        "/dashboard/login",
        data={"username": "nope", "password": _PW},
        follow_redirects=False,
    )
    assert resp.status_code == 401
    assert "set-cookie" not in resp.headers


def test_reject_token_signed_with_different_key(tmp_db, monkeypatch):
    settings = _configured_settings()
    client = _build_client(tmp_db, monkeypatch, settings)
    client.cookies[SESSION_COOKIE] = _forge_token("b" * 64, _USER)

    resp = client.get(
        "/dashboard", headers={"accept": "text/html"}, follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/dashboard/login?next=")


def test_reject_expired_token(tmp_db, monkeypatch):
    settings = _configured_settings()
    client = _build_client(tmp_db, monkeypatch, settings)
    long_ago = datetime.now(UTC) - timedelta(hours=13)
    client.cookies[SESSION_COOKIE] = _forge_token(_SECRET, _USER, now=long_ago)

    resp = client.get(
        "/dashboard", headers={"accept": "text/html"}, follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/dashboard/login?next=")


def test_reject_token_with_mismatched_sub(tmp_db, monkeypatch):
    settings = _configured_settings()
    client = _build_client(tmp_db, monkeypatch, settings)
    client.cookies[SESSION_COOKIE] = _forge_token(_SECRET, "someone-else")

    resp = client.get(
        "/dashboard", headers={"accept": "text/html"}, follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/dashboard/login?next=")


@pytest.mark.parametrize(
    "bad_value",
    [
        "abc",
        "a.b",
        # A Supabase-shaped RS256 token (three base64url segments); still
        # rejected because algorithms is pinned to ["HS256"].
        "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiJvcHMiLCJpYXQiOjE3MDAwMDAwMDAsImV4cCI6MTcwMDA0MzYwMH0."
        "c2lnbmF0dXJlLWxvb2tzLXJlYWwtYnV0LWlzbnQ",
    ],
    ids=["short", "two-part", "rs256-shaped"],
)
def test_reject_malformed_cookie(tmp_db, monkeypatch, bad_value):
    settings = _configured_settings()
    client = _build_client(tmp_db, monkeypatch, settings)
    client.cookies[SESSION_COOKIE] = bad_value

    resp = client.get(
        "/dashboard", headers={"accept": "text/html"}, follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/dashboard/login?next=")


# ---------------------------------------------------------------------------
# SC-4: `next` sanitisation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "next_value",
    [
        "https://evil.example",
        "//evil.example",
        "/docs",
        "/dashboard/login",
    ],
    ids=["absolute-url", "protocol-relative", "off-site-path", "login-path"],
)
def test_next_open_redirect_collapses_to_dashboard(tmp_db, monkeypatch, next_value):
    settings = _configured_settings()
    client = _build_client(tmp_db, monkeypatch, settings)

    resp = client.post(
        "/dashboard/login",
        params={"next": next_value},
        data={"username": _USER, "password": _PW},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard"


def test_next_same_site_path_with_query_is_preserved(tmp_db, monkeypatch):
    settings = _configured_settings()
    client = _build_client(tmp_db, monkeypatch, settings)

    resp = client.post(
        "/dashboard/login",
        params={"next": "/dashboard/places?city=Da+Nang"},
        data={"username": _USER, "password": _PW},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard/places?city=Da+Nang"


# ---------------------------------------------------------------------------
# SC-6: logout + Secure cookie attribute
# ---------------------------------------------------------------------------


def test_logout_clears_cookie_and_relocks_dashboard(tmp_db, monkeypatch):
    settings = _configured_settings()
    client = _build_client(tmp_db, monkeypatch, settings)
    client.cookies[SESSION_COOKIE] = create_session_token(_USER)
    assert client.get("/dashboard").status_code == 200

    resp = client.post("/dashboard/logout", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard/login"

    client.cookies.clear()
    still_locked = client.get(
        "/dashboard", headers={"accept": "text/html"}, follow_redirects=False
    )
    assert still_locked.status_code == 303


def test_secure_attribute_present_in_production(tmp_db, monkeypatch):
    settings = _configured_settings(
        environment="production",
        cors_origins=["https://app.example.com"],
    )
    client = _build_client(tmp_db, monkeypatch, settings)

    resp = client.post(
        "/dashboard/login",
        data={"username": _USER, "password": _PW},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "Secure" in resp.headers["set-cookie"]


def test_secure_attribute_absent_in_development(tmp_db, monkeypatch):
    settings = _configured_settings(environment="development")
    client = _build_client(tmp_db, monkeypatch, settings)

    resp = client.post(
        "/dashboard/login",
        data={"username": _USER, "password": _PW},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "Secure" not in resp.headers["set-cookie"]
