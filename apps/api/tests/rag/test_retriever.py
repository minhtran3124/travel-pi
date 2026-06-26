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


def test_ingest_places_stable_ids_no_duplicate(seeded_session):
    """Re-ingesting the same places upserts rather than appending duplicates."""
    from app.rag.embeddings import get_vector_store
    from app.rag.ingest import ingest_places

    store = get_vector_store(database_url="sqlite:///:memory:")
    count = ingest_places(store, seeded_session)
    assert count > 0
    # Second ingest — doc count in the store must not grow
    ingest_places(store, seeded_session)
    hits = store.similarity_search("place", k=count * 2 + 1)
    assert len(hits) <= count


def test_hybrid_search_filter_during_fetch_no_starvation():
    """Filter is pushed into similarity_search so matching docs are never starved.

    With 2 matching docs (city="Rare") among 25 filler docs and k=5,
    InMemoryVectorStore pre-filters to the 2 matching docs and returns both.
    A post-filter applied after an unfiltered fetch_k=5 draw could easily miss them.
    """
    from app.rag.embeddings import get_vector_store
    from app.rag.retriever import hybrid_search

    store = get_vector_store(database_url="sqlite:///:memory:")
    rare_docs = [
        Document(page_content="museum exhibit", metadata={"city": "Rare"}),
        Document(page_content="art gallery", metadata={"city": "Rare"}),
    ]
    filler_docs = [
        Document(page_content=f"filler {i}", metadata={"city": "Other"})
        for i in range(25)
    ]
    store.add_documents(rare_docs + filler_docs)

    results = hybrid_search(store, "museum", filters={"city": "Rare"}, k=5)
    assert len(results) == 2
    assert all(d.metadata["city"] == "Rare" for d in results)


def test_hybrid_search_no_filter_returns_top_k():
    """filters=None returns the unfiltered top-k (backward-compat)."""
    from app.rag.embeddings import get_vector_store
    from app.rag.retriever import hybrid_search

    store = get_vector_store(database_url="sqlite:///:memory:")
    docs = [
        Document(page_content=f"document {i}", metadata={"idx": i}) for i in range(10)
    ]
    store.add_documents(docs)

    results = hybrid_search(store, "document", k=3)
    assert len(results) == 3
