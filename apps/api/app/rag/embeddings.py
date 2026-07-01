"""Embeddings + vector store selection (specs/travel-agent Task 4.1).

RAG over destination/POI/tip content. ``get_embeddings()`` uses OpenAI when a key
is configured and a deterministic fake otherwise — so local dev and the test
suite embed without a key or network. ``get_vector_store()`` uses pgvector
(``langchain-postgres`` PGVector) on Postgres and an in-memory store elsewhere;
pgvector RAG is therefore a Postgres/docker capability, with SQLite/tests
exercising the same code path against the in-memory store.
"""

from __future__ import annotations

from langchain_core.embeddings import DeterministicFakeEmbedding, Embeddings
from langchain_core.vectorstores import InMemoryVectorStore, VectorStore

from app.core.config import get_settings

DEFAULT_COLLECTION = "travel_pois"
EMBED_DIM = 1536  # text-embedding-3-small dim; shared by RAG + the memory-store index
_FAKE_EMBED_DIM = EMBED_DIM  # the fake matches so dims are stable across modes


def get_embeddings() -> Embeddings:
    """Return the embedding model: OpenAI when keyed, deterministic fake otherwise.

    :return: The embedding model.
    """
    s = get_settings()
    if s.openai_api_key:
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(model=s.embedding_model, api_key=s.openai_api_key)
    return DeterministicFakeEmbedding(size=_FAKE_EMBED_DIM)


def get_vector_store(
    embeddings: Embeddings | None = None,
    *,
    collection: str = DEFAULT_COLLECTION,
    database_url: str | None = None,
) -> VectorStore:
    """Return the vector store for the configured backend (pgvector / in-memory).

    :param embeddings: Embedding model to use; defaults to ``get_embeddings()``.
    :param collection: Vector store collection/table name.
    :param database_url: Database URL used to select the backend; defaults to settings.
    :return: The vector store.
    """
    emb = embeddings or get_embeddings()
    url = database_url or get_settings().database_url
    if url.startswith("postgres"):
        from langchain_postgres import PGVector

        return PGVector(connection=url, collection_name=collection, embeddings=emb)
    return InMemoryVectorStore(emb)
