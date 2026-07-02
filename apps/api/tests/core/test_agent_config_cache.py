"""AgentConfigCache + reload_from_db (specs/min-43-db-agent-config Task A.4)."""

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
