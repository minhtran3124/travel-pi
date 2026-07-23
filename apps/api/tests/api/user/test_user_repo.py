"""UserRepository tests (specs/runtime-context-config B.1)."""

import pytest
from app.db.base import Base
from app.db.engine import get_session_factory
from app.repositories.user import UserRepository


@pytest.fixture
def repo(tmp_path):
    url = f"sqlite:///{tmp_path / 'user.db'}"
    factory = get_session_factory(url)
    Base.metadata.create_all(bind=factory().get_bind())
    return UserRepository(factory)


def test_get_tier_returns_free_when_no_row(repo):
    assert repo.get_tier("unknown-user") == "free"


def test_upsert_tier_and_get(repo):
    repo.upsert_tier("u1", "premium")
    assert repo.get_tier("u1") == "premium"


def test_upsert_tier_update(repo):
    repo.upsert_tier("u1", "premium")
    repo.upsert_tier("u1", "free")
    assert repo.get_tier("u1") == "free"


def test_upsert_tier_idempotent_no_duplicate(repo):
    repo.upsert_tier("u1", "premium")
    repo.upsert_tier("u1", "premium")
    # Only one row should exist — get_tier must still return premium
    assert repo.get_tier("u1") == "premium"
