"""Pure mapping tests for the live-bots DTO (no database)."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from app.services import live_bots_service as svc

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def _run(**kw):
    base = {
        "id": "r1",
        "user_id": "user-secret-id-123",
        "channel": "chat",
        "status": "running",
        "current_flow": "planner",
        "started_at": (NOW - timedelta(seconds=30)).isoformat(),
        "finished_at": None,
        "llm_calls": 3,
        "input_tokens": 100,
        "output_tokens": 50,
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _step(**kw):
    base = {"node": "planner", "tool_name": None, "status": "ok", "error_type": None}
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.mark.parametrize(
    "flow", ["planner", "concierge", "journal", "booking", "budget"]
)
def test_bot_per_flow(flow):
    assert svc.to_bot(_run(current_flow=flow), None, NOW, 600)["bot"] == flow


def test_bot_research_channel_and_generic_fallback():
    assert svc.bot_kind("planner", "research") == "research"
    assert svc.bot_kind(None, "chat") == "generic"
    assert svc.bot_kind("weird", "stream") == "generic"


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("running", "running"),
        ("interrupted", "waiting"),
        ("completed", "done"),
        ("failed", "failed"),
    ],
)
def test_state_per_status(status, expected):
    assert svc.to_bot(_run(status=status), None, NOW, 600)["state"] == expected


def test_retrying_only_for_retryable_error():
    retry = _step(status="error", error_type="APITimeoutError")
    hard = _step(status="error", error_type="ValueError")
    assert svc.to_bot(_run(), retry, NOW, 600)["state"] == "retrying"
    assert svc.to_bot(_run(), hard, NOW, 600)["state"] == "running"


@pytest.mark.parametrize(
    ("node", "expected"),
    [
        (None, 0),
        ("supervisor", 0),
        ("summarize", 0),
        ("planner", 1),
        ("concierge", 1),
        ("tools", 2),
        ("reflection", 3),
    ],
)
def test_stage_from_node(node, expected):
    assert svc.stage(node) == expected


def test_counters_and_step_label():
    bot = svc.to_bot(_run(), _step(node="tools", tool_name="search_flights"), NOW, 600)
    assert bot["tokens"] == 150
    assert bot["llm_calls"] == 3
    assert bot["elapsed_s"] == 30
    assert bot["step"] == "search_flights"
    assert bot["stage"] == 2


def test_elapsed_stops_at_finish():
    run = _run(
        status="completed",
        started_at=(NOW - timedelta(seconds=20)).isoformat(),
        finished_at=(NOW - timedelta(seconds=5)).isoformat(),
    )
    assert svc.to_bot(run, None, NOW, 600)["elapsed_s"] == 15


def test_stale_when_running_past_timeout():
    old = _run(started_at=(NOW - timedelta(seconds=700)).isoformat())
    assert svc.to_bot(old, None, NOW, 600)["stale"] is True
    assert svc.to_bot(_run(), None, NOW, 600)["stale"] is False
    done = _run(
        status="completed", started_at=old.started_at, finished_at=NOW.isoformat()
    )
    assert svc.to_bot(done, None, NOW, 600)["stale"] is False


def test_user_label_is_anonymous_and_stable():
    label = svc.user_label("alice@example.com")
    assert label == svc.user_label("alice@example.com")
    assert "alice" not in label and "@" not in label
    assert label != svc.user_label("bob@example.com")
    bot = svc.to_bot(_run(user_id="alice@example.com"), None, NOW, 600)
    assert "alice" not in str(bot)


def test_counts():
    bots = [
        {"state": "running"},
        {"state": "running"},
        {"state": "waiting"},
        {"state": "done"},
    ]
    assert svc.counts(bots, 7) == {
        "running": 2,
        "waiting": 1,
        "retrying": 0,
        "done_today": 7,
    }
