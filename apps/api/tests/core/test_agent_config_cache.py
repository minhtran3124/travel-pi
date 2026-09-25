"""AgentConfigCache + reload_from_db (specs/min-43-db-agent-config Task A.4).

MIN-47 adds a TTL-based lazy refresh + a generation counter — covered below.
"""

import logging
import threading
import time

import pytest
from app.core.agent_config_cache import (
    AgentConfigCache,
    AgentModelOverride,
    reload_from_db,
)
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.repositories.agent_config import AgentConfigRepository
from sqlalchemy.exc import SQLAlchemyError


@pytest.fixture(autouse=True)
def _clear_cache():
    AgentConfigCache.clear()
    yield
    AgentConfigCache.clear()


def test_sync_from_cache_replaces_map():
    AgentConfigCache.sync_from_cache(
        {"concierge": AgentModelOverride(provider="openai")}
    )
    assert AgentConfigCache.get("concierge") == AgentModelOverride(provider="openai")

    AgentConfigCache.sync_from_cache({"planner": AgentModelOverride(model="gpt-4o")})
    assert AgentConfigCache.get("concierge") is None
    assert AgentConfigCache.get("planner") == AgentModelOverride(model="gpt-4o")


def test_get_returns_none_for_unknown_agent():
    assert AgentConfigCache.get("nonexistent") is None


def test_override_carries_enabled_flag():
    """AgentModelOverride round-trips an explicit `enabled` bool; default is None."""
    from app.core.agent_config_cache import AgentConfigCache, AgentModelOverride

    assert AgentModelOverride().enabled is None  # unset → None (read side coalesces)
    AgentConfigCache.sync_from_cache({"reflection": AgentModelOverride(enabled=False)})
    assert AgentConfigCache.get("reflection").enabled is False


def test_clear_empties_cache():
    AgentConfigCache.sync_from_cache(
        {"concierge": AgentModelOverride(provider="openai")}
    )
    AgentConfigCache.clear()
    assert AgentConfigCache.get("concierge") is None


def test_reload_from_db_reflects_an_upsert(tmp_path):
    url = f"sqlite:///{tmp_path / 'cache.db'}"
    factory = get_session_factory(url)
    Base.metadata.create_all(get_engine(url), checkfirst=True)

    repo = AgentConfigRepository(factory)
    repo.upsert("concierge", provider="anthropic", model="claude-3", base_url=None)

    reload_from_db(factory)

    override = AgentConfigCache.get("concierge")
    assert override == AgentModelOverride(provider="anthropic", model="claude-3")
    assert AgentConfigCache.get("planner") is None


# --- MIN-47: TTL refresh + generation counter -------------------------------


def test_generation_bumps_only_when_data_changes():
    assert AgentConfigCache.generation() == 0

    AgentConfigCache.sync_from_cache({"a": AgentModelOverride(model="x")})
    assert AgentConfigCache.generation() == 1

    AgentConfigCache.sync_from_cache({"a": AgentModelOverride(model="x")})  # identical
    assert AgentConfigCache.generation() == 1  # no bump

    AgentConfigCache.sync_from_cache({"a": AgentModelOverride(model="y")})  # changed
    assert AgentConfigCache.generation() == 2


def test_get_reloads_when_poll_detects_a_change(monkeypatch):
    reload_calls = []
    monkeypatch.setattr(
        "app.core.agent_config_cache.max_updated_at",
        lambda factory: "2026-07-21T00:00:01+00:00",
    )
    monkeypatch.setattr(
        "app.core.agent_config_cache.reload_from_db",
        lambda factory: reload_calls.append(factory),
    )
    AgentConfigCache.configure("FACTORY", poll_interval_seconds=3600)
    AgentConfigCache._known_updated_at = "2026-07-21T00:00:00+00:00"  # stale
    AgentConfigCache._loaded_at = time.monotonic() - 10_000  # force past interval

    AgentConfigCache.get("concierge")

    assert reload_calls == ["FACTORY"]  # poll saw a change -> full reload
    assert AgentConfigCache._known_updated_at == "2026-07-21T00:00:01+00:00"


def test_get_skips_reload_when_poll_sees_no_change(monkeypatch):
    reload_calls = []
    monkeypatch.setattr(
        "app.core.agent_config_cache.max_updated_at",
        lambda factory: "2026-07-21T00:00:00+00:00",
    )
    monkeypatch.setattr(
        "app.core.agent_config_cache.reload_from_db",
        lambda factory: reload_calls.append(factory),
    )
    AgentConfigCache.configure("FACTORY", poll_interval_seconds=3600)
    AgentConfigCache._known_updated_at = "2026-07-21T00:00:00+00:00"  # matches
    AgentConfigCache._loaded_at = time.monotonic() - 10_000  # force past interval

    AgentConfigCache.get("concierge")

    assert reload_calls == []  # poll ran, nothing changed -> no expensive reload


def test_get_skips_poll_when_interval_not_elapsed(monkeypatch):
    poll_calls = []
    monkeypatch.setattr(
        "app.core.agent_config_cache.max_updated_at",
        lambda factory: poll_calls.append(factory) or "x",
    )
    AgentConfigCache.configure("FACTORY", poll_interval_seconds=3600)
    AgentConfigCache._loaded_at = time.monotonic()  # fresh

    AgentConfigCache.get("concierge")

    assert poll_calls == []  # within interval -> no DB hit at all


def test_no_reload_without_configure(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.core.agent_config_cache.reload_from_db",
        lambda factory: calls.append(factory),
    )
    # configure() never called → no loader wired → get() must not touch the DB.
    AgentConfigCache.get("concierge")

    assert calls == []


def test_invalidate_forces_next_read_to_reload():
    from app.core.agent_config_cache import AgentConfigCache, AgentModelOverride

    AgentConfigCache.clear()
    AgentConfigCache.sync_from_cache({"planner": AgentModelOverride(model="gpt-4o")})
    assert AgentConfigCache._dirty is False  # "loaded" state

    AgentConfigCache.invalidate()

    assert AgentConfigCache._dirty is True  # next read will reload


def test_invalidate_never_blocks_on_a_reload_in_flight(monkeypatch):
    """invalidate() must return immediately even while a reload holds
    ``_refresh_lock`` and is mid DB-call — it only takes ``_dirty_lock``,
    a separate, always-uncontended-for-long lock. If invalidate() ever
    regressed to acquiring ``_refresh_lock`` itself, this would hang for the
    full 5s timeout instead of returning right away.
    """
    from app.core.agent_config_cache import AgentConfigCache

    poll_reached_db = threading.Event()
    release_poll = threading.Event()

    def _blocking_max_updated_at(factory):
        poll_reached_db.set()
        release_poll.wait(timeout=5)
        return "2026-07-21T00:00:00+00:00"  # matches known -> no reload needed

    monkeypatch.setattr(
        "app.core.agent_config_cache.max_updated_at", _blocking_max_updated_at
    )
    AgentConfigCache.configure("FACTORY", poll_interval_seconds=3600)
    AgentConfigCache._known_updated_at = "2026-07-21T00:00:00+00:00"
    AgentConfigCache._loaded_at = time.monotonic() - 10_000  # force past interval

    poll_thread = threading.Thread(target=AgentConfigCache._maybe_refresh)
    poll_thread.start()
    assert poll_reached_db.wait(timeout=5)  # poll is now inside _refresh_lock

    start = time.monotonic()
    AgentConfigCache.invalidate()
    elapsed = time.monotonic() - start

    release_poll.set()
    poll_thread.join(timeout=5)

    assert elapsed < 1.0  # did not wait for the DB call to finish
    assert AgentConfigCache._dirty is True


def test_invalidate_survives_a_reload_already_in_flight(monkeypatch):
    """GH-106 PR #107 review: invalidate() must not be clobbered by a racing
    reload that started before it and finishes after it.

    Simulates: a poll thread has already captured ``was_dirty=False`` and is
    mid DB-call (inside ``max_updated_at``) when a same-process dashboard save
    commits and calls ``invalidate()`` from another thread. The reload then
    proceeds to completion and restamps ``_loaded_at`` fresh via
    ``sync_from_cache`` — the dirty flag set by the racing ``invalidate()``
    must survive that and still force the *next* poll to hit the DB for real,
    even though ``_loaded_at`` now looks fresh.
    """
    from app.core.agent_config_cache import AgentConfigCache, AgentModelOverride

    poll_reached_db = threading.Event()
    invalidate_done = threading.Event()

    def _fake_max_updated_at(factory):
        poll_reached_db.set()
        invalidate_done.wait(timeout=5)
        return "2026-07-21T00:00:01+00:00"  # different -> triggers a reload

    def _fake_reload_from_db(factory):
        AgentConfigCache.sync_from_cache(
            {"concierge": AgentModelOverride(provider="stale")}
        )

    monkeypatch.setattr(
        "app.core.agent_config_cache.max_updated_at", _fake_max_updated_at
    )
    monkeypatch.setattr(
        "app.core.agent_config_cache.reload_from_db", _fake_reload_from_db
    )
    AgentConfigCache.configure("FACTORY", poll_interval_seconds=3600)
    AgentConfigCache._known_updated_at = "2026-07-21T00:00:00+00:00"  # stale
    AgentConfigCache._loaded_at = time.monotonic() - 10_000  # force past interval

    poll_thread = threading.Thread(target=AgentConfigCache._maybe_refresh)
    poll_thread.start()
    assert poll_reached_db.wait(timeout=5)  # poll captured was_dirty=False, mid DB-call

    AgentConfigCache.invalidate()  # races the in-flight poll
    invalidate_done.set()  # let the poll's DB call return and finish the reload

    poll_thread.join(timeout=5)

    assert AgentConfigCache._dirty is True  # invalidation survived the in-flight reload

    # And it actually forces a real reload on the very next poll, even though
    # max_updated_at reports no change and _loaded_at now looks fresh.
    reload_calls = []
    monkeypatch.setattr(
        "app.core.agent_config_cache.max_updated_at",
        lambda factory: AgentConfigCache._known_updated_at,  # "no change"
    )
    monkeypatch.setattr(
        "app.core.agent_config_cache.reload_from_db",
        lambda factory: reload_calls.append(factory),
    )

    AgentConfigCache.get("concierge")

    assert reload_calls == ["FACTORY"]


def test_poll_failure_keeps_serving_stale_cache(monkeypatch):
    def _boom(factory):
        raise SQLAlchemyError("db unreachable")

    monkeypatch.setattr("app.core.agent_config_cache.max_updated_at", _boom)
    AgentConfigCache.configure("FACTORY", poll_interval_seconds=3600)
    AgentConfigCache.sync_from_cache(
        {"concierge": AgentModelOverride(provider="openai")}
    )
    AgentConfigCache._loaded_at = time.monotonic() - 10_000  # force past interval

    result = AgentConfigCache.get("concierge")  # must not raise

    assert result == AgentModelOverride(provider="openai")  # stale value still served


def test_reload_failure_keeps_serving_stale_cache(monkeypatch):
    monkeypatch.setattr(
        "app.core.agent_config_cache.max_updated_at",
        lambda factory: "2026-07-21T00:00:01+00:00",  # different -> would reload
    )

    def _boom(factory):
        raise SQLAlchemyError("db unreachable")

    monkeypatch.setattr("app.core.agent_config_cache.reload_from_db", _boom)
    AgentConfigCache.configure("FACTORY", poll_interval_seconds=3600)
    AgentConfigCache.sync_from_cache(
        {"concierge": AgentModelOverride(provider="openai")}
    )
    AgentConfigCache._known_updated_at = "2026-07-21T00:00:00+00:00"
    AgentConfigCache._loaded_at = time.monotonic() - 10_000

    result = AgentConfigCache.get("concierge")  # must not raise

    assert result == AgentModelOverride(provider="openai")  # stale value still served
    assert AgentConfigCache._known_updated_at == "2026-07-21T00:00:00+00:00"


def test_cache_detects_a_write_made_without_invalidate(tmp_path):
    # GH-106: models "another process" writing via the repository directly —
    # AgentConfigCache.invalidate() (this process's own same-process signal)
    # is deliberately never called. The fix is that THIS cache still picks up
    # the change through the poll once the interval elapses.
    url = f"sqlite:///{tmp_path / 'cross_process.db'}"
    factory = get_session_factory(url)
    Base.metadata.create_all(get_engine(url), checkfirst=True)
    repo = AgentConfigRepository(factory)
    repo.upsert("reflection", enabled=True)

    AgentConfigCache.configure(factory, poll_interval_seconds=3600)
    reload_from_db(factory)
    assert AgentConfigCache.get("reflection").enabled is True

    repo.upsert("reflection", enabled=False)  # the "other process"'s write
    AgentConfigCache._loaded_at = time.monotonic() - 10_000  # force past interval

    assert AgentConfigCache.get("reflection").enabled is False  # picked up via poll


def test_reload_warns_only_for_unpriced_models(tmp_path, caplog):
    """A reload logs one WARNING naming the agent + model for an unpriced row; priced rows stay silent."""
    import app.core.agent_config_cache as cache_mod

    url = f"sqlite:///{tmp_path / 'unpriced.db'}"
    factory = get_session_factory(url)
    Base.metadata.create_all(get_engine(url), checkfirst=True)

    repo = AgentConfigRepository(factory)
    repo.upsert("planner", model="gpt-5")  # priced
    repo.upsert("concierge", model="totally-made-up-model")  # unpriced

    cache_mod._WARNED_UNPRICED.clear()  # per-process dedupe; isolate from other tests
    with caplog.at_level(logging.WARNING, logger="app.core.agent_config_cache"):
        reload_from_db(factory)

    warnings = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and "unpriced model" in r.getMessage()
    ]
    assert len(warnings) == 1
    msg = warnings[0].getMessage()
    assert "concierge" in msg  # names the agent
    assert "totally-made-up-model" in msg  # names the model
    assert "planner" not in msg  # priced row stays silent
    assert "gpt-5" not in msg


def test_reload_names_every_agent_sharing_an_unpriced_model(tmp_path, caplog):
    import app.core.agent_config_cache as cache_mod

    url = f"sqlite:///{tmp_path / 'shared.db'}"
    factory = get_session_factory(url)
    Base.metadata.create_all(get_engine(url), checkfirst=True)

    repo = AgentConfigRepository(factory)
    repo.upsert("planner", model="totally-made-up-model")
    repo.upsert("concierge", model="totally-made-up-model")

    cache_mod._WARNED_UNPRICED.clear()
    with caplog.at_level(logging.WARNING, logger="app.core.agent_config_cache"):
        reload_from_db(factory)
        reload_from_db(factory)

    msgs = [
        r.getMessage() for r in caplog.records if "unpriced model" in r.getMessage()
    ]
    assert len(msgs) == 2
    assert any("planner" in m for m in msgs)
    assert any("concierge" in m for m in msgs)
