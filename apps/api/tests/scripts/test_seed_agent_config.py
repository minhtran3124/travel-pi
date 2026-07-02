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


def test_seeds_all_nine_nodes_with_defaults(db_url):
    from scripts.seed_agent_config import (
        DEFAULT_MODEL,
        DEFAULT_PROVIDER,
        seed_agent_config,
    )

    rows = seed_agent_config()

    assert {name for name, *_ in rows} == set(AGENT_CONFIG_NODES)
    assert len(rows) == 9
    assert all(p == DEFAULT_PROVIDER and m == DEFAULT_MODEL for _, p, m, _ in rows)

    # Persisted: every node carries clinepass + the nano model + the profile's
    # own gateway base_url (derived by default).
    repo = AgentConfigRepository(get_session_factory(db_url))
    stored = {r.agent_name: (r.provider, r.model, r.base_url) for r in repo.list_all()}
    assert stored["concierge"] == (
        "clinepass",
        "openai/gpt-5.4-nano",
        "https://api.cline.bot/api/v1",
    )
    assert len(stored) == 9


def test_base_url_defaults_to_profile_and_can_be_overridden(db_url):
    from scripts.seed_agent_config import seed_agent_config

    # Explicit override wins over the profile's gateway...
    rows = seed_agent_config(base_url="https://gw.example.com/v1", nodes=["planner"])
    assert rows[0][3] == "https://gw.example.com/v1"

    # ...and an empty string stores NULL (fall back to profile at runtime).
    rows = seed_agent_config(base_url="", nodes=["booking"])
    assert rows[0][3] is None


def test_is_idempotent(db_url):
    from scripts.seed_agent_config import seed_agent_config

    seed_agent_config()
    seed_agent_config()  # re-run upserts the same rows, no duplicates

    repo = AgentConfigRepository(get_session_factory(db_url))
    assert len(repo.list_all()) == 9


def test_custom_provider_model_and_node_subset(db_url):
    from scripts.seed_agent_config import seed_agent_config

    rows = seed_agent_config(
        provider="claude", model="claude-sonnet-5", nodes=["concierge", "planner"]
    )

    assert {name for name, *_ in rows} == {"concierge", "planner"}
    # claude profile derives its own gateway base_url.
    assert all(base_url == "https://api.claude.com/v1" for *_, base_url in rows)
    repo = AgentConfigRepository(get_session_factory(db_url))
    assert len(repo.list_all()) == 2


def test_rejects_unknown_provider(db_url):
    from scripts.seed_agent_config import seed_agent_config

    with pytest.raises(DomainValidationError):
        seed_agent_config(provider="not-a-provider")
