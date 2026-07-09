"""Ingest + hybrid retriever (specs/travel-knowledge-rag)."""

from langchain_core.documents import Document


def test_chunk_text_splits_long_prose():
    from app.rag.ingest import chunk_text

    long = "word " * 500
    chunks = chunk_text(long)
    assert len(chunks) > 1


def test_chunk_text_short_passthrough():
    from app.rag.ingest import chunk_text

    assert chunk_text("a short tip") == ["a short tip"]


def test_lexical_score_ignores_punctuation():
    """Punctuated natural-language tokens still overlap (regression: str.split)."""
    from app.rag.retriever import _lexical_score

    doc = Document(page_content="Visa-free stay in Vietnam. 45 days.")
    # 'visa'/'vietnam' from the query overlap the doc once punctuation/hyphens are
    # stripped; a naive whitespace split ('Vietnam?' vs 'Vietnam.') would score 0.
    assert _lexical_score("do I need a visa for Vietnam?", doc) >= 2


def test_hybrid_search_empty_store(reset_store, fake_embeddings):
    from app.rag.embeddings import get_vector_store
    from app.rag.retriever import hybrid_search

    store = get_vector_store(database_url="sqlite:///:memory:")
    assert hybrid_search(store, "anything") == []


def test_hybrid_search_metadata_filter(reset_store, fake_embeddings):
    from app.rag.embeddings import get_vector_store
    from app.rag.retriever import hybrid_search

    store = get_vector_store(database_url="sqlite:///:memory:")
    store.add_documents(
        [
            Document(page_content="ramen in Shinjuku", metadata={"country": "Japan"}),
            Document(
                page_content="ramen by the beach", metadata={"country": "Vietnam"}
            ),
            Document(page_content="sushi counter", metadata={"country": "Japan"}),
        ]
    )
    results = hybrid_search(store, "ramen", filters={"country": "Japan"}, k=5)
    assert results
    assert all(d.metadata["country"] == "Japan" for d in results)


def test_hybrid_search_filter_during_fetch_no_starvation(reset_store, fake_embeddings):
    """Filter is pushed into similarity_search so matching docs are never starved.

    With 2 matching docs (country="Rare") among 25 filler docs and k=5,
    InMemoryVectorStore pre-filters to the 2 matching docs and returns both.
    A post-filter applied after an unfiltered fetch_k draw could easily miss them.
    """
    from app.rag.embeddings import get_vector_store
    from app.rag.retriever import hybrid_search

    store = get_vector_store(database_url="sqlite:///:memory:")
    rare_docs = [
        Document(page_content="museum exhibit", metadata={"country": "Rare"}),
        Document(page_content="art gallery", metadata={"country": "Rare"}),
    ]
    filler_docs = [
        Document(page_content=f"filler {i}", metadata={"country": "Other"})
        for i in range(25)
    ]
    store.add_documents(rare_docs + filler_docs)

    results = hybrid_search(store, "museum", filters={"country": "Rare"}, k=5)
    assert len(results) == 2
    assert all(d.metadata["country"] == "Rare" for d in results)


def test_hybrid_search_no_filter_returns_top_k(reset_store, fake_embeddings):
    """filters=None returns the unfiltered top-k."""
    from app.rag.embeddings import get_vector_store
    from app.rag.retriever import hybrid_search

    store = get_vector_store(database_url="sqlite:///:memory:")
    docs = [
        Document(page_content=f"document {i}", metadata={"idx": i}) for i in range(10)
    ]
    store.add_documents(docs)

    results = hybrid_search(store, "document", k=3)
    assert len(results) == 3


def test_ingest_knowledge_into_store(seeded_session, reset_store, fake_embeddings):
    from app.rag.embeddings import get_vector_store
    from app.rag.ingest import ingest_knowledge

    store = get_vector_store(database_url="sqlite:///:memory:")
    count = ingest_knowledge(store, seeded_session)
    assert count > 0
    hits = store.similarity_search("visa", k=1)
    assert hits


def test_ingest_knowledge_stable_ids_no_duplicate(
    seeded_session, reset_store, fake_embeddings
):
    """Re-ingesting the same corpus upserts rather than appending duplicates."""
    from app.rag.embeddings import get_vector_store
    from app.rag.ingest import ingest_knowledge

    store = get_vector_store(database_url="sqlite:///:memory:")
    count = ingest_knowledge(store, seeded_session)
    assert count > 0
    # Second ingest — doc count in the store must not grow.
    ingest_knowledge(store, seeded_session)
    hits = store.similarity_search("travel", k=count * 2 + 1)
    assert len(hits) <= count
