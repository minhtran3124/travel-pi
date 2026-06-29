"""CLI tier setter (specs/agent-identity-tier Task 2.1)."""

import pytest
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.repositories.user import UserRepository


@pytest.fixture
def db_url(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'tier.db'}"
    Base.metadata.create_all(get_engine(url), checkfirst=True)

    # set_tier reads get_settings().database_url — point it at the temp db.
    from app.core import config

    settings = config.get_settings()
    monkeypatch.setattr(settings, "database_url", url, raising=False)
    config.get_settings.cache_clear()
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    import scripts.set_tier as mod

    monkeypatch.setattr(mod, "get_settings", lambda: settings)
    return url


def test_set_tier_premium_then_free(db_url):
    from scripts.set_tier import set_tier

    assert set_tier("u1", "premium") == "premium"
    repo = UserRepository(get_session_factory(db_url))
    assert repo.get_tier("u1") == "premium"
    # idempotent update back to free
    assert set_tier("u1", "free") == "free"
    assert repo.get_tier("u1") == "free"


def test_set_tier_rejects_invalid(db_url):
    from scripts.set_tier import set_tier

    with pytest.raises(ValueError):
        set_tier("u1", "enterprise")
