"""Demo bot seed script: idempotent writes, clear, production refusal, animation phases."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.models import BotHeartbeat
from app.repositories.bot_heartbeat import BotHeartbeatRepository
from scripts import seed_bots

NOW = datetime(2026, 10, 29, 10, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def repo(tmp_db):
    Base.metadata.create_all(get_engine(tmp_db), checkfirst=True)
    factory = get_session_factory(tmp_db)
    with factory() as s:  # tmp_db is shared across tests
        s.query(BotHeartbeat).delete()
        s.commit()
    return BotHeartbeatRepository(factory)


def _rows(repo):
    return repo.list_live("2000-01-01")


def _settings(monkeypatch, environment, url=""):
    fake = SimpleNamespace(environment=environment, database_url=url)
    monkeypatch.setattr(seed_bots, "get_settings", lambda: fake)


def test_seed_is_idempotent_and_tagged(repo):
    assert seed_bots.seed(repo, NOW) == 5
    first = [(r.instance_id, r.pid, r.host) for r in _rows(repo)]
    seed_bots.seed(repo, NOW, tick=3)
    rows = _rows(repo)
    assert [(r.instance_id, r.pid, r.host) for r in rows] == first
    assert {r.instance_id for r in rows} == {"api-1", "api-2", "worker"}
    assert {r.host for r in rows} == {seed_bots.DEMO_HOST}


def test_snapshots_cover_every_agent_kind_and_phase(repo):
    agents, phases = set(), set()
    for tick in range(len(seed_bots.PHASES)):
        seed_bots.seed(repo, NOW, tick=tick)
        for row in _rows(repo):
            for turn in row.snapshot["turns"]:
                for a in turn["agents"]:
                    agents.add(a["agent"])
                    phases.add(a["phase"])
    expected = {
        "supervisor",
        "planner",
        "concierge",
        "journal",
        "booking",
        "budget",
        "research",
    }
    assert expected <= agents
    assert phases == set(seed_bots.PHASES)


def test_clear_removes_only_demo_rows(repo):
    seed_bots.seed(repo, NOW)
    repo.upsert(
        instance_id="real",
        pid=1,
        role="web",
        host="h",
        started_at="x",
        last_seen="2026-10-29T10:00:00.000+00:00",
    )
    seed_bots.clear(repo)
    assert [r.instance_id for r in _rows(repo)] == ["real"]


def test_skip_leaves_instance_untouched(repo):
    seed_bots.seed(repo, NOW)
    later = datetime(2026, 10, 29, 10, 1, 0, tzinfo=timezone.utc)
    seed_bots.seed(repo, later, skip=frozenset({"api-2"}))
    seen = {r.instance_id: r.last_seen for r in _rows(repo)}
    assert seen["api-2"] < seen["api-1"]


def test_animation_takes_a_bot_offline_periodically():
    assert seed_bots.offline_instances(0) == frozenset()
    assert seed_bots.offline_instances(seed_bots.OFFLINE_FROM_TICK) == {"api-2"}
    assert seed_bots.offline_instances(seed_bots.CYCLE_TICKS) == frozenset()


def test_refuses_in_production(repo, tmp_db, monkeypatch):
    _settings(monkeypatch, "production", tmp_db)
    with pytest.raises(SystemExit):
        seed_bots.main([])
    assert _rows(repo) == []


def test_main_seeds_once_then_clears(repo, tmp_db, monkeypatch):
    _settings(monkeypatch, "development", tmp_db)
    assert seed_bots.main([]) == 0
    assert len(_rows(repo)) == 5
    assert seed_bots.main(["--clear"]) == 0
    assert _rows(repo) == []


def test_extra_turns_only_for_web_processes():
    base = seed_bots.build_snapshot("api-1", 101, NOW, 0)
    busy = seed_bots.build_snapshot("api-1", 101, NOW, 0, extra_turns=3)
    assert len(busy["turns"]) == len(base["turns"]) + 3
    worker = seed_bots.build_snapshot("worker", 301, NOW, 0, extra_turns=3)
    assert len(worker["turns"]) == len(
        seed_bots.build_snapshot("worker", 301, NOW, 0)["turns"]
    )
    convs = [t["conv"] for t in busy["turns"]]
    assert len(convs) == len(set(convs))
