"""The /dashboard/agent-runs page: a fresh app + settings per test."""

from datetime import UTC, datetime

from app.core.auth import AuthUser, get_current_user
from app.core.config import Settings
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.seed import seed_all
from app.db.session import get_session
from app.main import create_app
from app.repositories.agent_run import AgentRunRepository
from fastapi.testclient import TestClient


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
    settings = Settings(environment="development")
    with _build_client(tmp_db, monkeypatch, settings) as client:
        # Client build ran create_all + seed, so the table now exists.
        id_a, id_b = _insert_two_runs(tmp_db)
        resp = client.get("/dashboard/agent-runs")
        assert resp.status_code == 200
        body = resp.text
        assert id_a in body
        assert id_b in body
        assert "Last 24h" in body
        assert "flights" in body


def test_agent_runs_page_404_in_production_without_credentials(tmp_db, monkeypatch):
    settings = Settings(
        environment="production",
        cors_origins=["https://app.example.com"],
    )
    with _build_client(tmp_db, monkeypatch, settings) as client:
        assert client.get("/dashboard/agent-runs").status_code == 404
