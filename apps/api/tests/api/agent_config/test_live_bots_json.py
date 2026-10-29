"""GET /dashboard/live-bots.json: live runs behind the dashboard login (SQLite)."""

from datetime import UTC, datetime, timedelta

import pytest
from app.core.auth import AuthUser, get_current_user
from app.core.config import Settings
from app.core.dashboard_auth import SESSION_COOKIE, create_session_token
from app.db import models
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.session import get_session
from app.main import create_app
from app.repositories.agent_run import AgentRunRepository
from fastapi.testclient import TestClient

_SECRET = "a" * 64
_URL = "/dashboard/live-bots.json"


def _settings(**overrides) -> Settings:
    return Settings(
        dashboard_basic_user="ops",
        dashboard_basic_password="secret",
        dashboard_secret_key=_SECRET,
        **overrides,
    )


@pytest.fixture
def env(tmp_db, monkeypatch):
    Base.metadata.create_all(get_engine(tmp_db), checkfirst=True)
    factory = get_session_factory(tmp_db)
    with factory() as s:  # tmp_db is session-scoped: start every test from empty
        s.query(models.AgentRunStep).delete()
        s.query(models.AgentRun).delete()
        s.commit()
    settings = _settings(environment="development")
    monkeypatch.setattr("app.core.dashboard_auth.get_settings", lambda: settings)
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    monkeypatch.setattr("app.routers.dashboard.get_settings", lambda: settings)
    app = create_app()

    def _session():
        session = factory()
        try:
            yield session
            session.commit()
        finally:
            session.close()

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: AuthUser(
        id="u", email="e@x.com", role=None, claims={}
    )
    with TestClient(app) as client:
        client.cookies[SESSION_COOKIE] = create_session_token("ops")
        yield client, factory


def _add(factory, run_id, *, ago_s=10, status="running", finished_ago_s=None, **kw):
    now = datetime.now(UTC)
    with factory() as s:
        repo = AgentRunRepository(s)
        repo.start(
            run_id,
            user_id=kw.pop("user_id", "alice@example.com"),
            conversation_id="c",
            thread_id="t",
            trip_id=None,
            channel=kw.pop("channel", "chat"),
            kind="turn",
            started_at=(now - timedelta(seconds=ago_s)).isoformat(),
        )
        if status != "running":
            repo.finish(
                run_id,
                status=status,
                current_flow=kw.pop("flow", "planner"),
                finished_at=(now - timedelta(seconds=finished_ago_s or 0)).isoformat(),
                metrics={"llm_calls": 2, "input_tokens": 10, "output_tokens": 5},
            )
        if kw.get("steps"):
            repo.add_steps(run_id, kw["steps"])
        s.commit()


def _ids(resp):
    return [b["id"] for b in resp.json()["bots"]]


def test_shape_headers_and_empty(env):
    client, _ = env
    resp = client.get(_URL)
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "no-store"
    body = resp.json()
    assert body["bots"] == []
    assert body["counts"] == {
        "running": 0,
        "waiting": 0,
        "retrying": 0,
        "done_today": 0,
    }
    assert "generated_at" in body


def test_running_interrupted_and_latest_step(env):
    client, factory = env
    steps = [
        {"seq": 0, "kind": "node", "node": "supervisor", "status": "ok"},
        {
            "seq": 1,
            "kind": "tool",
            "node": "tools",
            "tool_name": "search_flights",
            "status": "ok",
        },
    ]
    _add(factory, "run-a", steps=steps)
    _add(factory, "run-b", status="interrupted", ago_s=20)
    body = client.get(_URL).json()
    by_id = {b["id"]: b for b in body["bots"]}
    assert by_id["run-a"]["state"] == "running"
    assert by_id["run-a"]["stage"] == 2
    assert by_id["run-a"]["step"] == "search_flights"
    assert by_id["run-b"]["state"] == "waiting"
    assert _ids(client.get(_URL)) == ["run-a", "run-b"]  # newest first
    assert body["counts"]["running"] == 1
    assert body["counts"]["waiting"] == 1


def test_recently_finished_included_old_finished_not(env):
    client, factory = env
    _add(factory, "just-done", status="completed", ago_s=30, finished_ago_s=2)
    _add(factory, "long-done", status="completed", ago_s=300, finished_ago_s=120)
    _add(factory, "just-failed", status="failed", ago_s=30, finished_ago_s=3)
    body = client.get(_URL).json()
    states = {b["id"]: b["state"] for b in body["bots"]}
    assert states == {"just-done": "done", "just-failed": "failed"}
    assert body["counts"]["done_today"] >= 1


def test_cap_at_fifty(env):
    client, factory = env
    for i in range(55):
        _add(factory, f"cap-{i:02d}", ago_s=100 - i)
    assert len(client.get(_URL).json()["bots"]) == 50


def test_stale_flag_uses_research_timeout(env):
    client, factory = env
    _add(factory, "old-run", ago_s=700)
    _add(factory, "new-run", ago_s=5)
    by_id = {b["id"]: b for b in client.get(_URL).json()["bots"]}
    assert by_id["old-run"]["stale"] is True
    assert by_id["new-run"]["stale"] is False


def test_user_is_anonymised(env):
    client, factory = env
    _add(factory, "anon-run", user_id="alice@example.com")
    text = client.get(_URL).text
    assert "alice" not in text
    assert "example.com" not in text


def test_research_channel_bot(env):
    client, factory = env
    _add(factory, "res-run", channel="research")
    assert client.get(_URL).json()["bots"][0]["bot"] == "research"


def test_requires_dashboard_login(env):
    client, _ = env
    client.cookies.clear()
    resp = client.get(_URL, headers={"accept": "text/html"}, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/dashboard/login")
    resp = client.get(
        _URL, headers={"accept": "application/json"}, follow_redirects=False
    )
    assert resp.status_code == 401
