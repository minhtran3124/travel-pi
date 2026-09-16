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

logger = logging.getLogger(__name__)


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
    """
    store.put(_prefs_namespace(user_id), key, _stamped(value))


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
    return [item.value for item in results]


# Reserved preference keys for MIN-53 personalization. These three ride the
# existing prefs namespace (no schema) and are auto-injected each turn.
PROFILE_KEYS: tuple[str, ...] = ("name", "gender", "travel_group")


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
        if item is not None:
            raw = item.value.get("text")
            text = raw.strip() if isinstance(raw, str) else ""
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
    """
    store.put(_namespace(user_id, "procedural"), key, _stamped(value))


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
    return [item.value for item in results]


def upsert_episode(store: BaseStore, user_id: str, key: str, value: dict) -> None:
    """Store/overwrite a single episodic memory — a past-trip outcome (value is a
    JSON dict whose ``text`` field is embedded by the semantic index; ``trip_id`` /
    ``city`` / ``outcome`` are stored metadata). Key-addressed (overwrite, not
    append); the natural key is ``trip_id`` so re-extracting a trip is idempotent.

    :param store: Long-term store to write to.
    :param user_id: Owning user's id.
    :param key: Episode key within the user's episodes namespace (the trip id).
    :param value: JSON-serializable episode payload.
    """
    store.put(_namespace(user_id, "episodes"), key, _stamped(value))


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
    result_type = _MEMORY_RESULT_TYPES[kind]
    return [
        result_type.from_item(item)
        for item in store.search(ns, query=query, limit=eff_limit)
    ]


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
# F2: the fresh phrase is exported and interpolated into the prompt rule in
# ``state.py`` rather than retyped there. Drift between those two literals IS the
# M1/D-2 defect class (the rule silently stops matching any bucket), and two tests
# asserting each side separately would not catch it.
_AGE_FRESH = "in the last month"

_AGE_COARSE: tuple[tuple[int | None, str], ...] = (
    (1, _AGE_FRESH),
    (12, "a few months ago"),
    (None, "over a year ago"),
)
# F1: every phrase names the range the arithmetic ACTUALLY supports. The first
# version of this table said "2-3 months ago" for months==1 and "about a year ago"
# for months==9 — reintroducing, one line below the fix for it, the same false-calendar
# -claim defect that M2 was raised for.
_AGE_FINE: tuple[tuple[int | None, str], ...] = (
    (1, _AGE_FRESH),
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
