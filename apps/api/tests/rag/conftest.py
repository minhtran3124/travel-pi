"""Fixtures for RAG tests (specs/travel-knowledge-rag).

Tools resolve their DB session from ``get_settings().database_url`` (they run
inside the graph, not a request), and the vector store is a cached singleton
keyed by that URL — so these fixtures point the setting at an isolated temp
SQLite DB, seed reference data once, and reset the store cache so each test gets
a private store. ``fake_embeddings`` patches ``get_embeddings`` to a deterministic
fake so the suite is hermetic even when ``apps/api/.env`` carries a real OpenAI
key (no network).
"""

import pytest
from app.core.config import get_settings
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.seed import seed_all


@pytest.fixture
def seeded_session(tmp_path):
    """A Session on a seeded temp DB (reference visa/tips available for ingest)."""
    url = f"sqlite:///{tmp_path / 'rag.db'}"
    get_settings.cache_clear()
    Base.metadata.create_all(get_engine(url), checkfirst=True)
    seed_all(get_session_factory(url))
    with get_session_factory(url)() as session:
        yield session
    get_settings.cache_clear()


@pytest.fixture
def fake_embeddings(monkeypatch):
    """Patch ``get_embeddings`` to a deterministic fake (no OpenAI, no network).

    ``get_embeddings`` checks ``settings.openai_api_key``; a real key in
    ``apps/api/.env`` would otherwise make every embedding call hit OpenAI.
    Patching the function directly (in both homes that re-export it) wins
    regardless of when other fixtures rebuild the cached settings.
    """
    import app.core.embeddings as ce
    from app.rag import embeddings as rag_emb
    from langchain_core.embeddings import DeterministicFakeEmbedding

    fake = DeterministicFakeEmbedding(size=1536)
    monkeypatch.setattr(ce, "get_embeddings", lambda: fake)
    monkeypatch.setattr(rag_emb, "get_embeddings", lambda: fake)
    return fake


@pytest.fixture
def reset_store():
    """Clear the cached vector store(s) before and after the test (isolation)."""
    from app.rag.embeddings import reset_vector_store

    reset_vector_store()
    yield
    reset_vector_store()
