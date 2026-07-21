"""AgentConfigRepository get/list_all/upsert (specs/min-43-db-agent-config Task A.2)."""

import pytest
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.exceptions import DomainValidationError
from app.repositories.agent_config import AgentConfigRepository


@pytest.fixture()
def repo(tmp_path):
    url = f"sqlite:///{tmp_path / 'agent_config_repo.db'}"
    factory = get_session_factory(url)
    Base.metadata.create_all(get_engine(url), checkfirst=True)
    with factory() as session:
        yield AgentConfigRepository(session)


def test_get_returns_none_when_absent(repo):
    assert repo.get("concierge") is None


def test_upsert_inserts_then_updates_same_row(repo):
    created = repo.upsert("concierge", provider="openai", model="gpt-4o")
    assert created.agent_name == "concierge"
    assert created.provider == "openai"

    updated = repo.upsert("concierge", provider="anthropic", model="claude")
    assert updated.id == created.id
    assert updated.provider == "anthropic"
    assert updated.model == "claude"

    assert len(repo.list_all()) == 1


def test_upsert_rejects_invalid_provider(repo):
    with pytest.raises(DomainValidationError):
        repo.upsert("concierge", provider="not-a-provider")


def test_upsert_accepts_gateway_profile_name(repo):
    # Profile names beyond the raw SDKs (e.g. clinepass) are valid providers.
    row = repo.upsert("concierge", provider="clinepass", model="openai/gpt-4o")
    assert row.provider == "clinepass"


def test_upsert_persists_temperature_and_max_tokens(repo):
    row = repo.upsert("concierge", provider="openai", temperature=0.2, max_tokens=1024)
    assert row.temperature == 0.2
    assert row.max_tokens == 1024

    # Re-upsert without the knobs clears them (full replace, not merge).
    cleared = repo.upsert("concierge", provider="openai")
    assert cleared.temperature is None
    assert cleared.max_tokens is None


def test_upsert_persists_enabled(repo):
    repo.upsert("reflection", enabled=False)
    assert repo.get("reflection").enabled is False

    repo.upsert("reflection", enabled=True)
    assert repo.get("reflection").enabled is True


def test_upsert_preserves_enabled_when_omitted(repo):
    # Explicitly disable, then upsert unrelated fields WITHOUT enabled: the
    # flag must be preserved (not clobbered back to the default).
    repo.upsert("reflection", enabled=False)
    repo.upsert("reflection", provider="openai")
    assert repo.get("reflection").enabled is False


def test_list_all_returns_every_row(repo):
    repo.upsert("concierge", provider="openai")
    repo.upsert("planner", provider="anthropic")
    names = {row.agent_name for row in repo.list_all()}
    assert names == {"concierge", "planner"}


def test_max_updated_at_returns_none_when_empty(repo):
    assert repo.max_updated_at() is None


def test_max_updated_at_reflects_latest_write(repo):
    repo.upsert("concierge", provider="openai")
    first = repo.max_updated_at()
    assert first is not None

    repo.upsert("planner", provider="anthropic")
    second = repo.max_updated_at()
    assert second >= first  # a later write is never an earlier timestamp
