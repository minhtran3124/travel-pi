"""SC-1: session helpers in ``app.core.dashboard_auth`` (specs/dashboard-auth-required).

Pure unit tests — no app, no client. Everything reads settings through
``app.core.dashboard_auth.get_settings`` (D10), so each test monkeypatches
that one name with a ``Settings`` built inline.
"""

import warnings
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from app.core import dashboard_auth as da
from app.core.config import Settings
from fastapi import Response
from starlette.requests import Request

_USER = "ops"
_PW = "s3cret"
_SECRET = "a" * 64


def _settings(**overrides) -> Settings:
    values = {
        "dashboard_basic_user": _USER,
        "dashboard_basic_password": _PW,
        "dashboard_secret_key": _SECRET,
    }
    values.update(overrides)
    # ``_env_file=None`` keeps a developer's apps/api/.env out of these tests.
    if values.get("environment") == "production":
        values.setdefault("cors_origins", ["https://ops.example"])
    return Settings(_env_file=None, **values)


@pytest.fixture
def configured(monkeypatch) -> Settings:
    settings = _settings()
    monkeypatch.setattr(da, "get_settings", lambda: settings)
    return settings


def _use(monkeypatch, settings: Settings) -> None:
    monkeypatch.setattr(da, "get_settings", lambda: settings)


def _request(path: str, query: str = "") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query.encode(),
        "headers": [],
    }
    return Request(scope)


# --- credentials_configured / missing_credentials --------------------------


def test_configured_when_all_three_set(configured):
    assert da.credentials_configured() is True
    assert da.missing_credentials() == []


@pytest.mark.parametrize(
    ("override", "missing"),
    [
        ({"dashboard_basic_user": None}, ["DASHBOARD_BASIC_USER"]),
        ({"dashboard_basic_password": ""}, ["DASHBOARD_BASIC_PASSWORD"]),
        ({"dashboard_secret_key": None}, ["DASHBOARD_SECRET_KEY"]),
    ],
)
def test_unconfigured_when_any_var_missing(monkeypatch, override, missing):
    _use(monkeypatch, _settings(**override))
    assert da.credentials_configured() is False
    assert da.missing_credentials() == missing


def test_unconfigured_when_all_missing(monkeypatch):
    _use(
        monkeypatch,
        _settings(
            dashboard_basic_user=None,
            dashboard_basic_password=None,
            dashboard_secret_key=None,
        ),
    )
    assert da.missing_credentials() == [
        "DASHBOARD_BASIC_USER",
        "DASHBOARD_BASIC_PASSWORD",
        "DASHBOARD_SECRET_KEY",
    ]


def test_short_secret_is_unconfigured_without_key_length_warning(monkeypatch):
    _use(monkeypatch, _settings(dashboard_secret_key="0123456789"))
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert da.credentials_configured() is False
        assert da.missing_credentials() == ["DASHBOARD_SECRET_KEY"]
        with pytest.raises(da.DashboardLoginRequired):
            da.get_current_dashboard_user("not-a-token")


def test_secret_of_exactly_32_bytes_is_configured(monkeypatch):
    _use(monkeypatch, _settings(dashboard_secret_key="b" * 32))
    assert da.credentials_configured() is True


# --- authenticate -----------------------------------------------------------


def test_authenticate_accepts_configured_pair(configured):
    assert da.authenticate(_USER, _PW) is True


@pytest.mark.parametrize(
    ("username", "password"),
    [(_USER, "wrong"), ("nope", _PW), ("", ""), ("opsé", _PW), (_USER, "pâss")],
)
def test_authenticate_rejects(configured, username, password):
    assert da.authenticate(username, password) is False


def test_authenticate_rejects_when_unconfigured(monkeypatch):
    _use(monkeypatch, _settings(dashboard_basic_password=None))
    assert da.authenticate(_USER, _PW) is False


# --- create_session_token / get_current_dashboard_user ----------------------


def test_issued_token_verifies(configured):
    token = da.create_session_token(_USER)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        user = da.get_current_dashboard_user(token)
    assert user == da.DashboardUser(username=_USER)
    claims = jwt.decode(token, _SECRET, algorithms=["HS256"])
    assert claims["exp"] - claims["iat"] == int(da.SESSION_TTL.total_seconds())


def test_missing_cookie_raises(configured):
    with pytest.raises(da.DashboardLoginRequired):
        da.get_current_dashboard_user(None)


def test_valid_token_rejected_when_unconfigured(monkeypatch):
    _use(monkeypatch, _settings())
    token = da.create_session_token(_USER)
    _use(monkeypatch, _settings(dashboard_basic_user=None))
    with pytest.raises(da.DashboardLoginRequired):
        da.get_current_dashboard_user(token)


def test_wrong_key_rejected(configured):
    token = jwt.encode(_claims(), "z" * 64, algorithm="HS256")
    with pytest.raises(da.DashboardLoginRequired):
        da.get_current_dashboard_user(token)


def test_expired_token_rejected(configured):
    token = da.create_session_token(
        _USER, now=_now() - da.SESSION_TTL - timedelta(minutes=5)
    )
    with pytest.raises(da.DashboardLoginRequired):
        da.get_current_dashboard_user(token)


def test_token_within_leeway_still_valid(configured):
    token = da.create_session_token(
        _USER, now=_now() - da.SESSION_TTL + timedelta(seconds=30)
    )
    assert da.get_current_dashboard_user(token).username == _USER


def test_future_iat_rejected(configured):
    token = da.create_session_token(_USER, now=_now() + timedelta(hours=1))
    with pytest.raises(da.DashboardLoginRequired):
        da.get_current_dashboard_user(token)


@pytest.mark.parametrize("dropped", ["exp", "iat", "sub"])
def test_missing_required_claim_rejected(configured, dropped):
    claims = _claims()
    del claims[dropped]
    token = jwt.encode(claims, _SECRET, algorithm="HS256")
    with pytest.raises(da.DashboardLoginRequired):
        da.get_current_dashboard_user(token)


def test_sub_mismatch_rejected(configured):
    token = da.create_session_token("someone-else")
    with pytest.raises(da.DashboardLoginRequired):
        da.get_current_dashboard_user(token)


def test_alg_none_rejected(configured):
    token = jwt.encode(_claims(), key=None, algorithm="none")
    with pytest.raises(da.DashboardLoginRequired):
        da.get_current_dashboard_user(token)


@pytest.mark.parametrize(
    "raw", ["", "abc", "a.b", "a.b.c", "eyJhbGciOiJSUzI1NiJ9.e30.sig"]
)
def test_malformed_token_rejected(configured, raw):
    with pytest.raises(da.DashboardLoginRequired):
        da.get_current_dashboard_user(raw)


def test_login_required_is_an_auth_error():
    from app.exceptions import AuthError

    assert issubclass(da.DashboardLoginRequired, AuthError)
    assert da.DashboardLoginRequired().status_code == 401


# --- safe_next / login_redirect_url ----------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "https://evil.example",
        "//evil.example",
        "/docs",
        "/dashboard/login",
        "/dashboard/login?next=/dashboard",
        "/dashboard\r\nSet-Cookie: x=1",
        "/dashboard\n",
        "dashboard",
    ],
)
def test_safe_next_falls_back(value):
    assert da.safe_next(value) == "/dashboard"


@pytest.mark.parametrize(
    "value",
    [
        "/dashboard",
        "/dashboard/prompts",
        "/dashboard/places?city=Da+Nang",
        "/dashboard/login-log",
    ],
)
def test_safe_next_preserves_dashboard_paths(value):
    assert da.safe_next(value) == value


def test_login_redirect_url_preserves_path_and_query():
    url = da.login_redirect_url(_request("/dashboard/places", "city=Da+Nang&page=2"))
    assert (
        url
        == "/dashboard/login?next=%2Fdashboard%2Fplaces%3Fcity%3DDa%2BNang%26page%3D2"
    )


def test_login_redirect_url_without_query():
    assert (
        da.login_redirect_url(_request("/dashboard"))
        == "/dashboard/login?next=%2Fdashboard"
    )


# --- cookies -----------------------------------------------------------------


def _cookie_header(response: Response) -> str:
    return response.headers["set-cookie"].lower()


def test_set_session_cookie_flags_in_development(configured):
    response = Response()
    da.set_session_cookie(response, "tok")
    header = _cookie_header(response)
    assert header.startswith(f"{da.SESSION_COOKIE}=tok;")
    assert "httponly" in header
    assert "samesite=lax" in header
    assert "path=/dashboard" in header
    assert f"max-age={int(da.SESSION_TTL.total_seconds())}" in header
    assert "secure" not in header


def test_set_session_cookie_secure_in_production(monkeypatch):
    _use(monkeypatch, _settings(environment="production"))
    response = Response()
    da.set_session_cookie(response, "tok")
    assert "secure" in _cookie_header(response)


def test_clear_session_cookie_repeats_path_and_flags(monkeypatch):
    _use(monkeypatch, _settings(environment="production"))
    response = Response()
    da.clear_session_cookie(response)
    header = _cookie_header(response)
    assert header.startswith(f"{da.SESSION_COOKIE}=")
    assert "max-age=0" in header
    assert "path=/dashboard" in header
    assert "httponly" in header
    assert "samesite=lax" in header
    assert "secure" in header


# --- helpers -----------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def _claims() -> dict:
    now = _now()
    return {"sub": _USER, "iat": now, "exp": now + da.SESSION_TTL}
