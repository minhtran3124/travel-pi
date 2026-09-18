"""SC-15: the SSE endpoint — DB snapshot when the bus is empty, replay+tail when
a live channel exists. Event names match the FE union in ``research_events.py``.
"""

from __future__ import annotations

import pytest
from app.core.config import get_settings
from app.streaming.research_events import ResearchDone, ResearchPhase, ResearchStart
from fastapi.testclient import TestClient

from tests.api.research import USER_ID, build_app, insert_run


@pytest.fixture(autouse=True)
def _enabled(monkeypatch):
    monkeypatch.setenv("RESEARCH_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _events(text: str) -> list[str]:
    """Ordered list of event names from an SSE body."""
    names = []
    for block in text.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("event:"):
                names.append(line[len("event:") :].strip())
    return names


def test_snapshot_path_emits_start_phase_done(tmp_path):
    app, url, _store = build_app(tmp_path)
    # No bus channel for this run → the endpoint builds a DB snapshot. The run is
    # already terminal, so the poll loop emits the terminal event immediately.
    insert_run(url, "run-1", USER_ID, "t1", status="completed")
    client = TestClient(app)

    resp = client.get("/agent/research/run-1/stream")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    names = _events(resp.text)
    assert names == ["research_start", "research_phase", "research_done"]


def test_snapshot_failed_run_emits_error(tmp_path):
    app, url, _store = build_app(tmp_path)
    insert_run(url, "run-2", USER_ID, "t1", status="failed")
    client = TestClient(app)

    resp = client.get("/agent/research/run-2/stream")
    assert resp.status_code == 200
    names = _events(resp.text)
    assert names[0] == "research_start"
    assert names[-1] == "research_error"


def test_live_bus_replays_then_tails(tmp_path):
    app, url, _store = build_app(tmp_path)
    insert_run(url, "run-3", USER_ID, "t1", status="running")
    # Pre-load the bus so a late subscriber replays the buffer, then closes on the
    # terminal event carried in it.
    bus = app.state.research_bus
    bus.publish("run-3", ResearchStart(run_id="run-3", trip_id="t1"))
    bus.publish(
        "run-3", ResearchPhase(todos=[{"content": "flights", "status": "in_progress"}])
    )
    bus.publish(
        "run-3",
        ResearchDone(status="completed", files=["/flights.md"], proposal_ready=False),
    )
    client = TestClient(app)

    resp = client.get("/agent/research/run-3/stream")
    assert resp.status_code == 200
    names = _events(resp.text)
    assert names == ["research_start", "research_phase", "research_done"]
    assert "/flights.md" in resp.text


def test_stream_foreign_run_is_404(tmp_path):
    app, url, _store = build_app(tmp_path)
    insert_run(url, "run-x", "someone-else", "t1", status="completed")
    client = TestClient(app)

    resp = client.get("/agent/research/run-x/stream")
    assert resp.status_code == 404, resp.text
