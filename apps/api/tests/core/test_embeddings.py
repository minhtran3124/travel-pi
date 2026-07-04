"""Shared embeddings helper (relocated from tests/rag/test_embeddings.py;
specs/remove-rag-feature)."""

from langchain_core.embeddings import DeterministicFakeEmbedding


def test_get_embeddings_fake_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.core.embeddings import get_embeddings

    emb = get_embeddings()
    assert isinstance(emb, DeterministicFakeEmbedding)
    # deterministic: same text -> same vector
    assert emb.embed_query("Tokyo") == emb.embed_query("Tokyo")
    get_settings.cache_clear()
