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
from app.memory.guard import (
    PROFILE_KEYS,
    MemoryKindLiteral,
    MemoryRejected,
    check,
    check_content,
    check_episode,
)

logger = logging.getLogger(__name__)


def _guarded_text(guard_kind: MemoryKindLiteral, key: str, raw: str) -> str | None:
    """Run the read guard on one row's *raw* text; return normalized text or ``None``.

    Single source of truth for the "check_content, drop-and-log on
    :class:`MemoryRejected`" loop that every non-episode read path shares
    (:func:`_guarded_values`, :func:`get_profile`, :func:`search_memory_typed`).
    A dropped row is logged naming only kind/key/reason — never the text.
    """
    try:
        return check_content(guard_kind, key, raw)
    except MemoryRejected as exc:
        logger.warning(
            "memory_filtered kind=%s key=%s reason=%s",
            guard_kind,
            key,
            exc.reason,
        )
        return None


def _guarded_values(guard_kind: MemoryKindLiteral, results) -> list[dict]:
    """Filter preference/instruction search *results* through the read guard.

    Each item's text is re-checked with :func:`_guarded_text`; a row that
    fails (blocklist / bad-shape key) is dropped with a warning naming only
    kind/key/reason — never the text. Survivors carry the guard's **normalized**
    text (``<``/``>`` stripped, over-length truncated), so a row poisoned before
    this guard existed is neutralized on read without a migration.
    """
    out: list[dict] = []
    for item in results:
        text = _guarded_text(guard_kind, item.key, item.value.get("text", ""))
        if text is None:
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
    """Store/overwrite a single user preference (value must be a JSON dict).

    :raises MemoryRejected: when the key is not allowed or the text is empty,
        over-length or blocklisted (see :func:`app.memory.guard.check`).
    """
    text = check("preferences", key, value.get("text", ""))
    store.put(_prefs_namespace(user_id), key, _stamped({**value, "text": text}))


def search_preferences(
    store: BaseStore, user_id: str, *, query: str | None = None, limit: int = 5
) -> list[dict]:
    """Return preference values for a user (semantic when a query is given)."""
    results = store.search(_prefs_namespace(user_id), query=query, limit=limit)
    return _guarded_values("preferences", results)


# ``PROFILE_KEYS`` (the reserved MIN-53 personalization keys) is defined once in
# ``app.memory.guard`` and imported at the top of this module, so the guard and
# the store share one source of truth. It is re-exported here (``store.PROFILE_KEYS``)
# because ``app.agents.nodes`` imports it from ``store``; the import direction is
# store → guard only.


def get_profile(store: BaseStore, user_id: str) -> dict[str, str]:
    """Return ``{key: text}`` for each :data:`PROFILE_KEYS` present with non-blank text.

    Uses direct keyed ``store.get`` rather than semantic ``search_preferences`` so
    the fields are exact and never reordered/dropped by similarity ranking.
    """
    profile: dict[str, str] = {}
    for key in PROFILE_KEYS:
        item = store.get(_prefs_namespace(user_id), key)
        if item is None:
            continue
        raw = item.value.get("text")
        if not isinstance(raw, str):
            continue
        text = _guarded_text("preferences", key, raw)
        if text:
            profile[key] = text
    return profile


def upsert_instruction(store: BaseStore, user_id: str, key: str, value: dict) -> None:
    """Store/overwrite a single procedural instruction (value must be a JSON dict
    with a ``text`` field so the semantic index works).

    :raises MemoryRejected: when the key is not in the canonical instruction
        allowlist or the text is empty, over-length or blocklisted.
    """
    text = check("instructions", key, value.get("text", ""))
    store.put(_namespace(user_id, "procedural"), key, _stamped({**value, "text": text}))


def get_instructions(
    store: BaseStore, user_id: str, *, query: str | None = None, limit: int = 10
) -> list[dict]:
    """Return procedural instruction values for a user (semantic when a query is given)."""
    results = store.search(_namespace(user_id, "procedural"), query=query, limit=limit)
    return _guarded_values("instructions", results)


def upsert_episode(store: BaseStore, user_id: str, key: str, value: dict) -> None:
    """Store/overwrite a single episodic memory — a past-trip outcome.

    Key-addressed (overwrite, not append); the natural key is ``trip_id`` so
    re-extracting a trip is idempotent.

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
    """Return episodic-memory values for a user (semantic when a query is given)."""
    results = store.search(_namespace(user_id, "episodes"), query=query, limit=limit)
    return [
        payload
        for item in results
        if (payload := _guarded_episode_payload(item)) is not None
    ]


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

    Returns matching values as dicts (semantic ranking when *query* is given).
    When *limit* is ``None`` the per-kind default is used.
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
    (selected by *kind*) instead of raw dicts.
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
        text = _guarded_text(guard_kind, item.key, item.value.get("text", ""))
        if text is None:
            continue
        typed_values.append(result_type(key=item.key, text=text))
    return typed_values
