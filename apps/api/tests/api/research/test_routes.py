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


def test_start_passes_the_departure_point_to_the_run(tmp_path, monkeypatch):
    from app.research.service import ResearchService

    seen: dict = {}

    async def fake_launch(self, run_id, user_id, trip_id, **kwargs):
        seen.update(kwargs)

    monkeypatch.setattr(ResearchService, "launch", fake_launch)
    app, url, _store = build_app(tmp_path)
    create_trip(url, "t1", USER_ID)
    client = TestClient(app)

    resp = client.post("/agent/trips/t1/research", json={"origin": "Ho Chi Minh City"})

    assert resp.status_code == 202, resp.text
    assert seen["origin"] == "Ho Chi Minh City"


def test_revise_forwards_origin_and_language_to_the_run(tmp_path, monkeypatch):
    from app.research.service import ResearchService

    seen: dict = {}

    async def fake_launch(self, run_id, user_id, trip_id, **kwargs):
        seen.update(kwargs)

    monkeypatch.setattr(ResearchService, "launch", fake_launch)
    app, url, _store = build_app(tmp_path)
    create_trip(url, "t1", USER_ID)
    insert_run(url, "run-1", USER_ID, "t1", status="completed")
    client = TestClient(app)

    resp = client.post(
        "/agent/research/run-1/revise",
        json={"origin": "Ho Chi Minh City", "language": "vi"},
    )

    assert resp.status_code == 202, resp.text
    assert seen["origin"] == "Ho Chi Minh City"
    assert seen["language"] == "vi"


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
    assert body["review"] is None  # not graded


def test_status_reports_a_rejected_run_as_needs_review(tmp_path):
    from app.db.engine import get_session_factory
    from app.repositories.agent_run import AgentRunRepository

    app, url, _store = build_app(tmp_path)
    create_trip(url, "t1", USER_ID)
    insert_run(url, "run-1", USER_ID, "t1", status="completed")
    AgentRunRepository(get_session_factory(url)).add_steps(
        "run-1",
        [
            {
                "seq": 0,
                "kind": "node",
                "node": "rubric",
                "status": "ok",
                "meta": {"rubric_status": "max_iterations_reached"},
            }
        ],
    )
    client = TestClient(app)

    for path in ("/agent/research/run-1", "/agent/trips/t1/research"):
        body = client.get(path).json()
        assert body["status"] == "completed"
        assert body["review"] == "needs_review"


def test_markdown_is_served_as_the_reader_view_and_json_untouched(tmp_path):
    app, url, store = build_app(tmp_path)
    create_trip(url, "t1", USER_ID)
    insert_run(url, "run-1", USER_ID, "t1", status="completed")
    ns = ("users", USER_ID, "research", "t1")
    uid = "38382e5c-a32e-5d1e-9d08-8d2d69c51dca"
    store.put(
        ns,
        "/flights.md",
        {"content": f"- VN456, USD 139, offer_id `{uid}` (search_flights).\n"},
    )
    store.put(ns, "/proposal.json", {"content": f'{{"flights": ["{uid}"]}}'})
    client = TestClient(app)

    md = client.get("/agent/research/run-1/files/research/flights.md").json()
    assert md["content"] == "- VN456, USD 139.\n"
    raw = client.get("/agent/research/run-1/files/plan/proposal.json").json()
    assert uid in raw["content"]


def test_status_running_not_live_reads_as_interrupted(tmp_path):
    """A ``running`` row no process here is driving (not live on the bus) is an
    orphan; status reads ``interrupted`` for display without writing the DB."""
    app, url, _store = build_app(tmp_path)
    create_trip(url, "t1", USER_ID)
    insert_run(url, "run-1", USER_ID, "t1", status="running")
    client = TestClient(app)

    body = client.get("/agent/research/run-1").json()
    assert body["status"] == "interrupted"
    assert body["proposal_ready"] is False


def test_status_running_live_reads_as_running(tmp_path):
    """A ``running`` row this process is driving (live on the bus) still reads
    ``running`` — only orphans flip to ``interrupted``."""
    app, url, _store = build_app(tmp_path)
    create_trip(url, "t1", USER_ID)
    insert_run(url, "run-1", USER_ID, "t1", status="running")
    app.state.research_bus.open("run-1")
    client = TestClient(app)

    body = client.get("/agent/research/run-1").json()
    assert body["status"] == "running"


def test_status_failed_run_hides_the_proposal(tmp_path):
    """Apply is only offered on a genuinely completed run, so
    ``proposal_ready`` is false on a failed run even when a proposal.json exists."""
    app, url, store = build_app(tmp_path)
    create_trip(url, "t1", USER_ID)
    insert_run(url, "run-1", USER_ID, "t1", status="failed")
    ns = ("users", USER_ID, "research", "t1")
    store.put(ns, "/proposal.json", {"content": "{}"})
    client = TestClient(app)

    body = client.get("/agent/research/run-1").json()
    assert body["status"] == "failed"
    assert body["files"] == ["/proposal.json"]
    assert body["proposal_ready"] is False


def test_write_file_round_trips_for_the_owner(tmp_path):
    """A run owner writes a dossier file, then reads back exactly what was written."""
    app, url, _store = build_app(tmp_path)
    create_trip(url, "t1", USER_ID)
    insert_run(url, "run-1", USER_ID, "t1", status="completed")
    client = TestClient(app)

    put = client.put(
        "/agent/research/run-1/files/research/notes.md",
        json={"content": "Updated the plan."},
    )
    assert put.status_code == 200, put.text

    got = client.get("/agent/research/run-1/files/research/notes.md").json()
    assert got["content"] == "Updated the plan."


def test_write_file_foreign_run_is_404(tmp_path):
    """A foreign run is indistinguishable from missing, so a write to it is a 404."""
    app, url, _store = build_app(tmp_path)
    insert_run(url, "run-x", "someone-else", "t1", status="completed")
    client = TestClient(app)

    resp = client.put(
        "/agent/research/run-x/files/research/notes.md",
        json={"content": "hi"},
    )
    assert resp.status_code == 404, resp.text


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
