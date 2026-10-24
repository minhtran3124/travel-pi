"""CLI agent_config seeder (scripts/seed_agent_config.py, MIN-43)."""

import pytest
from app.data.agent_config import AGENT_CONFIG_NODES
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.exceptions import DomainValidationError
from app.repositories.agent_config import AgentConfigRepository


@pytest.fixture
def db_url(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'agent_config_seed.db'}"
    Base.metadata.create_all(get_engine(url), checkfirst=True)

    # seed_agent_config reads get_settings().database_url — point it at the temp db.
    from app.core import config

    settings = config.get_settings()
    monkeypatch.setattr(settings, "database_url", url, raising=False)
    config.get_settings.cache_clear()
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    import scripts.seed_agent_config as mod

    monkeypatch.setattr(mod, "get_settings", lambda: settings)
    return url


def test_seeds_every_node_with_defaults(db_url):
    from scripts.seed_agent_config import (
        DEFAULT_MODEL,
        DEFAULT_PROVIDER,
        seed_agent_config,
    )

    rows = seed_agent_config()

    # Count against AGENT_CONFIG_NODES, not a literal: the set assertion above
    # already pins WHICH nodes are seeded, so a hardcoded number adds no coverage
    # and only breaks when a legitimate node is added (it did, for date_resolution).
    assert {r["agent_name"] for r in rows} == set(AGENT_CONFIG_NODES)
    assert len(rows) == len(AGENT_CONFIG_NODES)
    assert all(
        r["provider"] == DEFAULT_PROVIDER and r["model"] == DEFAULT_MODEL for r in rows
    )
    # Knobs default to NULL (provider defaults) unless asked for.
    assert all(r["temperature"] is None and r["max_tokens"] is None for r in rows)

    # Persisted: every node carries clinepass + the nano model + the profile's
    # own gateway base_url (derived by default).
    repo = AgentConfigRepository(get_session_factory(db_url))
    stored = {r.agent_name: (r.provider, r.model, r.base_url) for r in repo.list_all()}
    assert stored["concierge"] == (
        "clinepass",
        "openai/gpt-5.4-nano",
        "https://api.cline.bot/api/v1",
    )
    assert len(stored) == len(AGENT_CONFIG_NODES)


def test_base_url_defaults_to_profile_and_can_be_overridden(db_url):
    from scripts.seed_agent_config import seed_agent_config

    # Explicit override wins over the profile's gateway...
    rows = seed_agent_config(base_url="https://gw.example.com/v1", nodes=["planner"])
    assert rows[0]["base_url"] == "https://gw.example.com/v1"

    # ...and an empty string stores NULL (fall back to profile at runtime).
    rows = seed_agent_config(base_url="", nodes=["booking"])
    assert rows[0]["base_url"] is None


def test_seeds_temperature_and_max_tokens(db_url):
    from scripts.seed_agent_config import seed_agent_config

    seed_agent_config(temperature=0.2, max_tokens=2048, nodes=["concierge"])

    repo = AgentConfigRepository(get_session_factory(db_url))
    row = repo.get("concierge")
    assert row.temperature == 0.2
    assert row.max_tokens == 2048


def test_is_idempotent(db_url):
    from scripts.seed_agent_config import seed_agent_config

    seed_agent_config()
    seed_agent_config()  # re-run upserts the same rows, no duplicates

    repo = AgentConfigRepository(get_session_factory(db_url))
    assert len(repo.list_all()) == len(AGENT_CONFIG_NODES)


def test_custom_provider_model_and_node_subset(db_url):
    from scripts.seed_agent_config import seed_agent_config

    rows = seed_agent_config(
        provider="claude", model="claude-sonnet-5", nodes=["concierge", "planner"]
    )

    assert {r["agent_name"] for r in rows} == {"concierge", "planner"}
    # claude profile derives its own gateway base_url.
    assert all(r["base_url"] == "https://api.claude.com" for r in rows)
    repo = AgentConfigRepository(get_session_factory(db_url))
    assert len(repo.list_all()) == 2


def test_rejects_unknown_provider(db_url):
    from scripts.seed_agent_config import seed_agent_config

    with pytest.raises(DomainValidationError):
        seed_agent_config(provider="not-a-provider")


def test_anthropic_provider_without_model_seeds_claude_tiers(db_url):
    from app.agents.constants import FAST_AGENTS
    from scripts.seed_agent_config import seed_agent_config

    rows = seed_agent_config(provider="anthropic", base_url=None)

    for r in rows:
        fast = r["agent_name"] in FAST_AGENTS
        assert r["model"] == ("claude-haiku-5-5" if fast else "claude-sonnet-5-5")
