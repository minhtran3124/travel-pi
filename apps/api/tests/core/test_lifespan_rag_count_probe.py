"""Lifespan's RAG pre-warm must probe by document COUNT, not mere presence — a
presence-only probe (``similarity_search(..., k=1)``) skips re-ingestion forever
once the store holds anything at all, so new visa/tips content added after the
first ingest on an existing Postgres never gets embedded (gh-237)."""

from app.core import config
from app.main import create_app
from fastapi.testclient import TestClient
from langchain_core.documents import Document

# A single short visa doc — chunk_text keeps a short string as one chunk, so
# its expected id is exactly "visa-Wonderland" (see app/rag/ingest._doc_id).
_FAKE_CORPUS = [
    Document(
        page_content="Visa info for Wonderland.",
        metadata={"source": "visa", "country": "Wonderland"},
    )
]
_EXPECTED_ID = "visa-Wonderland"


class _FakeDoc:
    def __init__(self, doc_id: str) -> None:
        self.id = doc_id


class _FakeStore:
    """Stand-in for a persisted (non in-memory) vector store — a plain object
    is not an ``InMemoryVectorStore`` instance, so lifespan takes the count-probe
    branch."""

    def __init__(self, existing_ids: list[str]) -> None:
        self.existing_ids = set(existing_ids)
        self.add_documents_calls = 0

    def get_by_ids(self, ids: list[str]) -> list[_FakeDoc]:
        return [_FakeDoc(i) for i in ids if i in self.existing_ids]

    def add_documents(self, docs, ids: list[str]) -> list[str]:
        self.add_documents_calls += 1
        self.existing_ids.update(ids)
        return list(ids)


def _app_on_temp_db(monkeypatch, tmp_path, name: str):
    url = f"sqlite:///{tmp_path / name}"
    settings = config.get_settings()
    monkeypatch.setattr(settings, "database_url", url, raising=False)
    config.get_settings.cache_clear()
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    return create_app()


def test_lifespan_skips_reingest_when_counts_match(monkeypatch, tmp_path):
    """Store already has every expected id → ingest_knowledge is not called."""
    import app.rag.embeddings as embeddings_mod
    import app.rag.ingest as ingest_mod

    monkeypatch.setattr(
        ingest_mod, "build_knowledge_corpus", lambda session: _FAKE_CORPUS
    )
    fake_store = _FakeStore(existing_ids=[_EXPECTED_ID])
    monkeypatch.setattr(embeddings_mod, "get_vector_store", lambda: fake_store)

    app = _app_on_temp_db(monkeypatch, tmp_path, "skip.db")
    with TestClient(app):
        pass

    assert fake_store.add_documents_calls == 0


def test_lifespan_reingests_when_counts_differ(monkeypatch, tmp_path):
    """Store is missing an expected id (e.g. new content since the last ingest) → ingest_knowledge runs."""
    import app.rag.embeddings as embeddings_mod
    import app.rag.ingest as ingest_mod

    monkeypatch.setattr(
        ingest_mod, "build_knowledge_corpus", lambda session: _FAKE_CORPUS
    )
    fake_store = _FakeStore(existing_ids=[])
    monkeypatch.setattr(embeddings_mod, "get_vector_store", lambda: fake_store)

    app = _app_on_temp_db(monkeypatch, tmp_path, "reingest.db")
    with TestClient(app):
        pass

    assert fake_store.add_documents_calls == 1
    assert _EXPECTED_ID in fake_store.existing_ids
