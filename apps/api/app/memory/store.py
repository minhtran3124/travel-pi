"""Long-term cross-session memory: preferences and past-trip facts keyed by
``(namespace, key)``, backed by an embedding-indexed LangGraph Store.

Built once in the app ``lifespan`` via :func:`open_store`. A Postgres image
without pgvector degrades to an indexed ``InMemoryStore``. Without the semantic
index, ``query`` is silently ignored and search degrades to recency.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore
from langgraph.store.postgres import PostgresStore

from app.core.config import get_settings
from app.core.embeddings import EMBED_DIM, get_embeddings

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

    Postgres URL -> ``PostgresStore`` with a pgvector semantic index; anything
    else, or any init failure, -> an indexed ``InMemoryStore``.
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

    Production builds the durable store through :func:`open_store`; this sync
    helper exists only for the ephemeral in-memory case. ``database_url`` is
    unused, accepted for interface symmetry.
    """
    return InMemoryStore(index=_index_config())


def _namespace(user_id: str, kind: str) -> tuple[str, str, str]:
    return ("users", user_id, kind)


def _prefs_namespace(user_id: str) -> tuple[str, str, str]:
    return _namespace(user_id, "prefs")


def _stamped(value: dict) -> dict:
    """Return a shallow copy of *value* with ``updated_at`` set to now (UTC)."""
    return {**value, "updated_at": datetime.now(timezone.utc).isoformat()}


def upsert_preference(store: BaseStore, user_id: str, key: str, value: dict) -> None:
    """Store/overwrite a single user preference (value must be a JSON dict)."""
    store.put(_prefs_namespace(user_id), key, _stamped(value))


def search_preferences(
    store: BaseStore, user_id: str, *, query: str | None = None, limit: int = 5
) -> list[dict]:
    """Return preference values for a user (semantic when a query is given)."""
    results = store.search(_prefs_namespace(user_id), query=query, limit=limit)
    return [item.value for item in results]


# Reserved preference keys that ride the prefs namespace and are auto-injected each turn.
PROFILE_KEYS: tuple[str, ...] = ("name", "gender", "travel_group")


def get_profile(store: BaseStore, user_id: str) -> dict[str, str]:
    """Return ``{key: text}`` for each :data:`PROFILE_KEYS` present with non-blank text.

    Uses direct keyed ``store.get`` rather than semantic ``search_preferences`` so
    the fields are exact and never reordered/dropped by similarity ranking.
    """
    profile: dict[str, str] = {}
    for key in PROFILE_KEYS:
        item = store.get(_prefs_namespace(user_id), key)
        if item is not None:
            raw = item.value.get("text")
            text = raw.strip() if isinstance(raw, str) else ""
            if text:
                profile[key] = text
    return profile


def upsert_instruction(store: BaseStore, user_id: str, key: str, value: dict) -> None:
    """Store/overwrite a single procedural instruction (value must be a JSON dict
    with a ``text`` field so the semantic index works)."""
    store.put(_namespace(user_id, "procedural"), key, _stamped(value))


def get_instructions(
    store: BaseStore, user_id: str, *, query: str | None = None, limit: int = 10
) -> list[dict]:
    """Return procedural instruction values for a user (semantic when a query is given)."""
    results = store.search(_namespace(user_id, "procedural"), query=query, limit=limit)
    return [item.value for item in results]


def upsert_episode(store: BaseStore, user_id: str, key: str, value: dict) -> None:
    """Store/overwrite a single episodic memory — a past-trip outcome.

    Key-addressed (overwrite, not append); the natural key is ``trip_id`` so
    re-extracting a trip is idempotent.
    """
    store.put(_namespace(user_id, "episodes"), key, _stamped(value))


def search_episodes(
    store: BaseStore, user_id: str, *, query: str | None = None, limit: int = 3
) -> list[dict]:
    """Return episodic-memory values for a user (semantic when a query is given)."""
    results = store.search(_namespace(user_id, "episodes"), query=query, limit=limit)
    return [item.value for item in results]


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
    def from_item(cls, item) -> Preference:
        return cls(key=item.key, text=item.value.get("text", ""))


@dataclass
class Instruction:
    """A typed standing instruction (procedural memory)."""

    key: str
    text: str

    @classmethod
    def from_item(cls, item) -> Instruction:
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
    def from_item(cls, item) -> Episode:
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

    Returns matching values as dicts (semantic ranking when *query* is given).
    When *limit* is ``None`` the per-kind default is used.
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
    (selected by *kind*) instead of raw dicts.
    """
    kind = MemoryKind(kind)
    ns = _namespace(user_id, kind.value)
    eff_limit = limit if limit is not None else _DEFAULT_SEARCH_LIMITS[kind]
    result_type = _MEMORY_RESULT_TYPES[kind]
    return [
        result_type.from_item(item)
        for item in store.search(ns, query=query, limit=eff_limit)
    ]
