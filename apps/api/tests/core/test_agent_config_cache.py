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


def test_get_reloads_from_db_when_stale(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.core.agent_config_cache.reload_from_db",
        lambda factory: calls.append(factory),
    )
    AgentConfigCache.configure("FACTORY", ttl_seconds=3600)
    AgentConfigCache._loaded_at = time.monotonic() - 10_000  # force past TTL

    AgentConfigCache.get("concierge")

    assert calls == ["FACTORY"]  # a single reload was triggered


def test_get_skips_reload_when_fresh(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.core.agent_config_cache.reload_from_db",
        lambda factory: calls.append(factory),
    )
    AgentConfigCache.configure("FACTORY", ttl_seconds=3600)
    AgentConfigCache._loaded_at = time.monotonic()  # fresh

    AgentConfigCache.get("concierge")

    assert calls == []  # within TTL → no DB hit


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
