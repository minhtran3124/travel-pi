"""Ingest + hybrid retriever (specs/travel-agent Task 4.2)."""

from langchain_core.documents import Document


def test_chunk_text_splits_long_prose():
    from app.rag.ingest import chunk_text

    long = "word " * 500
    chunks = chunk_text(long)
    assert len(chunks) > 1


def test_chunk_text_short_passthrough():
    from app.rag.ingest import chunk_text

    assert chunk_text("a short tip") == ["a short tip"]


def test_ingest_places_into_store(seeded_session):
    from app.rag.embeddings import get_vector_store
    from app.rag.ingest import ingest_places

    store = get_vector_store(database_url="sqlite:///:memory:")
    count = ingest_places(store, seeded_session)
    assert count > 0
    hits = store.similarity_search("place", k=1)
    assert hits


def test_hybrid_search_metadata_filter():
    from app.rag.embeddings import get_vector_store
    from app.rag.retriever import hybrid_search

    store = get_vector_store(database_url="sqlite:///:memory:")
    store.add_documents(
        [
            Document(page_content="ramen in Shinjuku", metadata={"city": "Tokyo"}),
            Document(page_content="ramen by the beach", metadata={"city": "Da Nang"}),
            Document(page_content="sushi counter", metadata={"city": "Tokyo"}),
        ]
    )
    results = hybrid_search(store, "ramen", filters={"city": "Tokyo"}, k=5)
    assert results
    assert all(d.metadata["city"] == "Tokyo" for d in results)


def test_hybrid_search_empty_store():
    from app.rag.embeddings import get_vector_store
    from app.rag.retriever import hybrid_search

    store = get_vector_store(database_url="sqlite:///:memory:")
    assert hybrid_search(store, "anything") == []
