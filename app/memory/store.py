"""Long-term cross-session memory (specs/travel-agent Task 2.2; agent-graph-lifecycle).

The LangGraph Store holds memory that outlives a single thread — the traveller's
preferences and past-trip facts, addressable by ``(namespace, key)`` and retrievable
across different conversations.

Per ``specs/agent-graph-lifecycle`` the store is built **once** in the app ``lifespan``
via :func:`open_store` (a context manager held open for the process lifetime) rather
than per request. Postgres in docker/prod; ``InMemoryStore`` locally / in tests and as
the degrade path. (Semantic-search indexing — REVIEW.md C3 — is a separate follow-up;
the store stays sync here so the sync memory tools keep working.)
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _libpq_dsn(url: str) -> str:
    """Strip SQLAlchemy's ``+driver`` so psycopg/libpq accepts the DSN."""
    return url.replace("postgresql+psycopg://", "postgresql://").replace(
        "postgres+psycopg://", "postgresql://"
    )


@asynccontextmanager
async def open_store(database_url: str | None = None) -> AsyncIterator[BaseStore]:
    """Yield the long-term store for the app's lifetime (``lifespan``-managed).

    Postgres URL -> ``PostgresStore`` (tables created via ``setup()``), opened once and
    closed on shutdown. Anything else, or any init failure -> ``InMemoryStore``.
    """
    url = database_url or get_settings().database_url
    if url.startswith("postgres"):
        try:
            from langgraph.store.postgres import PostgresStore

            with PostgresStore.from_conn_string(_libpq_dsn(url)) as store:
                store.setup()
                yield store
            return
        except Exception:
            logger.exception(
                "PostgresStore init failed for %s; using InMemoryStore", url
            )
    yield InMemoryStore()


def get_store(database_url: str | None = None) -> BaseStore:
    """In-memory store for tests / non-Postgres degrade.

    Production code builds the durable store through :func:`open_store` so its
    connection is lifecycle-managed; this sync helper exists only for the ephemeral
    in-memory case.
    """
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
