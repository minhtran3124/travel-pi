"""Embeddings + vector store selection for RAG over visa + local-tips content.

``get_vector_store()`` uses pgvector on Postgres and an :class:`InMemoryVectorStore` elsewhere. The
store is cached per database URL because ``InMemoryVectorStore`` state lives on the instance, so
without caching it would return nothing on SQLite/tests.
"""

from __future__ import annotations

import threading

from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore, VectorStore

from app.core.config import get_settings
from app.core.embeddings import get_embeddings

DEFAULT_COLLECTION = "travel_knowledge"

# Serializes PGVector's first construction, which registers ORM tables on a process-global Base that
# is not thread-safe (racing builds raise "Table ... already defined"). Reentrant so the cached path
# can hold it while _build_store re-acquires it.
_build_lock = threading.RLock()
_store_cache: dict[tuple[str, str], VectorStore] = {}


def _build_store(embeddings: Embeddings, url: str, collection: str) -> VectorStore:
    """Select the vector store backend by URL: Postgres -> ``PGVector``, anything else -> in-memory."""
    if url.startswith("postgres"):
        from langchain_postgres import PGVector

        with _build_lock:
            return PGVector(
                embeddings=embeddings,
                connection=url,
                collection_name=collection,
            )
    return InMemoryVectorStore(embeddings)


def _get_vector_store_cached(
    database_url: str,
    *,
    collection: str,
) -> VectorStore:
    """Return (and cache) the vector store per ``(database_url, collection)``. Double-checked locking,
    not ``lru_cache``, so concurrent cold misses can't each build a ``PGVector`` and collide on its
    non-thread-safe global table registration."""
    key = (database_url, collection)
    store = _store_cache.get(key)
    if store is not None:
        return store
    with _build_lock:
        store = _store_cache.get(key)  # re-check: another thread may have built it
        if store is None:
            store = _build_store(get_embeddings(), database_url, collection)
            _store_cache[key] = store
        return store


def get_vector_store(
    embeddings: Embeddings | None = None,
    *,
    collection: str = DEFAULT_COLLECTION,
    database_url: str | None = None,
) -> VectorStore:
    """Return the vector store for the configured backend. When *embeddings* is given the store is built
    freshly and NOT cached, since such a caller expects a private instance."""
    if embeddings is not None:
        url = database_url or get_settings().database_url
        return _build_store(embeddings, url, collection)
    url = database_url or get_settings().database_url
    return _get_vector_store_cached(url, collection=collection)


def reset_vector_store() -> None:
    """Clear the cached vector store(s) so a test pointing ``DATABASE_URL`` at a fresh DB does not reuse
    a store cached against the previous URL."""
    with _build_lock:
        _store_cache.clear()


__all__ = [
    "DEFAULT_COLLECTION",
    "get_embeddings",
    "get_vector_store",
    "reset_vector_store",
]
