"""Embeddings + vector store selection (specs/travel-agent Task 4.1)."""

from langchain_core.documents import Document
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.vectorstores import InMemoryVectorStore


def test_get_embeddings_fake_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.rag.embeddings import get_embeddings

    emb = get_embeddings()
    assert isinstance(emb, DeterministicFakeEmbedding)
    # deterministic: same text -> same vector
    assert emb.embed_query("Tokyo") == emb.embed_query("Tokyo")
    get_settings.cache_clear()


def test_get_vector_store_in_memory_for_sqlite():
    from app.rag.embeddings import get_vector_store

    store = get_vector_store(database_url="sqlite:///:memory:")
    assert isinstance(store, InMemoryVectorStore)


def test_vector_store_add_and_search():
    from app.rag.embeddings import get_vector_store

    store = get_vector_store(database_url="sqlite:///:memory:")
    store.add_documents(
        [
            Document(page_content="ramen shop in Shinjuku", metadata={"city": "Tokyo"}),
            Document(page_content="beach in Da Nang", metadata={"city": "Da Nang"}),
        ]
    )
    results = store.similarity_search("ramen shop in Shinjuku", k=1)
    assert results
    assert results[0].metadata["city"] == "Tokyo"
