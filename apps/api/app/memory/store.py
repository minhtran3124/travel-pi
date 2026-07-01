"""Long-term cross-session memory (specs/travel-agent Task 2.2; agent-graph-lifecycle;
agent-memory-semantic).

The LangGraph Store holds memory that outlives a single thread — the traveller's
preferences and past-trip facts, addressable by ``(namespace, key)`` and retrievable
across different conversations.

Built **once** in the app ``lifespan`` via :func:`open_store` (a context manager held
open for the process lifetime) rather than per request. Postgres in docker/prod;
``InMemoryStore`` locally / in tests and as the degrade path.

Both backends are constructed with a semantic ``index`` (REVIEW.md C3) so
``store.search(ns, query=...)`` ranks by embedding similarity — without it, ``query`` is
silently ignored and search degrades to recency. The index embeds the ``text`` field of
each stored value using the shared ``app.rag.embeddings`` model (real OpenAI when keyed,
deterministic fake otherwise). On a Postgres image without pgvector the indexed
``PostgresStore`` fails to initialise and degrades to an indexed ``InMemoryStore``.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum

from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore
from langgraph.store.postgres import PostgresStore

from app.core.config import get_settings
from app.rag.embeddings import EMBED_DIM, get_embeddings

logger = logging.getLogger(__name__)


def _libpq_dsn(url: str) -> str:
    """Strip SQLAlchemy's ``+driver`` so psycopg/libpq accepts the DSN."""
    return url.replace("postgresql+psycopg://", "postgresql://").replace(
        "postgres+psycopg://", "postgresql://"
    )


def _index_config() -> dict:
    """Semantic-search index for the store: embed the ``text`` field of each value."""
    return {
        "dims": EMBED_DIM,
        "embed": get_embeddings(),
        "fields": ["text"],
    }


@asynccontextmanager
async def open_store(database_url: str | None = None) -> AsyncIterator[BaseStore]:
    """Yield the long-term store for the app's lifetime (``lifespan``-managed).

    Postgres URL -> ``PostgresStore`` with a pgvector semantic index (tables created via
    ``setup()``), opened once and closed on shutdown. Anything else, or any init failure
    (e.g. a Postgres image without pgvector) -> an indexed ``InMemoryStore``.
    """
    url = database_url or get_settings().database_url
    if url.startswith("postgres"):
        try:
            with PostgresStore.from_conn_string(
                _libpq_dsn(url), index=_index_config()
            ) as store:
                store.setup()
                yield store
            return
        except Exception:
            logger.exception(
                "PostgresStore init failed for %s; using InMemoryStore", url
            )

    yield InMemoryStore(index=_index_config())


def get_store(database_url: str | None = None) -> BaseStore:
    """Indexed in-memory store for tests / non-Postgres degrade.

    Production code builds the durable store through :func:`open_store` so its
    connection is lifecycle-managed; this sync helper exists only for the ephemeral
    in-memory case. It carries the same semantic index so ``query`` search works.
    """
    return InMemoryStore(index=_index_config())


def _namespace(user_id: str, kind: str) -> tuple[str, str, str]:
    return ("users", user_id, kind)


def _prefs_namespace(user_id: str) -> tuple[str, str, str]:
    return _namespace(user_id, "prefs")


def upsert_preference(store: BaseStore, user_id: str, key: str, value: dict) -> None:
    """
    Store/overwrite a single user preference (value must be a JSON dict).
    """
    store.put(_prefs_namespace(user_id), key, value)


def search_preferences(
    store: BaseStore, user_id: str, *, query: str | None = None, limit: int = 5
) -> list[dict]:
    """Return preference values for a user (semantic when a query is given)."""
    results = store.search(_prefs_namespace(user_id), query=query, limit=limit)
    return [item.value for item in results]


def upsert_instruction(store: BaseStore, user_id: str, key: str, value: dict) -> None:
    """Store/overwrite a single procedural instruction (value must be a JSON dict
    with a ``text`` field so the semantic index works)."""
    store.put(_namespace(user_id, "procedural"), key, value)


def get_instructions(
    store: BaseStore, user_id: str, *, query: str | None = None, limit: int = 10
) -> list[dict]:
    """Return procedural instruction values for a user (semantic when a query is given)."""
    results = store.search(_namespace(user_id, "procedural"), query=query, limit=limit)
    return [item.value for item in results]


def upsert_episode(store: BaseStore, user_id: str, key: str, value: dict) -> None:
    """Store/overwrite a single episodic memory — a past-trip outcome (value is a
    JSON dict whose ``text`` field is embedded by the semantic index; ``trip_id`` /
    ``city`` / ``outcome`` are stored metadata). Key-addressed (overwrite, not
    append); the natural key is ``trip_id`` so re-extracting a trip is idempotent.
    """
    store.put(_namespace(user_id, "episodes"), key, value)


def search_episodes(
    store: BaseStore, user_id: str, *, query: str | None = None, limit: int = 3
) -> list[dict]:
    """Return episodic-memory values for a user (semantic when a query is given)."""
    results = store.search(_namespace(user_id, "episodes"), query=query, limit=limit)
    return [item.value for item in results]
# --- Structured namespaces: typed search (research P2 row 2) -----------------
# The three memory kinds are isolated under ("users", user_id, <kind>). This block
# makes that structure explicit and typed: a MemoryKind enum (single source of
# truth for the valid kinds), a unified search_memory dispatcher, and typed result
# dataclasses (Preference / Instruction / Episode) so callers can opt into typed
# access instead of raw dicts. The per-kind helpers above stay unchanged.


class MemoryKind(str, Enum):
    """The three structured long-term memory kinds (LangChain memory taxonomy)."""

    PREFERENCES = "prefs"
    PROCEDURAL = "procedural"
    EPISODES = "episodes"


# Per-kind default recall limits (mirror the per-kind helpers' defaults).
_DEFAULT_SEARCH_LIMITS: dict[MemoryKind, int] = {
    MemoryKind.PREFERENCES: 5,
    MemoryKind.PROCEDURAL: 10,
    MemoryKind.EPISODES: 3,
}


@dataclass
class Preference:
    """A typed traveller preference (semantic memory)."""

    key: str
    text: str

    @classmethod
    def from_item(cls, item) -> "Preference":
        return cls(key=item.key, text=item.value.get("text", ""))


@dataclass
class Instruction:
    """A typed standing instruction (procedural memory)."""

    key: str
    text: str

    @classmethod
    def from_item(cls, item) -> "Instruction":
        return cls(key=item.key, text=item.value.get("text", ""))


@dataclass
class Episode:
    """A typed past-trip outcome (episodic memory)."""

    key: str
    text: str
    trip_id: str | None = None
    city: str | None = None
    outcome: str = "proposed"

    @classmethod
    def from_item(cls, item) -> "Episode":
        v = item.value
        return cls(
            key=item.key,
            text=v.get("text", ""),
            trip_id=v.get("trip_id"),
            city=v.get("city"),
            outcome=v.get("outcome", "proposed"),
        )


_MEMORY_RESULT_TYPES: dict[MemoryKind, type] = {
    MemoryKind.PREFERENCES: Preference,
    MemoryKind.PROCEDURAL: Instruction,
    MemoryKind.EPISODES: Episode,
}


def search_memory(
    store: BaseStore,
    user_id: str,
    kind: MemoryKind | str,
    *,
    query: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Unified dispatcher over the structured memory namespaces.

    Validates *kind* against :class:`MemoryKind`, resolves the
    ``("users", user_id, kind)`` namespace, and returns the matching values as
    dicts (semantic ranking when *query* is given). When *limit* is ``None`` the
    per-kind default is used (prefs=5, procedural=10, episodes=3).
    """
    kind = MemoryKind(kind)
    ns = _namespace(user_id, kind.value)
    eff_limit = limit if limit is not None else _DEFAULT_SEARCH_LIMITS[kind]
    return [item.value for item in store.search(ns, query=query, limit=eff_limit)]


def search_memory_typed(
    store: BaseStore,
    user_id: str,
    kind: MemoryKind | str,
    *,
    query: str | None = None,
    limit: int | None = None,
) -> list[Preference | Instruction | Episode]:
    """Typed variant of :func:`search_memory`.

    Returns ``Preference`` / ``Instruction`` / ``Episode`` dataclass instances
    (selected by *kind*) instead of raw dicts, so callers get typed, named fields
    including the store key.
    """
    kind = MemoryKind(kind)
    ns = _namespace(user_id, kind.value)
    eff_limit = limit if limit is not None else _DEFAULT_SEARCH_LIMITS[kind]
    result_type = _MEMORY_RESULT_TYPES[kind]
    return [result_type.from_item(item) for item in store.search(ns, query=query, limit=eff_limit)]

