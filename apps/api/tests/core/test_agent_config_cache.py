"""AgentConfigCache + reload_from_db (specs/min-43-db-agent-config Task A.4).

MIN-47 adds a TTL-based lazy refresh + a generation counter — covered below.
"""

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
    assert AgentConfigCache._loaded_at is not None  # "loaded" state

    AgentConfigCache.invalidate()

    assert AgentConfigCache._loaded_at is None  # next read will reload


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
