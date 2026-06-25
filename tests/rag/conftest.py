"""Fixtures for RAG tests (specs/travel-agent Phase 4)."""

import pytest
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.seed import seed_all


@pytest.fixture
def seeded_session(tmp_path):
    """A Session on a seeded temp DB (reference places available for ingest)."""
    url = f"sqlite:///{tmp_path / 'rag.db'}"
    Base.metadata.create_all(get_engine(url), checkfirst=True)
    seed_all(get_session_factory(url))
    with get_session_factory(url)() as session:
        yield session
