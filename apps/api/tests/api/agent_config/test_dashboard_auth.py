"""The /dashboard/* guard: each state needs its own Settings + fresh app."""

import pytest
from app.core.auth import AuthUser, get_current_user
from app.core.config import Settings
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.seed import seed_all
from app.db.session import get_session
from app.main import create_app
from fastapi.testclient import TestClient

_USER = "ops"
_PW = "s3cret"


def _build_client(tmp_db, monkeypatch, settings: Settings) -> TestClient:
    """Build a TestClient whose dashboard guard reads ``settings``."""
    Base.metadata.create_all(get_engine(tmp_db), checkfirst=True)
    seed_all(get_session_factory(tmp_db))

    monkeypatch.setattr("app.core.dashboard_auth.get_settings", lambda: settings)
    # create_app also reads settings (docs gating); keep it in the same mode.
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


def test_production_without_credentials_returns_404(tmp_db, monkeypatch):
    settings = Settings(
        environment="production",
        cors_origins=["https://app.example.com"],
    )
    with _build_client(tmp_db, monkeypatch, settings) as client:
        assert client.get("/dashboard/agent-config").status_code == 404
        assert client.get("/dashboard/_search.json").status_code == 404
        assert client.get("/dashboard/prompts").status_code == 404


def test_credentials_configured_but_absent_returns_401(tmp_db, monkeypatch):
    settings = Settings(
        dashboard_basic_user=_USER,
        dashboard_basic_password=_PW,
    )
    with _build_client(tmp_db, monkeypatch, settings) as client:
        resp = client.get("/dashboard/agent-config")
        assert resp.status_code == 401
        assert resp.headers["WWW-Authenticate"] == "Basic"


def test_credentials_configured_but_wrong_returns_401(tmp_db, monkeypatch):
    settings = Settings(
        dashboard_basic_user=_USER,
        dashboard_basic_password=_PW,
    )
    with _build_client(tmp_db, monkeypatch, settings) as client:
        resp = client.get("/dashboard/agent-config", auth=(_USER, "wrong"))
        assert resp.status_code == 401
        assert resp.headers["WWW-Authenticate"] == "Basic"
        resp2 = client.get("/dashboard/agent-config", auth=("nope", _PW))
        assert resp2.status_code == 401


def test_non_ascii_credentials_return_401_not_500(tmp_db, monkeypatch):
    # A non-ASCII Basic credential makes secrets.compare_digest raise TypeError;
    # the guard must read it as "wrong" (401), never surface a 500.
    settings = Settings(
        dashboard_basic_user=_USER,
        dashboard_basic_password=_PW,
    )
    with _build_client(tmp_db, monkeypatch, settings) as client:
        resp = client.get("/dashboard/agent-config", auth=("óps", "pä ss"))
        assert resp.status_code == 401
        assert resp.headers["WWW-Authenticate"] == "Basic"


def test_valid_basic_credentials_return_200(tmp_db, monkeypatch):
    settings = Settings(
        dashboard_basic_user=_USER,
        dashboard_basic_password=_PW,
    )
    with _build_client(tmp_db, monkeypatch, settings) as client:
        resp = client.get("/dashboard/agent-config", auth=(_USER, _PW))
        assert resp.status_code == 200
        assert "agent" in resp.text.lower()


def test_development_without_credentials_is_open(tmp_db, monkeypatch):
    settings = Settings(environment="development")
    with _build_client(tmp_db, monkeypatch, settings) as client:
        assert client.get("/dashboard/agent-config").status_code == 200
        assert client.get("/dashboard/_search.json").status_code == 200


@pytest.mark.parametrize("path", ["/dashboard/_search.json", "/dashboard/prompts"])
def test_valid_credentials_reach_all_dashboard_routes(tmp_db, monkeypatch, path):
    settings = Settings(
        dashboard_basic_user=_USER,
        dashboard_basic_password=_PW,
    )
    with _build_client(tmp_db, monkeypatch, settings) as client:
        assert client.get(path).status_code == 401
        assert client.get(path, auth=(_USER, _PW)).status_code == 200
