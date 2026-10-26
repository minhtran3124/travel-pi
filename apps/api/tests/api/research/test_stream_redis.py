"""Task 6: SSE progress crosses web instances through Redis pub/sub.

Needs a reachable Redis (``REDIS_TEST_URL``, e.g. ``redis://localhost:6379/15``); the
tests skip cleanly when it is unset or unreachable, so ``make test`` stays zero-config.
"""

from __future__ import annotations

import os
import threading
import time
import uuid

import pytest
from app.core.config import get_settings
from app.research.progress import RedisProgressBus
from app.streaming.research_events import (
    ResearchDone,
    ResearchFile,
    ResearchStart,
)
from fastapi.testclient import TestClient

from tests.api.research import USER_ID, build_app, insert_run

REDIS_URL = os.environ.get("REDIS_TEST_URL")


def _reachable() -> bool:
    if not REDIS_URL:
        return False
    try:
        import redis

        return bool(redis.Redis.from_url(REDIS_URL, socket_connect_timeout=1).ping())
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(not _reachable(), reason="REDIS_TEST_URL not reachable")


@pytest.fixture(autouse=True)
def _enabled(monkeypatch):
    monkeypatch.setenv("RESEARCH_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _bus() -> RedisProgressBus:
    assert REDIS_URL
    return RedisProgressBus(REDIS_URL, live_ttl_s=60)


def _names(text: str) -> list[str]:
    return [
        line[len("event:") :].strip()
        for line in text.splitlines()
        if line.startswith("event:")
    ]


def test_instance_b_streams_run_published_by_instance_a(tmp_path):
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    producer = _bus()  # the worker / instance A, a different process in production
    app_b, url, _ = build_app(tmp_path)
    app_b.state.research_bus = _bus()
    insert_run(url, run_id, USER_ID, "t1", status="running")

    producer.open(run_id)
    producer.publish(run_id, ResearchStart(run_id=run_id, trip_id="t1"))
    producer.publish(run_id, ResearchFile(path="/a.md", bytes=3))
    producer.publish(
        run_id, ResearchDone(status="completed", files=["/a.md"], proposal_ready=False)
    )

    resp = TestClient(app_b).get(f"/agent/research/{run_id}/stream")

    assert _names(resp.text) == ["research_start", "research_file", "research_done"]


def test_live_tail_after_subscribe_has_no_gaps_or_duplicates(tmp_path):
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    producer = _bus()
    app_b, url, _ = build_app(tmp_path)
    app_b.state.research_bus = _bus()
    insert_run(url, run_id, USER_ID, "t1", status="running")
    producer.open(run_id)
    producer.publish(run_id, ResearchStart(run_id=run_id, trip_id="t1"))

    def _later() -> None:
        time.sleep(0.5)
        for i in range(3):
            producer.publish(run_id, ResearchFile(path=f"/f{i}.md", bytes=i))
        producer.publish(
            run_id, ResearchDone(status="completed", files=[], proposal_ready=False)
        )
        producer.close(run_id)

    t = threading.Thread(target=_later)
    t.start()
    resp = TestClient(app_b).get(f"/agent/research/{run_id}/stream")
    t.join()

    assert _names(resp.text) == [
        "research_start",
        "research_file",
        "research_file",
        "research_file",
        "research_done",
    ]
    assert resp.text.count("/f0.md") == 1


def test_finished_run_takes_db_snapshot_branch(tmp_path):
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    producer = _bus()
    app_b, url, _ = build_app(tmp_path)
    app_b.state.research_bus = _bus()
    insert_run(url, run_id, USER_ID, "t1", status="completed")
    producer.open(run_id)
    producer.publish(run_id, ResearchStart(run_id=run_id, trip_id="t1"))
    producer.close(run_id)

    assert app_b.state.research_bus.has(run_id) is False
    resp = TestClient(app_b).get(f"/agent/research/{run_id}/stream")

    assert _names(resp.text) == ["research_start", "research_phase", "research_done"]


def test_closed_run_is_not_resurrected_by_late_publish():
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    bus = _bus()
    bus.open(run_id)
    bus.close(run_id)
    bus.publish(run_id, ResearchStart(run_id=run_id, trip_id="t1"))
    bus.open(run_id)

    assert bus.has(run_id) is False


def test_redis_down_degrades_to_not_live():
    bus = RedisProgressBus("redis://127.0.0.1:1/0", live_ttl_s=60)

    bus.open("r")
    bus.publish("r", ResearchStart(run_id="r", trip_id="t"))
    bus.close("r")

    assert bus.has("r") is False
