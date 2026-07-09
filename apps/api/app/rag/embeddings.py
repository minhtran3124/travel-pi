"""Embeddings + vector store selection (specs/travel-knowledge-rag).

RAG over visa + local-tips content. ``get_embeddings()`` is sourced from the
shared :mod:`app.core.embeddings` (it already selects OpenAI when a key is
configured and a deterministic fake otherwise, so local dev and the test suite
embed without a key or network). ``get_vector_store()`` uses pgvector
(``langchain-postgres`` ``PGVector``) on Postgres and an :class:`InMemoryVectorStore`
elsewhere; pgvector RAG is therefore a Postgres/docker capability, with
SQLite/tests exercising the same code path against the in-memory store.

Two changes vs. the deleted original (``specs/remove-rag-feature`` recovered it
from git ``3d0dc6a^``):

1. **Cached singleton keyed by database URL.** ``InMemoryVectorStore`` is
   per-instance — its state does not persist across calls — so the old tool
   returned *nothing* on SQLite/tests unless a test ingested in-process. Caching
   the store per URL (plus auto-ingest at startup, see ``core/lifespan``) makes
   the tool work out-of-the-box on every backend. ``reset_vector_store`` clears
   the cache for test isolation, mirroring ``weather_service.clear_geocode_cache``.
2. ``PGVector``'s constructor now takes ``embeddings`` positionally (it used to be
   keyword-only after ``connection``); the call here passes both as keywords so it
   is explicit and version-tolerant.
"""

from __future__ import annotations

from functools import lru_cache

from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore, VectorStore

from app.core.config import get_settings
from app.core.embeddings import get_embeddings

DEFAULT_COLLECTION = "travel_knowledge"
# Collection name for the visa + local-tips + country-summary documents. Distinct
# from the old ``travel_pois`` (places) collection so a Postgres deployment that
# still has the orphaned places collection does not mix scopes.


def _build_store(embeddings: Embeddings, url: str, collection: str) -> VectorStore:
    """Select the vector store backend by URL (single source for the choice).

    Postgres URL -> ``PGVector`` (pgvector, persists the collection); anything
    else -> :class:`InMemoryVectorStore`. Shared by both the cached path and the
    caller-supplied-embeddings path so the backend choice lives in one place.

    :param embeddings: Embedding model the store will use.
    :param url: Database URL used to select the backend.
    :param collection: Vector store collection/table name (pgvector only).
    :return: The vector store.
    """
    if url.startswith("postgres"):
        from langchain_postgres import PGVector

        return PGVector(
            embeddings=embeddings,
            connection=url,
            collection_name=collection,
        )
    return InMemoryVectorStore(embeddings)


@lru_cache(maxsize=8)
def _get_vector_store_cached(
    database_url: str,
    *,
    collection: str,
) -> VectorStore:
    """Return (and cache) the vector store for the configured backend.

    Cached per ``(database_url, collection)`` so repeated calls in one process
    share one store instance — essential for ``InMemoryVectorStore``, whose state
    lives on the instance. ``reset_vector_store`` clears the cache.

    :param database_url: Database URL used to select the backend.
    :param collection: Vector store collection/table name.
    :return: The (cached) vector store.
    """
    return _build_store(get_embeddings(), database_url, collection)


def get_vector_store(
    embeddings: Embeddings | None = None,
    *,
    collection: str = DEFAULT_COLLECTION,
    database_url: str | None = None,
) -> VectorStore:
    """Return the vector store for the configured backend (pgvector / in-memory).

    Postgres URL -> ``PGVector`` (pgvector cosine, persists the collection across
    restarts). Anything else -> :class:`InMemoryVectorStore` (SQLite local/dev and
    the test suite). When *embeddings* is given the store is built freshly and is
    NOT cached (a caller passing its own embeddings — e.g. a test wanting a
    specific fake — expects a private instance), preserving the old call shape.

    :param embeddings: Embedding model to use; defaults to ``get_embeddings()``.
        When provided, the returned store is not cached.
    :param collection: Vector store collection/table name.
    :param database_url: Database URL used to select the backend; defaults to
        ``settings.database_url``.
    :return: The vector store.
    """
    if embeddings is not None:
        url = database_url or get_settings().database_url
        return _build_store(embeddings, url, collection)
    url = database_url or get_settings().database_url
    return _get_vector_store_cached(url, collection=collection)


def reset_vector_store() -> None:
    """Clear the cached vector store(s) (test isolation / re-seed).

    Mirrors ``weather_service.clear_geocode_cache``: tests that point
    ``DATABASE_URL`` at a fresh temp DB must not reuse a store cached against the
    previous URL. Call this in a fixture's setup/teardown when the test changes
    the database URL.

    :return: None.
    """
    _get_vector_store_cached.cache_clear()


__all__ = [
    "DEFAULT_COLLECTION",
    "get_embeddings",
    "get_vector_store",
    "reset_vector_store",
]
