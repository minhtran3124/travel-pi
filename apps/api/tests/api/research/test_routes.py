"""SC-14: research routes with the flag on — start, tier/ownership gates, conflict,
rate limit, and status.
"""

from __future__ import annotations

import pytest
from app.core.config import get_settings
from fastapi.testclient import TestClient

from tests.api.research import USER_ID, build_app, create_trip, insert_run


@pytest.fixture(autouse=True)
def _enabled(monkeypatch):
    monkeypatch.setenv("RESEARCH_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_start_returns_202_with_run_id(tmp_path):
    app, url, _store = build_app(tmp_path)
    create_trip(url, "t1", USER_ID)
    client = TestClient(app)

    resp = client.post("/agent/trips/t1/research", json={"instruction": "focus stays"})
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["run_id"]
    assert body["thread_turn"] == 1


def test_start_free_tier_is_403(tmp_path):
    app, url, _store = build_app(tmp_path, premium=False)
    create_trip(url, "t1", USER_ID)
    client = TestClient(app)

    resp = client.post("/agent/trips/t1/research", json={})
    assert resp.status_code == 403, resp.text


def test_start_foreign_trip_is_403(tmp_path):
    app, url, _store = build_app(tmp_path)
    # Trip belongs to someone else; the caller (u1) must not learn it exists.
    create_trip(url, "t1", "someone-else")
    client = TestClient(app)

    resp = client.post("/agent/trips/t1/research", json={})
    assert resp.status_code == 403, resp.text


def test_start_conflicts_while_one_running(tmp_path):
    app, url, _store = build_app(tmp_path)
    create_trip(url, "t1", USER_ID)
    insert_run(url, "existing-run", USER_ID, "t1", status="running")
    # Live: this process is driving it.
    app.state.research_bus.open("existing-run")
    client = TestClient(app)

    resp = client.post("/agent/trips/t1/research", json={})
    assert resp.status_code == 409, resp.text


def test_start_resumes_a_run_left_running_by_a_dead_process(tmp_path):
    """A row still ``running`` that no process here is driving (a restart landed
    mid-run, inside the stale window the startup sweep skips) must not 409 the
    trip until the next restart: the start resumes it under a new run."""
    app, url, _store = build_app(tmp_path)
    create_trip(url, "t1", USER_ID)
    insert_run(url, "orphan-run", USER_ID, "t1", status="running")
    client = TestClient(app)

    resp = client.post("/agent/trips/t1/research", json={})
    assert resp.status_code == 202, resp.text
    assert resp.json()["run_id"] != "orphan-run"
    assert client.get("/agent/research/orphan-run").json()["status"] == "interrupted"


def test_fourth_start_in_a_day_is_429(tmp_path):
    app, url, _store = build_app(tmp_path)
    create_trip(url, "t1", USER_ID)
    client = TestClient(app)

    # Each start's background runner completes the run, so the next start is not a
    # 409 conflict; the 4th trips the research_start daily cap (default 3).
    for _ in range(3):
        assert client.post("/agent/trips/t1/research", json={}).status_code == 202
    resp = client.post("/agent/trips/t1/research", json={})
    assert resp.status_code == 429, resp.text


def test_status_returns_state_files_and_proposal_flag(tmp_path):
    app, url, store = build_app(tmp_path)
    create_trip(url, "t1", USER_ID)
    insert_run(url, "run-1", USER_ID, "t1", status="completed")
    # Seed a dossier file + proposal into the (fake agent's) store.
    ns = ("users", USER_ID, "research", "t1")
    store.put(ns, "/flights.md", {"content": "FL"})
    store.put(ns, "/proposal.json", {"content": "{}"})
    client = TestClient(app)

    resp = client.get("/agent/research/run-1")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "completed"
    assert body["files"] == ["/flights.md", "/proposal.json"]
    assert body["proposal_ready"] is True


def test_status_foreign_run_is_404(tmp_path):
    app, url, _store = build_app(tmp_path)
    insert_run(url, "run-x", "someone-else", "t1", status="completed")
    client = TestClient(app)

    resp = client.get("/agent/research/run-x")
    assert resp.status_code == 404, resp.text


def test_revise_counts_against_the_daily_cap(tmp_path):
    """A revise books a full run, so it spends the same ``research_start`` cap as a
    start (design §5); without that, one completed dossier revised over and over is
    an unbounded run launcher."""
    app, url, _store = build_app(tmp_path)
    create_trip(url, "t1", USER_ID)
    client = TestClient(app)

    run_id = client.post("/agent/trips/t1/research", json={}).json()["run_id"]
    for _ in range(2):
        resp = client.post(f"/agent/research/{run_id}/revise", json={})
        assert resp.status_code == 202, resp.text
        run_id = resp.json()["run_id"]

    resp = client.post(f"/agent/research/{run_id}/revise", json={})
    assert resp.status_code == 429, resp.text
    assert client.post("/agent/trips/t1/research", json={}).status_code == 429
