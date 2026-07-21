"""In-process cache of per-agent LLM config overrides, loaded from the DB.

Core-level singleton: no ``app.agents`` / ``app.clients`` imports, so
``get_agent_llm`` (in ``app.clients.llm``) can import this without a cycle.

Loaded once at startup, then **refreshed lazily on read once past the poll
interval** (MIN-47, GH-106): the first reader after the interval elapses does
a cheap ``max_updated_at()`` check, and only pays for a full bulk reload from
the DB if that value actually changed. Config edits (via
``scripts/seed_agent_config.py``, the MIN-48 dashboard UI, or another OS
process) take effect within a few seconds without a restart, while normal
reads stay in-memory. A ``generation`` counter is bumped whenever a reload
actually changes the data, so callers that memoise built models (the agent
graph) can detect the change and rebuild.
"""

import logging
import threading
import time
from dataclasses import dataclass
from typing import ClassVar

logger = logging.getLogger(__name__)

# Fallback poll interval (seconds) until ``configure`` wires the settings-driven value.
_DEFAULT_POLL_INTERVAL_SECONDS = 5.0


@dataclass(frozen=True)
class AgentModelOverride:
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    enabled: bool | None = None  # None = enabled (coalesced on the read side)


class AgentConfigCache:
    """Process-wide, poll-refreshed cache of ``agent_name -> AgentModelOverride``."""

    _cache: dict[str, AgentModelOverride] = {}
    _generation: int = 0
    _loaded_at: float | None = None
    _known_updated_at: str | None = None
    _poll_interval_seconds: float = _DEFAULT_POLL_INTERVAL_SECONDS
    _session_factory = None
    # FastAPI's GraphDep (app/routers/agent.py) is a sync dependency, so
    # FastAPI runs it via run_in_threadpool on a real OS thread per request —
    # concurrent _maybe_refresh() calls across threads are the normal case
    # under load, not an edge case. This lock serializes only the
    # actual-refresh path (poll -> conditional reload -> known-version
    # update) inside _maybe_refresh; the interval-check early-return stays
    # lock-free so the hot path ("not due yet") costs nothing. Permanent
    # class attribute — clear() does not need to reset it.
    _refresh_lock: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    def configure(cls, session_factory, poll_interval_seconds: float) -> None:
        """Wire the DB loader + poll interval used for lazy refresh (called at startup).

        :param session_factory: Callable returning a session (context manager).
        :param poll_interval_seconds: Max cache age before the next read polls the DB.
        """
        cls._session_factory = session_factory
        cls._poll_interval_seconds = poll_interval_seconds

    @classmethod
    def sync_from_cache(cls, cache: dict[str, AgentModelOverride]) -> None:
        """Replace the cached map wholesale; bump ``generation`` if it changed.

        :param cache: The new ``agent_name -> AgentModelOverride`` map.
        """
        new = dict(cache)
        if new != cls._cache:
            cls._cache = new
            cls._generation += 1
        cls._loaded_at = time.monotonic()

    @classmethod
    def get(cls, agent_name: str) -> AgentModelOverride | None:
        """Return the override for *agent_name*, reloading first if stale.

        :param agent_name: The agent name to look up.
        :return: The cached override, or ``None``.
        """
        cls._maybe_refresh()
        return cls._cache.get(agent_name)

    @classmethod
    def generation(cls) -> int:
        """Return the current config generation, reloading first if stale.

        The counter changes only when a reload alters the data, so a caller can
        cheaply detect "config changed since I last looked" and rebuild.

        :return: The current generation counter.
        """
        cls._maybe_refresh()
        return cls._generation

    @classmethod
    def invalidate(cls) -> None:
        """Force the next read to reload from the DB (called after a config write).

        Resets only the freshness stamp; the cached map stays in place until the
        next ``_maybe_refresh`` actually reloads. A no-op when no loader is wired.
        """
        cls._loaded_at = None

    @classmethod
    def _maybe_refresh(cls) -> None:
        """Poll the DB for a change past the interval; reload only if something changed.

        Fails open on any DB error: keeps serving the last-known-good cache and
        retries on the next interval, rather than raising into the request path
        (GH-106 — polling runs far more often than the old 1h TTL, so a
        transient DB hiccup must not break every in-flight request).
        """
        if cls._session_factory is None:
            return  # no loader wired (tests drive the cache via sync_from_cache)
        if (
            cls._loaded_at is not None
            and time.monotonic() - cls._loaded_at < cls._poll_interval_seconds
        ):
            return
        # Stamp first so a slow poll doesn't let concurrent readers stampede.
        cls._loaded_at = time.monotonic()
        # Serialize the actual refresh: GraphDep runs this on a threadpool
        # worker per request, so racing threads could otherwise interleave a
        # slower thread's stale reload over a faster thread's fresher one.
        with cls._refresh_lock:
            try:
                latest = max_updated_at(cls._session_factory)
            except Exception as exc:  # noqa: BLE001 - fail open on any DB error
                logger.error(
                    f"[AgentConfigCache] poll failed, serving stale cache: {exc}"
                )
                return
            if latest == cls._known_updated_at:
                return
            try:
                reload_from_db(cls._session_factory)
            except Exception as exc:  # noqa: BLE001 - fail open on any DB error
                logger.error(
                    f"[AgentConfigCache] reload failed, serving stale cache: {exc}"
                )
                return
            cls._known_updated_at = latest

    @classmethod
    def clear(cls) -> None:
        """Reset the cache and all refresh state (tests)."""
        cls._cache = {}
        cls._generation = 0
        cls._loaded_at = None
        cls._known_updated_at = None
        cls._session_factory = None
        cls._poll_interval_seconds = _DEFAULT_POLL_INTERVAL_SECONDS


def reload_from_db(session_factory) -> None:
    """Reload :class:`AgentConfigCache` from every stored ``AgentConfig`` row.

    :param session_factory: Callable returning a new session (context manager).
    """
    from app.repositories.agent_config import AgentConfigRepository

    repo = AgentConfigRepository(session_factory)
    cache = {
        row.agent_name: AgentModelOverride(
            provider=row.provider,
            model=row.model,
            base_url=row.base_url,
            temperature=row.temperature,
            max_tokens=row.max_tokens,
            enabled=row.enabled,
        )
        for row in repo.list_all()
    }
    AgentConfigCache.sync_from_cache(cache)


def max_updated_at(session_factory) -> str | None:
    """Return the most recent ``updated_at`` across every ``agent_config`` row.

    Cheap freshness probe used by ``_maybe_refresh`` before paying for a full
    ``reload_from_db``. ``None`` when the table is empty.

    :param session_factory: Callable returning a new session (context manager).
    :return: The lexicographically greatest ISO-8601 ``updated_at``, or ``None``.
    """
    from app.repositories.agent_config import AgentConfigRepository

    return AgentConfigRepository(session_factory).max_updated_at()
