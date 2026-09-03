"""AgentRunRepository lifecycle: start → finish → add_background → list → totals."""

from datetime import datetime, timedelta, timezone

import pytest
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.models import AgentRun
from app.repositories.agent_run import AgentRunRepository


@pytest.fixture
def repo(tmp_db):
    factory = get_session_factory(tmp_db)
    Base.metadata.create_all(get_engine(tmp_db), checkfirst=True)
    with factory() as s:
        s.query(AgentRun).delete()
        s.commit()
    return AgentRunRepository(factory)


def _start(repo, id="run-1", user_id="u1"):
    repo.start(
        id,
        user_id=user_id,
        conversation_id="c1",
        thread_id="t1",
        trip_id=None,
        channel="chat",
        kind="turn",
        started_at="2026-09-03T00:00:00+00:00",
    )


def test_start_creates_running_row(repo):
    _start(repo)
    rows = repo.list_recent()
    assert len(rows) == 1
    assert rows[0].status == "running"
    assert rows[0].llm_calls == 0
    assert rows[0].background_tokens == 0


def test_finish_maps_metrics_and_ignores_unknown_keys(repo):
    _start(repo)
    repo.finish(
        "run-1",
        status="completed",
        current_flow="planning",
        finished_at="2026-09-03T00:00:05+00:00",
        metrics={
            "llm_calls": 3,
            "llm_errors": 1,
            "input_tokens": 100,
            "output_tokens": 40,
            "cached_tokens": 10,
            "latency_ms": 5000,
            "cost_usd": 0.0123,
            "by_model": {"gpt-5": {"input_tokens": 100}},
            "by_node": {"supervisor": {"llm_calls": 1}},
            "total_tokens": 140,  # unknown column → ignored
            "bogus": "x",  # ignored
        },
    )
    row = repo.list_recent()[0]
    assert row.status == "completed"
    assert row.current_flow == "planning"
    assert row.finished_at == "2026-09-03T00:00:05+00:00"
    assert row.llm_calls == 3
    assert row.llm_errors == 1
    assert row.input_tokens == 100
    assert row.output_tokens == 40
    assert row.cached_tokens == 10
    assert row.latency_ms == 5000
    assert row.cost_usd == pytest.approx(0.0123)
    assert row.by_model == {"gpt-5": {"input_tokens": 100}}
    assert row.by_node == {"supervisor": {"llm_calls": 1}}


def test_finish_missing_id_is_noop(repo):
    # No row exists — must not raise.
    repo.finish(
        "nope",
        status="failed",
        current_flow=None,
        finished_at="2026-09-03T00:00:05+00:00",
        metrics={"llm_calls": 1},
    )
    assert repo.list_recent() == []


def test_add_background_increments(repo):
    _start(repo)
    repo.add_background("run-1", llm_calls=2, tokens=500, ms=1200)
    repo.add_background("run-1", llm_calls=1, tokens=100, ms=300)
    row = repo.list_recent()[0]
    assert row.background_llm_calls == 3
    assert row.background_tokens == 600
    assert row.background_ms == 1500


def test_list_recent_newest_first_and_limit(repo):
    _start(repo, id="run-a")
    _start(repo, id="run-b")
    _start(repo, id="run-c")
    ids = [r.id for r in repo.list_recent(limit=2)]
    assert len(ids) == 2
    # created_at desc → most recently inserted first.
    assert ids[0] == "run-c"


def test_totals_aggregates_since_cutoff(repo):
    _start(repo, id="run-1")
    repo.finish(
        "run-1",
        status="completed",
        current_flow=None,
        finished_at="2026-09-03T00:00:05+00:00",
        metrics={
            "input_tokens": 100,
            "output_tokens": 40,
            "cost_usd": 0.01,
            "latency_ms": 5000,
        },
    )
    _start(repo, id="run-2")
    repo.finish(
        "run-2",
        status="completed",
        current_flow=None,
        finished_at="2026-09-03T00:00:06+00:00",
        metrics={
            "input_tokens": 10,
            "output_tokens": 5,
            "cost_usd": None,  # no price → excluded from cost sum
            "latency_ms": 2000,
        },
    )
    totals = repo.totals(since=datetime.now(timezone.utc) - timedelta(hours=1))
    assert totals["turns"] == 2
    assert totals["tokens"] == 155
    assert totals["cost"] == pytest.approx(0.01)
    assert sorted(totals["latencies"]) == [2000, 5000]


def test_totals_excludes_rows_before_since(repo):
    _start(repo)
    totals = repo.totals(since=datetime.now(timezone.utc) + timedelta(hours=1))
    assert totals["turns"] == 0
    assert totals["tokens"] == 0
    assert totals["cost"] == 0
    assert totals["latencies"] == []
