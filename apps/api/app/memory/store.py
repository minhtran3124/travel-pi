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
each stored value using the shared ``app.core.embeddings`` model (real OpenAI when keyed,
deterministic fake otherwise). On a Postgres image without pgvector the indexed
``PostgresStore`` fails to initialise and degrades to an indexed ``InMemoryStore``.
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
from app.memory.guard import (
    PROFILE_KEYS,
    MemoryKindLiteral,
    MemoryRejected,
    check,
    check_content,
    check_episode,
)

logger = logging.getLogger(__name__)


def _guarded_values(guard_kind: MemoryKindLiteral, results) -> list[dict]:
    """Filter preference/instruction search *results* through the read guard.

    Each item's text is re-checked with :func:`guard.check_content`; a row that
    fails (blocklist / bad-shape key) is dropped with a warning naming only
    kind/key/reason — never the text. Survivors carry the guard's **normalized**
    text (``<``/``>`` stripped, over-length truncated), so a row poisoned before
    this guard existed is neutralized on read without a migration.

    :param guard_kind: The guard content kind (``preferences`` / ``instructions``).
    :param results: Iterable of store search items (``.key`` / ``.value``).
    :return: The surviving values with normalized ``text``.
    """
    out: list[dict] = []
    for item in results:
        try:
            text = check_content(guard_kind, item.key, item.value.get("text", ""))
        except MemoryRejected as exc:
            logger.warning(
                "memory_filtered kind=%s key=%s reason=%s",
                guard_kind,
                item.key,
                exc.reason,
            )
            continue
        out.append({**item.value, "text": text})
    return out


def _guarded_episode_payload(item) -> dict | None:
    """Read-guard one episode item, returning the limited payload or ``None``.

    Runs :func:`guard.check_content` on the episode ``text`` and
    :func:`guard.check_episode` on the metadata (coerce ``outcome``, normalize
    ``city``); on any :class:`MemoryRejected` the row is dropped with a
    text-free warning. The returned payload is limited to
    ``text`` / ``city`` / ``outcome`` / ``trip_id`` (§3.1) — store-internal
    fields such as ``updated_at`` are not surfaced.

    :param item: A store search/get item (``.key`` / ``.value``).
    :return: The limited episode payload, or ``None`` when dropped.
    """
    try:
        text = check_content("episodes", item.key, item.value.get("text", ""))
        cleaned = check_episode(item.value)
    except MemoryRejected as exc:
        logger.warning(
            "memory_filtered kind=%s key=%s reason=%s",
            "episodes",
            item.key,
            exc.reason,
        )
        return None
    payload: dict = {"text": text, "outcome": cleaned["outcome"]}
    if cleaned.get("city") is not None:
        payload["city"] = cleaned["city"]
    if cleaned.get("trip_id") is not None:
        payload["trip_id"] = cleaned["trip_id"]
    return payload


def _libpq_dsn(url: str) -> str:
    """Strip SQLAlchemy's ``+driver`` so psycopg/libpq accepts the DSN.

    :param url: SQLAlchemy-style database URL.
    :return: The URL with the ``+driver`` suffix removed.
    """
    return url.replace("postgresql+psycopg://", "postgresql://").replace(
        "postgres+psycopg://", "postgresql://"
    )


def _index_config() -> dict:
    """Semantic-search index for the store: embed the ``text`` field of each value.

    :return: Index config (dims, embedding model, indexed fields).
    """
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

    :param database_url: Database URL to connect to; defaults to
        ``settings.database_url`` when omitted.
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

    :param database_url: Unused — accepted for interface symmetry with
        :func:`open_store`.
    :return: A fresh indexed ``InMemoryStore``.
    """
    return InMemoryStore(index=_index_config())


def _namespace(user_id: str, kind: str) -> tuple[str, str, str]:
    return ("users", user_id, kind)


def _prefs_namespace(user_id: str) -> tuple[str, str, str]:
    return _namespace(user_id, "prefs")


def _stamped(value: dict) -> dict:
    """Return *value* with ``updated_at`` set to the current UTC time (D5 store
    hygiene). Does not mutate the caller's dict; index config is untouched —
    ``text`` remains the only embedded field.

    :param value: JSON-serializable payload about to be written.
    :return: A shallow copy of *value* with ``updated_at`` added/refreshed.
    """
    return {**value, "updated_at": datetime.now(timezone.utc).isoformat()}


def upsert_preference(store: BaseStore, user_id: str, key: str, value: dict) -> None:
    """Store/overwrite a single user preference (value must be a JSON dict).

    :param store: Long-term store to write to.
    :param user_id: Owning user's id.
    :param key: Preference key within the user's prefs namespace.
    :param value: JSON-serializable preference payload.
    :raises MemoryRejected: when the key is not allowed or the text is empty,
        over-length or blocklisted (see :func:`app.memory.guard.check`).
    """
    text = check("preferences", key, value.get("text", ""))
    store.put(_prefs_namespace(user_id), key, _stamped({**value, "text": text}))


def search_preferences(
    store: BaseStore, user_id: str, *, query: str | None = None, limit: int = 5
) -> list[dict]:
    """Return preference values for a user (semantic when a query is given).

    :param store: Long-term store to search.
    :param user_id: Owning user's id.
    :param query: Optional free-text query; when given, results are ranked by
        semantic similarity.
    :param limit: Maximum number of results to return.
    :return: Matching preference values.
    """
    results = store.search(_prefs_namespace(user_id), query=query, limit=limit)
    return _guarded_values("preferences", results)


# ``PROFILE_KEYS`` (the reserved MIN-53 personalization keys) is defined once in
# ``app.memory.guard`` and imported at the top of this module, so the guard and
# the store share one source of truth. It is re-exported here (``store.PROFILE_KEYS``)
# because ``app.agents.nodes`` imports it from ``store``; the import direction is
# store → guard only.


def get_profile(store: BaseStore, user_id: str) -> dict[str, str]:
    """Return the traveller's personalization profile: reserved preference keys
    (:data:`PROFILE_KEYS`) that exist with non-empty text, in reserved-key order.

    Uses direct keyed ``store.get`` rather than semantic ``search_preferences`` so
    the three fields are exact and never reordered/dropped by similarity ranking.

    :param store: Long-term store to read from.
    :param user_id: Owning user's id.
    :return: ``{key: text}`` for each reserved key present with non-blank text.
    """
    profile: dict[str, str] = {}
    for key in PROFILE_KEYS:
        item = store.get(_prefs_namespace(user_id), key)
        if item is None:
            continue
        raw = item.value.get("text")
        if not isinstance(raw, str):
            continue
        try:
            text = check_content("preferences", key, raw)
        except MemoryRejected as exc:
            logger.warning(
                "memory_filtered kind=%s key=%s reason=%s",
                "preferences",
                key,
                exc.reason,
            )
            continue
        if text:
            profile[key] = text
    return profile


def upsert_instruction(store: BaseStore, user_id: str, key: str, value: dict) -> None:
    """Store/overwrite a single procedural instruction (value must be a JSON dict
    with a ``text`` field so the semantic index works).

    :param store: Long-term store to write to.
    :param user_id: Owning user's id.
    :param key: Instruction key within the user's procedural namespace.
    :param value: JSON-serializable instruction payload.
    :raises MemoryRejected: when the key is not in the canonical instruction
        allowlist or the text is empty, over-length or blocklisted.
    """
    text = check("instructions", key, value.get("text", ""))
    store.put(_namespace(user_id, "procedural"), key, _stamped({**value, "text": text}))


def get_instructions(
    store: BaseStore, user_id: str, *, query: str | None = None, limit: int = 10
) -> list[dict]:
    """Return procedural instruction values for a user (semantic when a query is given).

    :param store: Long-term store to search.
    :param user_id: Owning user's id.
    :param query: Optional free-text query; when given, results are ranked by
        semantic similarity.
    :param limit: Maximum number of results to return.
    :return: Matching instruction values.
    """
    results = store.search(_namespace(user_id, "procedural"), query=query, limit=limit)
    return _guarded_values("instructions", results)


def upsert_episode(store: BaseStore, user_id: str, key: str, value: dict) -> None:
    """Store/overwrite a single episodic memory — a past-trip outcome (value is a
    JSON dict whose ``text`` field is embedded by the semantic index; ``trip_id`` /
    ``city`` / ``outcome`` are stored metadata). Key-addressed (overwrite, not
    append); the natural key is ``trip_id`` so re-extracting a trip is idempotent.

    :param store: Long-term store to write to.
    :param user_id: Owning user's id.
    :param key: Episode key within the user's episodes namespace (the trip id).
    :param value: JSON-serializable episode payload.
    :raises MemoryRejected: when the key breaks the slug shape rule or the text
        is empty, over-length or blocklisted (``city`` is normalized too).
    """
    text = check("episodes", key, value.get("text", ""))
    cleaned = check_episode(value)
    cleaned["text"] = text
    store.put(_namespace(user_id, "episodes"), key, _stamped(cleaned))


def search_episodes(
    store: BaseStore, user_id: str, *, query: str | None = None, limit: int = 3
) -> list[dict]:
    """Return episodic-memory values for a user (semantic when a query is given).

    :param store: Long-term store to search.
    :param user_id: Owning user's id.
    :param query: Optional free-text query; when given, results are ranked by
        semantic similarity.
    :param limit: Maximum number of results to return.
    :return: Matching episode values.
    """
    results = store.search(_namespace(user_id, "episodes"), query=query, limit=limit)
    return [
        payload
        for item in results
        if (payload := _guarded_episode_payload(item)) is not None
    ]


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

# Store namespace kind -> guard content kind (the guard's vocabulary differs from
# the namespace strings: prefs -> preferences, procedural -> instructions).
_GUARD_KIND: dict[MemoryKind, MemoryKindLiteral] = {
    MemoryKind.PREFERENCES: "preferences",
    MemoryKind.PROCEDURAL: "instructions",
    MemoryKind.EPISODES: "episodes",
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

    Validates *kind* against :class:`MemoryKind`, resolves the
    ``("users", user_id, kind)`` namespace, and returns the matching values as
    dicts (semantic ranking when *query* is given). When *limit* is ``None`` the
    per-kind default is used (prefs=5, procedural=10, episodes=3).

    :param store: Long-term store to search.
    :param user_id: Owning user's id.
    :param kind: Which memory namespace to search.
    :param query: Optional free-text query; when given, results are ranked by
        semantic similarity.
    :param limit: Maximum number of results; defaults to the per-kind limit when
        ``None``.
    :return: Matching memory values as dicts.
    """
    kind = MemoryKind(kind)
    ns = _namespace(user_id, kind.value)
    eff_limit = limit if limit is not None else _DEFAULT_SEARCH_LIMITS[kind]
    results = store.search(ns, query=query, limit=eff_limit)
    if kind is MemoryKind.EPISODES:
        return [
            payload
            for item in results
            if (payload := _guarded_episode_payload(item)) is not None
        ]
    return _guarded_values(_GUARD_KIND[kind], results)


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

    :param store: Long-term store to search.
    :param user_id: Owning user's id.
    :param kind: Which memory namespace to search.
    :param query: Optional free-text query; when given, results are ranked by
        semantic similarity.
    :param limit: Maximum number of results; defaults to the per-kind limit when
        ``None``.
    :return: Matching memory values as typed dataclass instances.
    """
    kind = MemoryKind(kind)
    ns = _namespace(user_id, kind.value)
    eff_limit = limit if limit is not None else _DEFAULT_SEARCH_LIMITS[kind]
    results = store.search(ns, query=query, limit=eff_limit)

    if kind is MemoryKind.EPISODES:
        typed: list[Preference | Instruction | Episode] = []
        for item in results:
            payload = _guarded_episode_payload(item)
            if payload is None:
                continue
            typed.append(
                Episode(
                    key=item.key,
                    text=payload["text"],
                    trip_id=payload.get("trip_id"),
                    city=payload.get("city"),
                    outcome=payload["outcome"],
                )
            )
        return typed

    guard_kind = _GUARD_KIND[kind]
    result_type = _MEMORY_RESULT_TYPES[kind]
    typed_values: list[Preference | Instruction | Episode] = []
    for item in results:
        try:
            text = check_content(guard_kind, item.key, item.value.get("text", ""))
        except MemoryRejected as exc:
            logger.warning(
                "memory_filtered kind=%s key=%s reason=%s",
                guard_kind,
                item.key,
                exc.reason,
            )
            continue
        typed_values.append(result_type(key=item.key, text=text))
    return typed_values
