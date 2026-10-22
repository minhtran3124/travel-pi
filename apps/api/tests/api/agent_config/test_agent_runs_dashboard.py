"""SC-8: the /dashboard/agent-runs page (specs/agent-turn-metrics).

Renders the recent agent runs + 24h / 7d totals behind the dashboard guard.
Built like ``test_dashboard_auth.py``: a fresh app + settings per test so the
guard's login-required behaviour can be exercised directly (specs/dashboard-
auth-required).
"""

from datetime import UTC, datetime

from app.core.auth import AuthUser, get_current_user
from app.core.config import Settings
from app.core.dashboard_auth import SESSION_COOKIE, create_session_token
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.seed import seed_all
from app.db.session import get_session
from app.main import create_app
from app.repositories.agent_run import AgentRunRepository
from fastapi.testclient import TestClient

_DASHBOARD_SECRET = "a" * 64


def _configured_settings(**overrides) -> Settings:
    """A ``Settings`` with dashboard login configured (D4)."""
    return Settings(
        dashboard_basic_user="ops",
        dashboard_basic_password="secret",
        dashboard_secret_key=_DASHBOARD_SECRET,
        **overrides,
    )


def _build_client(tmp_db, monkeypatch, settings: Settings) -> TestClient:
    """Build a TestClient whose dashboard guard reads ``settings``."""
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


def _log_in(client: TestClient, settings: Settings) -> None:
    """Set a valid dashboard session cookie on ``client`` for ``settings``."""
    token = create_session_token(settings.dashboard_basic_user)
    client.cookies[SESSION_COOKIE] = token


def _insert_two_runs(tmp_db) -> tuple[str, str]:
    """Insert two finished agent_runs rows; return their ids."""
    factory = get_session_factory(tmp_db)
    with factory() as session:
        repo = AgentRunRepository(session)
        now = datetime.now(UTC).isoformat()
        for run_id in ("run-alpha-1", "run-beta-2"):
            repo.start(
                run_id,
                user_id="test-user-1",
                conversation_id="conv-1",
                thread_id="thread-1",
                trip_id=None,
                channel="chat",
                kind="turn",
                started_at=now,
            )
            repo.finish(
                run_id,
                status="completed",
                current_flow="flights",
                finished_at=now,
                metrics={
                    "llm_calls": 3,
                    "input_tokens": 1200,
                    "output_tokens": 400,
                    "cached_tokens": 100,
                    "latency_ms": 850,
                    "cost_usd": 0.0123,
                },
            )
        session.commit()
    return "run-alpha-1", "run-beta-2"


def test_agent_runs_page_renders_in_dev(tmp_db, monkeypatch):
    settings = _configured_settings(environment="development")
    with _build_client(tmp_db, monkeypatch, settings) as client:
        _log_in(client, settings)
        # Client build ran create_all + seed, so the table now exists.
        id_a, id_b = _insert_two_runs(tmp_db)
        resp = client.get("/dashboard/agent-runs")
        assert resp.status_code == 200
        body = resp.text
        assert id_a in body
        assert id_b in body
        # A totals field and a per-run field both render.
        assert "Last 24h" in body
        assert "flights" in body


def test_agent_runs_page_redirects_without_cookie(tmp_db, monkeypatch):
    settings = _configured_settings(
        environment="production",
        cors_origins=["https://app.example.com"],
    )
    with _build_client(tmp_db, monkeypatch, settings) as client:
        resp = client.get(
            "/dashboard/agent-runs",
            headers={"accept": "text/html"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"].startswith("/dashboard/login?next=")
