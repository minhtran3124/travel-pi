"""Long-term cross-session memory (specs/travel-agent Task 2.2).

The LangGraph Store holds memory that outlives a single thread — the traveller's
preferences and past-trip facts, addressable by ``(namespace, key)`` and
retrievable across different conversations. Postgres in docker/prod (pgvector
semantic search), in-memory locally / in tests. Selection mirrors the engine and
checkpointer split and degrades to ``InMemoryStore`` if the backend fails.
"""

from __future__ import annotations

import logging

from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def get_store(database_url: str | None = None) -> BaseStore:
    """Return the long-term memory store for the configured backend."""
    url = database_url or get_settings().database_url
    if url.startswith("postgres"):
        try:
            from langgraph.store.postgres import PostgresStore

            store = PostgresStore.from_conn_string(url).__enter__()
            store.setup()
            return store
        except Exception:
            logger.exception("PostgresStore init failed; using InMemoryStore")
    return InMemoryStore()


def _prefs_namespace(user_id: str) -> tuple[str, str, str]:
    return ("users", user_id, "prefs")


def upsert_preference(store: BaseStore, user_id: str, key: str, value: dict) -> None:
    """Store/overwrite a single user preference (value must be a JSON dict)."""
    store.put(_prefs_namespace(user_id), key, value)


def search_preferences(
    store: BaseStore, user_id: str, *, query: str | None = None, limit: int = 5
) -> list[dict]:
    """Return preference values for a user (semantic when the backend supports it)."""
    results = store.search(_prefs_namespace(user_id), query=query, limit=limit)
    return [item.value for item in results]
