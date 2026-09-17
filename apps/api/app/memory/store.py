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


_PAGE_SIZE = 100
_SEMANTIC_TOP_K = 10


def _read_all(
    store: BaseStore,
    namespace: tuple[str, ...],
) -> list:
    """Return every item in *namespace*; ``store.search`` has no unlimited mode, so page."""
    items: dict = {}
    offset = 0
    while True:
        page = store.search(namespace, limit=_PAGE_SIZE, offset=offset)
        fresh = [item for item in page if (item.namespace, item.key) not in items]
        items.update(((item.namespace, item.key), item) for item in fresh)
        # Also stop on a page with nothing new, so a store that mishandles offset cannot spin.
        if len(page) < _PAGE_SIZE or not fresh:
            return list(items.values())
        offset += len(page)


def _search_unbounded(
    store: BaseStore,
    namespace: tuple[str, ...],
    query: str | None,
) -> list:
    """Every row when unqueried; a semantic *query* is a top-k search, so it is never paged."""
    if query is not None:
        return store.search(namespace, query=query, limit=_SEMANTIC_TOP_K)
    return _read_all(store, namespace)


def upsert_preference(store: BaseStore, user_id: str, key: str, value: dict) -> None:
    """Store/overwrite a single user preference (value must be a JSON dict).

    :raises MemoryRejected: when the key is not allowed or the text is empty,
        over-length or blocklisted (see :func:`app.memory.guard.check`).
    """
    text = check("preferences", key, value.get("text", ""))
    store.put(_prefs_namespace(user_id), key, _stamped({**value, "text": text}))


def search_preferences(
    store: BaseStore,
    user_id: str,
    *,
    query: str | None = None,
) -> list[dict]:
    """Return every preference for a user, or the top semantic matches when a query is given."""
    results = _search_unbounded(store, _prefs_namespace(user_id), query)
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
    store: BaseStore,
    user_id: str,
    *,
    query: str | None = None,
) -> list[dict]:
    """Return every instruction for a user, or the top semantic matches when a query is given."""
    results = _search_unbounded(store, _namespace(user_id, "procedural"), query)
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


# Episodes are unbounded by key, so they alone keep a default recall limit.
_EPISODE_DEFAULT_LIMIT = 3


def _search_kind(
    store: BaseStore,
    user_id: str,
    kind: MemoryKind,
    query: str | None,
    limit: int | None,
) -> list:
    """Search one kind; with no *limit*, episodes default to 3 and the others are unbounded."""
    ns = _namespace(user_id, kind.value)
    if limit is None and kind is not MemoryKind.EPISODES:
        return _search_unbounded(store, ns, query)
    eff_limit = limit if limit is not None else _EPISODE_DEFAULT_LIMIT
    return store.search(ns, query=query, limit=eff_limit)


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
    updated_at: str | None = None

    @classmethod
    def from_item(cls, item) -> Preference:
        return cls(
            key=item.key,
            text=item.value.get("text", ""),
            updated_at=item.value.get("updated_at"),
        )


@dataclass
class Instruction:
    """A typed standing instruction (procedural memory)."""

    key: str
    text: str
    updated_at: str | None = None

    @classmethod
    def from_item(cls, item) -> Instruction:
        return cls(
            key=item.key,
            text=item.value.get("text", ""),
            updated_at=item.value.get("updated_at"),
        )


@dataclass
class Episode:
    """A typed past-trip outcome (episodic memory)."""

    key: str
    text: str
    trip_id: str | None = None
    city: str | None = None
    outcome: str = "proposed"
    updated_at: str | None = None

    @classmethod
    def from_item(cls, item) -> Episode:
        v = item.value
        return cls(
            key=item.key,
            text=v.get("text", ""),
            trip_id=v.get("trip_id"),
            city=v.get("city"),
            outcome=v.get("outcome", "proposed"),
            updated_at=v.get("updated_at"),
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
    With no *limit*: episodes return 3; preferences and instructions return every row
    (or the top semantic matches when a *query* is given).
    """
    kind = MemoryKind(kind)
    results = _search_kind(store, user_id, kind, query, limit)
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
    results = _search_kind(store, user_id, kind, query, limit)

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
        typed_values.append(
            result_type(
                key=item.key,
                text=text,
                updated_at=item.value.get("updated_at"),
            )
        )
    return typed_values


# --- Fact age + management helpers (specs/agent-memory-layer-5 Task 1.1) ------


# Age vocabularies, by prompt position. Both are month-granularity — never a day
# count, which would change daily inside a cached prompt and buy nothing.
#
# COARSE is for blocks that sit EARLY in the system prompt (standing instructions is
# position 3 of 8 in ``state.py:system_with_summary``): a change there invalidates the
# cached prefix for everything after it, including ``summary``, so the vocabulary is
# kept as stable as possible.
#
# FINE is for blocks at the END (preferences is position 8, followed only by the daily
# date note that ``ground_current_date`` appends outermost). The cached prefix already
# stops before that note, so extra churn in preferences costs essentially nothing —
# which buys real resolution inside the first year, the span this product cares about
# most ("travel preferences are seasonal and annual", design.md §6).
#
# M2: the freshest phrase is "in the last month", NOT "this month". The code computes
# ELAPSED whole months, not a calendar month, so a row stamped 20 Aug read on 16 Sep
# scores 0 months and would be labelled "this month" while in fact belonging to the
# previous one — wrong by up to nearly two calendar months. The elapsed phrasing has
# identical cache properties and makes no false claim.
#
# Each entry is (max_months_exclusive, phrase); the last entry is the fallback.
# F2: PUBLIC on purpose — `state.py` imports it to build the prompt rule, so it is
# a cross-package contract, not an internal detail. It is exported and interpolated in
# ``state.py`` rather than retyped there. Drift between those two literals IS the
# M1/D-2 defect class (the rule silently stops matching any bucket), and two tests
# asserting each side separately would not catch it.
AGE_FRESH = "in the last month"

# F1 applied to the coarse table too. It previously read "a few months ago" for the
# WHOLE 1-11 month span — the same vagueness F1 removed from the fine table, left in
# place only because the reviewer happened not to flag it. "A few months" is not what
# eleven months is, and this block's phrase is what the staleness rule is read against.
# Coarse still means coarse: three buckets, so the string changes at most twice in a
# row's lifetime, which is what protects the cached prefix ahead of `summary`.
_AGE_COARSE: tuple[tuple[int | None, str], ...] = (
    (1, AGE_FRESH),
    (12, "1-11 months ago"),
    (None, "over a year ago"),
)
# F1: every phrase names the range the arithmetic ACTUALLY supports. The first version
# of this table said "2-3 months ago" for months==1 and "about a year ago" for
# months==9 — reintroducing, one line below the fix for it, the same false-calendar
# -claim defect that M2 was raised for.
_AGE_FINE: tuple[tuple[int | None, str], ...] = (
    (1, AGE_FRESH),
    (4, "1-3 months ago"),
    (9, "4-8 months ago"),
    (16, "9-15 months ago"),
    (None, "over a year ago"),
)


def _months_elapsed(stamp: datetime, ref: datetime) -> int:
    """Whole months between *stamp* and *ref*. Negative when *stamp* is in the future.

    Day-of-month aware, so 31 Jan -> 28 Feb counts as 0 months rather than 1. The
    result is NOT clamped: :func:`format_age` needs to tell "freshly written" apart
    from "impossible" (see M3 there).

    :param stamp: The stored timestamp (timezone-aware).
    :param ref: The reference "now" (timezone-aware).
    :return: Whole months elapsed; negative for a future stamp.
    """
    months = (ref.year - stamp.year) * 12 + (ref.month - stamp.month)
    if ref.day < stamp.day:
        months -= 1
    return months


def format_age(
    updated_at: str | None, *, now: datetime | None = None, fine: bool = False
) -> str | None:
    """Render a stored ``updated_at`` as a month-granularity age phrase.

    Code computes the delta so the model only reads the result
    (``docs/solutions/agent/llm-parses-code-computes.md``). The phrase is **never a day
    count**: a string that changed daily would churn a cached system prompt for every
    user at each rollover, and buys nothing the model needs
    (``docs/solutions/agent/prompt-caching-implicit-idle-eviction.md``).

    Two vocabularies, chosen by the caller's position in the prompt — see
    :data:`_AGE_COARSE` and :data:`_AGE_FINE` for why position decides this.

    :param updated_at: An ISO-8601 timestamp string, or ``None``. A timezone-naive stamp
        is treated as UTC.
    :param now: Reference "now" (defaults to the current UTC time); injectable so tests
        are deterministic.
    :param fine: Use the finer vocabulary (for late-in-prompt blocks such as
        preferences). Defaults to the coarse vocabulary.
    :return: The age phrase, or ``None`` when *updated_at* is ``None``, empty, or
        unparseable. Never guesses, never substitutes *now*, never raises.
    """
    if not updated_at or not isinstance(updated_at, str):
        return None
    try:
        stamp = datetime.fromisoformat(updated_at)
    except (ValueError, TypeError):
        return None

    ref = now or datetime.now(timezone.utc)
    # Normalize both sides to aware UTC so the subtraction never mixes naive/aware.
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)

    months = _months_elapsed(stamp, ref)
    # M3: a stamp in the future cannot be an age. Clock skew, a bad backfill or a
    # hand-edited row would otherwise be shown to the model as maximally FRESH — the
    # most confidence-inspiring label available, on the least trustworthy data. Treat
    # it the way the plan's "absent data renders as absent" constraint treats a missing
    # stamp: return None, and the line renders with no marker at all.
    if months < 0:
        return None
    for max_months, phrase in _AGE_FINE if fine else _AGE_COARSE:
        if max_months is None or months < max_months:
            return phrase
    return None  # unreachable: both vocabularies end with a None fallback


def list_memory(
    store: BaseStore, user_id: str, kind: MemoryKind | str, *, limit: int = 50
) -> list[dict]:
    """Unfiltered listing of a user's memory rows for one *kind*, key preserved.

    Unlike :func:`search_memory` (which drops the store key), each returned row carries
    ``key`` — the delete handle a management surface needs — alongside the stored
    ``text`` and ``updated_at``. No query is applied; rows are the store's natural order.

    :param store: Long-term store to read from.
    :param user_id: Owning user's id.
    :param kind: Which memory namespace to list; validated through :class:`MemoryKind`.
    :param limit: Maximum number of rows to return.
    :return: Rows as dicts, each including its store ``key``.
    """
    kind = MemoryKind(kind)
    ns = _namespace(user_id, kind.value)
    # Spread the value FIRST so the authoritative store key always wins: this key is
    # the delete handle, and a stored value that happened to carry its own "key" field
    # must not be able to shadow it.
    return [
        {**item.value, "key": item.key}
        for item in store.search(ns, query=None, limit=limit)
    ]


def delete_memory(
    store: BaseStore, user_id: str, kind: MemoryKind | str, key: str
) -> bool:
    """Hard-delete a single memory row by ``(kind, key)``. Idempotent.

    Coerces *kind* through :class:`MemoryKind` **before** building the namespace, so an
    unknown kind raises rather than being interpolated into a namespace tuple. On an
    indexed ``PostgresStore`` the underlying ``store.delete`` also removes the pgvector
    embedding row via ``store_vectors``' ``ON DELETE CASCADE``. Deleting a missing key
    is not an error.

    :param store: Long-term store to delete from.
    :param user_id: Owning user's id.
    :param kind: Which memory namespace the key lives in; validated through
        :class:`MemoryKind`.
    :param key: The row key to delete.
    :return: ``True`` once the delete has been issued (idempotent — missing key included).
    """
    kind = MemoryKind(kind)
    ns = _namespace(user_id, kind.value)
    store.delete(ns, key)
    return True
