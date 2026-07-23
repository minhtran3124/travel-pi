"""Vector store selection + embeddings (specs/travel-knowledge-rag).

Tests ``app.rag.embeddings.get_vector_store`` (pgvector/InMemory selection, the
cached singleton, and ``reset_vector_store``) plus one check that
``app.core.embeddings.get_embeddings`` falls back to the deterministic fake when
no OpenAI key is set. Renamed from ``test_embeddings.py`` to avoid a pytest
basename collision with ``tests/core/test_embeddings.py`` (the survivor of
``specs/remove-rag-feature``).
"""

from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.vectorstores import InMemoryVectorStore


def test_get_vector_store_in_memory_for_sqlite(reset_store, fake_embeddings):
    from app.rag.embeddings import get_vector_store

    store = get_vector_store(database_url="sqlite:///:memory:")
    assert isinstance(store, InMemoryVectorStore)


def test_get_vector_store_is_cached_singleton(reset_store, fake_embeddings):
    """Same URL + collection returns the same cached store instance."""
    from app.rag.embeddings import get_vector_store

    a = get_vector_store(database_url="sqlite:///:memory:")
    b = get_vector_store(database_url="sqlite:///:memory:")
    assert a is b


def test_get_vector_store_different_url_is_different_instance(
    reset_store, fake_embeddings
):
    from app.rag.embeddings import get_vector_store

    a = get_vector_store(database_url="sqlite:///one.db")
    b = get_vector_store(database_url="sqlite:///two.db")
    assert a is not b


def test_reset_vector_store_clears_cache(reset_store, fake_embeddings):
    from app.rag.embeddings import get_vector_store, reset_vector_store

    a = get_vector_store(database_url="sqlite:///:memory:")
    reset_vector_store()
    b = get_vector_store(database_url="sqlite:///:memory:")
    assert a is not b


def test_concurrent_get_vector_store_builds_once(
    reset_store, fake_embeddings, monkeypatch
):
    """Concurrent cold-cache access builds exactly one store (thread-safe cache).

    Guards the fix for the race where ``PGVector``'s non-thread-safe global table
    registration raised ``Table ... already defined``: without serialized
    construction, N threads racing a cold cache each build. The double-checked
    lock builds once. Uses a stub ``_build_store`` so the test needs no Postgres.
    """
    import threading
    import time

    import app.rag.embeddings as e

    builds: list[tuple[str, str]] = []

    def slow_build(embeddings, url, collection):
        time.sleep(0.02)  # widen the race window so a broken impl double-builds
        builds.append((url, collection))
        return object()  # sentinel store; identity is what the test checks

    monkeypatch.setattr(e, "_build_store", slow_build)

    start = threading.Barrier(8)
    results: list[object] = []

    def worker():
        start.wait()  # release all racers into the cache-miss path together
        results.append(e.get_vector_store(database_url="sqlite:///race.db"))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(builds) == 1  # built exactly once despite 8 concurrent racers
    assert len({id(r) for r in results}) == 1  # all share the single instance


def test_explicit_embeddings_not_cached(reset_store, fake_embeddings):
    """A caller passing its own embeddings gets a private, uncached instance."""
    from app.rag.embeddings import get_vector_store

    emb = DeterministicFakeEmbedding(size=1536)
    a = get_vector_store(embeddings=emb, database_url="sqlite:///:memory:")
    b = get_vector_store(embeddings=emb, database_url="sqlite:///:memory:")
    assert a is not b


def test_get_embeddings_fake_without_key(monkeypatch):
    """get_embeddings() returns the fake when openai_api_key is unset.

    ``apps/api/.env`` may carry a real key in dev; patch the cached settings'
    field directly (env_file is read at construction, so ``delenv`` alone is not
    enough). Keep the patched instance cached so ``get_settings()`` sees the
    cleared key — do NOT clear the cache after patching (that would rebuild from
    .env and re-load the key).
    """
    from app.core.config import get_settings
    from langchain_core.embeddings import DeterministicFakeEmbedding

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()
    s = get_settings()
    monkeypatch.setattr(s, "openai_api_key", None)

    from app.core.embeddings import get_embeddings

    emb = get_embeddings()
    assert isinstance(emb, DeterministicFakeEmbedding)
    # deterministic: same text -> same vector
    assert emb.embed_query("Vietnam") == emb.embed_query("Vietnam")
