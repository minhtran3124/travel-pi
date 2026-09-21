"""Memory delete + unfiltered listing (specs/agent-memory-layer-5 Task 1.1, SC-5).

``delete_memory`` removes a row by ``(kind, key)`` and is idempotent. ``list_memory``
lists a kind's rows *preserving the store key* (plain ``search_memory`` drops it; the key
is the future UI's delete handle).

The InMemoryStore case runs everywhere. The indexed ``PostgresStore`` case is a regression
pin on ``store_vectors``' ``FOREIGN KEY (prefix, key) REFERENCES store(prefix, key)
ON DELETE CASCADE`` (langgraph 1.2.6, ``langgraph/store/postgres/base.py:104-112``): one
``store.delete`` must remove the pgvector embedding row too. It only runs when DATABASE_URL
points at Postgres, and *must* use an indexed store — the cascade ships in VECTOR_MIGRATIONS,
so a store built without an index has no store_vectors table to pin.
"""

import os

import pytest

_DB_URL = os.environ.get("DATABASE_URL", "")
_IS_POSTGRES = _DB_URL.startswith("postgres")


def test_list_memory_preserves_key_and_updated_at():
    """list_memory returns rows carrying the store key and updated_at."""
    from app.memory.store import get_store, list_memory, upsert_preference

    store = get_store("sqlite:///:memory:")
    upsert_preference(store, "u1", "diet", {"text": "vegetarian"})

    rows = list_memory(store, "u1", "prefs")
    assert len(rows) == 1
    assert rows[0]["key"] == "diet"
    assert rows[0]["text"] == "vegetarian"
    assert "updated_at" in rows[0]


def test_list_memory_rejects_unknown_kind():
    from app.memory.store import get_store, list_memory

    store = get_store("sqlite:///:memory:")
    with pytest.raises(ValueError):
        list_memory(store, "u1", "bogus")


def test_delete_then_search_returns_nothing_inmemory():
    """Deleting a key removes it from a subsequent search (InMemoryStore)."""
    from app.memory.store import (
        delete_memory,
        get_store,
        list_memory,
        search_preferences,
        upsert_preference,
    )

    store = get_store("sqlite:///:memory:")
    upsert_preference(store, "u1", "diet", {"text": "vegetarian"})
    assert len(search_preferences(store, "u1")) == 1

    assert delete_memory(store, "u1", "prefs", "diet") is True
    assert search_preferences(store, "u1") == []
    assert list_memory(store, "u1", "prefs") == []


def test_delete_missing_key_is_noop_inmemory():
    """Deleting an absent key is not an error (idempotent)."""
    from app.memory.store import delete_memory, get_store

    store = get_store("sqlite:///:memory:")
    # Never stored — must not raise.
    assert delete_memory(store, "u1", "prefs", "never-existed") is True
    # Delete twice in a row is fine too.
    from app.memory.store import upsert_preference

    upsert_preference(store, "u1", "diet", {"text": "veg"})
    assert delete_memory(store, "u1", "prefs", "diet") is True
    assert delete_memory(store, "u1", "prefs", "diet") is True


def test_delete_rejects_unknown_kind_before_namespace():
    """An unknown kind raises rather than being interpolated into a namespace."""
    from app.memory.store import delete_memory, get_store

    store = get_store("sqlite:///:memory:")
    with pytest.raises(ValueError):
        delete_memory(store, "u1", "bogus", "diet")


@pytest.mark.skipif(
    not _IS_POSTGRES,
    reason="Postgres cascade pin: DATABASE_URL is not Postgres (InMemoryStore covers the rest).",
)
def test_delete_cascades_pgvector_row_on_indexed_postgres():
    """Regression pin: delete removes the embedding row via ON DELETE CASCADE.

    Uses an *indexed* PostgresStore so store_vectors exists; a subsequent semantic
    search returning nothing proves the embedding row went with the base row.
    """
    from app.memory.store import (
        _index_config,
        _libpq_dsn,
        delete_memory,
        search_preferences,
        upsert_preference,
    )
    from langgraph.store.postgres import PostgresStore

    uid = f"del-test-{os.getpid()}"
    with PostgresStore.from_conn_string(
        _libpq_dsn(_DB_URL), index=_index_config()
    ) as store:
        store.setup()
        upsert_preference(store, uid, "diet", {"text": "vegetarian slow food"})
        # Semantic search hits the store_vectors table.
        assert len(search_preferences(store, uid, query="food")) == 1

        assert delete_memory(store, uid, "prefs", "diet") is True

        # Both keyed and semantic search must now be empty.
        assert search_preferences(store, uid) == []
        assert search_preferences(store, uid, query="food") == []
