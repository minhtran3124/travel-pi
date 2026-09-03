"""SC-9: the /dashboard/agent-runs/{run_id} detail page (specs/agent-run-trace-detail).

Renders one turn's call chain behind the dashboard guard. Built like
``test_agent_runs_dashboard.py``: a fresh app + settings per test so the guard's
dev-open vs production-hidden behaviour can be exercised directly.
"""

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

# ``tmp_db`` is shared across the module, so every test uses its own run id.
EMPTY_RUN_ID = "run-detail-empty"


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


def _insert_run(tmp_db, run_id: str, *, steps: bool) -> None:
    """Insert one finished run, optionally with a three-step call chain."""
    factory = get_session_factory(tmp_db)
    with factory() as session:
        repo = AgentRunRepository(session)
        now = datetime.now(UTC).isoformat()
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
                "llm_calls": 2,
                "input_tokens": 1200,
                "output_tokens": 400,
                "cached_tokens": 100,
                "latency_ms": 900,
                "cost_usd": 0.0123,
                "by_model": {
                    "gpt-5-mini": {
                        "calls": 2,
                        "input_tokens": 1200,
                        "output_tokens": 400,
                        "cached_tokens": 100,
                    }
                },
            },
            prompt_versions={"communication_style": 9},
        )
        if steps:
            repo.add_steps(
                run_id,
                [
                    {
                        "seq": 0,
                        "kind": "node",
                        "node": "supervisor",
                        "ns": "",
                        "offset_ms": 0,
                        "ms": 900,
                        "status": "ok",
                    },
                    {
                        "seq": 1,
                        "kind": "llm",
                        "node": "assistant",
                        "ns": "supervisor:1|concierge:2",
                        "model": "gpt-5-mini",
                        "input_tokens": 1200,
                        "output_tokens": 400,
                        "cost_usd": 0.0123,
                        "offset_ms": 10,
                        "ms": 500,
                        "status": "ok",
                    },
                    {
                        "seq": 2,
                        "kind": "tool",
                        "node": "tools",
                        "tool_name": "search_flights",
                        "offset_ms": 520,
                        "ms": 0,
                        "status": "error",
                        "error_type": "TimeoutError",
                    },
                ],
            )
        session.commit()


def test_detail_page_renders_chain_in_dev(tmp_db, monkeypatch):
    settings = Settings(environment="development")
    with _build_client(tmp_db, monkeypatch, settings) as client:
        _insert_run(tmp_db, "run-detail-chain", steps=True)
        resp = client.get("/dashboard/agent-runs/run-detail-chain")
        assert resp.status_code == 200
        body = resp.text
        # Chain rows: a node name, a tool name, the model, and the error marker.
        assert "supervisor" in body
        assert "search_flights" in body
        assert "gpt-5-mini" in body
        assert "TimeoutError" in body
        # Header + totals render.
        assert "completed" in body
        assert "flights" in body


def test_detail_page_prompt_link_carries_version(tmp_db, monkeypatch):
    settings = Settings(environment="development")
    with _build_client(tmp_db, monkeypatch, settings) as client:
        _insert_run(tmp_db, "run-detail-prompt", steps=True)
        body = client.get("/dashboard/agent-runs/run-detail-prompt").text
        assert "/dashboard/prompts/communication_style?version=v9" in body


def test_detail_page_without_steps_renders_note(tmp_db, monkeypatch):
    settings = Settings(environment="development")
    with _build_client(tmp_db, monkeypatch, settings) as client:
        _insert_run(tmp_db, EMPTY_RUN_ID, steps=False)
        resp = client.get(f"/dashboard/agent-runs/{EMPTY_RUN_ID}")
        assert resp.status_code == 200
        assert "No steps recorded for this run" in resp.text


def test_detail_page_404_for_unknown_run(tmp_db, monkeypatch):
    settings = Settings(environment="development")
    with _build_client(tmp_db, monkeypatch, settings) as client:
        assert client.get("/dashboard/agent-runs/nope-1").status_code == 404


def test_detail_page_404_in_production_without_credentials(tmp_db, monkeypatch):
    settings = Settings(
        environment="production",
        cors_origins=["https://app.example.com"],
    )
    with _build_client(tmp_db, monkeypatch, settings) as client:
        _insert_run(tmp_db, "run-detail-prod", steps=True)
        assert client.get("/dashboard/agent-runs/run-detail-prod").status_code == 404
