"""Heartbeat task: start/stop lifecycle, provider hook, failures swallowed, disabled flag."""

import asyncio

import pytest
from app.core import heartbeat as hb
from app.core.config import get_settings
from app.core.instance import BotIdentity
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.models import BotHeartbeat
from app.repositories.bot_heartbeat import BotHeartbeatRepository


@pytest.fixture
def factory(tmp_db):
    f = get_session_factory(tmp_db)
    Base.metadata.create_all(get_engine(tmp_db), checkfirst=True)
    with f() as s:
        s.query(BotHeartbeat).delete()
        s.commit()
    return f


@pytest.fixture(autouse=True)
def _reset_provider():
    # app lifespan (any TestClient) plugs the live registry in globally; start from the default
    hb.set_snapshot_provider(None)
    yield
    hb.set_snapshot_provider(None)


def _identity(role="web"):
    return BotIdentity(
        instance_id="api-1",
        role=role,
        host="h",
        pid=4242,
        started_at="2026-10-29T09:00:00.000+00:00",
    )


def _rows(factory):
    return BotHeartbeatRepository(factory).list_live("")


def test_beat_once_writes_row_with_default_empty_snapshot(factory):
    assert hb.Heartbeat(_identity(), factory, 3).beat_once() is True
    (row,) = _rows(factory)
    assert (row.instance_id, row.pid, row.role, row.snapshot) == (
        "api-1",
        4242,
        "web",
        {},
    )


def test_provider_hook_feeds_snapshot(factory):
    hb.set_snapshot_provider(lambda: {"turns": [{"phase": "tools"}]})
    hb.Heartbeat(_identity(), factory, 3).beat_once()
    assert _rows(factory)[0].snapshot == {"turns": [{"phase": "tools"}]}


def test_raising_provider_is_swallowed(factory):
    def boom():
        raise RuntimeError("nope")

    hb.set_snapshot_provider(boom)
    assert hb.Heartbeat(_identity(), factory, 3).beat_once() is True
    assert _rows(factory)[0].snapshot == {}


def test_db_failure_is_swallowed_and_loop_keeps_beating(factory):
    beat = hb.Heartbeat(_identity(), factory, 3)
    real = beat._repo.upsert
    calls = {"n": 0}

    def flaky(**kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("db down")
        return real(**kw)

    beat._repo.upsert = flaky
    assert beat.beat_once() is False
    assert beat.beat_once() is True
    assert len(_rows(factory)) == 1


@pytest.mark.asyncio
async def test_start_beats_and_stop_removes_row(factory):
    beat = hb.Heartbeat(_identity("worker"), factory, 0.01)
    beat.start()
    for _ in range(100):
        if _rows(factory):
            break
        await asyncio.sleep(0.02)
    assert _rows(factory)[0].role == "worker"
    await beat.stop()
    assert _rows(factory) == []


@pytest.mark.asyncio
async def test_stop_swallows_delete_failure(factory):
    beat = hb.Heartbeat(_identity(), factory, 0.01)
    beat.start()

    def boom(*a):
        raise RuntimeError("db gone")

    beat._repo.delete = boom
    await beat.stop()


@pytest.mark.asyncio
async def test_start_heartbeat_respects_disabled_flag(monkeypatch, factory):
    monkeypatch.setenv("BOT_HEARTBEAT_ENABLED", "false")
    get_settings.cache_clear()
    try:
        assert hb.start_heartbeat(session_factory=factory) is None
        monkeypatch.setenv("BOT_HEARTBEAT_ENABLED", "true")
        monkeypatch.setenv("BOT_HEARTBEAT_INTERVAL_SECONDS", "0.01")
        get_settings.cache_clear()
        beat = hb.start_heartbeat(role="worker", session_factory=factory)
        assert beat is not None and beat.identity.role == "worker"
        await beat.stop()
    finally:
        get_settings.cache_clear()
