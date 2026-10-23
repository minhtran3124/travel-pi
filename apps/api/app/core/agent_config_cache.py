"""In-process cache of per-agent LLM config overrides: loaded once at startup, then refreshed lazily on read past the poll interval (a cheap ``max_updated_at()`` check gates a full reload). A ``generation`` counter bumps when a reload changes the data so callers can rebuild."""

import logging
import threading
import time
from dataclasses import dataclass
from typing import ClassVar

from sqlalchemy.exc import SQLAlchemyError

from app.core.pricing import is_priced, normalize_model

logger = logging.getLogger(__name__)

# (agent, normalized model) pairs already warned about, so a reload can't flood the logs.
_WARNED_UNPRICED: set[tuple[str, str]] = set()

# Fallback poll interval (seconds) until ``configure`` wires the settings-driven value.
_DEFAULT_POLL_INTERVAL_SECONDS = 5.0


@dataclass(frozen=True)
class AgentModelOverride:
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    effort: str | None = None
    enabled: bool | None = None  # None = enabled (coalesced on the read side)


class AgentConfigCache:
    """Process-wide, poll-refreshed cache of ``agent_name -> AgentModelOverride``."""

    _cache: dict[str, AgentModelOverride] = {}
    _generation: int = 0
    _loaded_at: float | None = None
    _known_updated_at: str | None = None
    _poll_interval_seconds: float = _DEFAULT_POLL_INTERVAL_SECONDS
    _session_factory = None
    # Set by invalidate(), cleared once _maybe_refresh() reaches the DB; forces
    # the next poll even if _loaded_at still looks fresh.
    _dirty: bool = False
    # Serializes only the actual-refresh path; the interval-check early-return
    # stays lock-free. Permanent class attribute (clear() need not reset it).
    _refresh_lock: ClassVar[threading.Lock] = threading.Lock()
    # Guards only `_dirty`; kept separate from _refresh_lock so invalidate()
    # never blocks on the DB round-trip that lock serializes.
    _dirty_lock: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    def configure(cls, session_factory, poll_interval_seconds: float) -> None:
        """Wire the DB loader and poll interval used for lazy refresh (called at startup)."""
        cls._session_factory = session_factory
        cls._poll_interval_seconds = poll_interval_seconds

    @classmethod
    def sync_from_cache(cls, cache: dict[str, AgentModelOverride]) -> None:
        """Replace the cached map wholesale; bump ``generation`` if it changed."""
        new = dict(cache)
        if new != cls._cache:
            cls._cache = new
            cls._generation += 1
        cls._loaded_at = time.monotonic()

    @classmethod
    def get(cls, agent_name: str) -> AgentModelOverride | None:
        """Return the override for *agent_name*, reloading first if stale."""
        cls._maybe_refresh()
        return cls._cache.get(agent_name)

    @classmethod
    def generation(cls) -> int:
        """Return the current config generation, reloading first if stale (the counter changes only when a reload alters the data)."""
        cls._maybe_refresh()
        return cls._generation

    @classmethod
    def invalidate(cls) -> None:
        """Force the next read to reload from the DB via a durable dirty flag that an in-flight reload can't clobber (unlike nulling ``_loaded_at``)."""
        with cls._dirty_lock:
            cls._dirty = True

    @classmethod
    def _maybe_refresh(cls) -> None:
        """Poll the DB past the interval and reload only on change; fails open to the last-known-good cache on any DB error rather than raising into the request path."""
        if cls._session_factory is None:
            return  # no loader wired (tests drive the cache via sync_from_cache)
        if (
            not cls._dirty
            and cls._loaded_at is not None
            and time.monotonic() - cls._loaded_at < cls._poll_interval_seconds
        ):
            return
        # Stamp first so a slow poll doesn't let concurrent readers stampede.
        cls._loaded_at = time.monotonic()
        # Serialize the actual refresh so a slower thread can't interleave a stale reload over a fresher one.
        with cls._refresh_lock:
            with cls._dirty_lock:
                was_dirty = cls._dirty
                cls._dirty = False
            try:
                latest = max_updated_at(cls._session_factory)
            except SQLAlchemyError as exc:
                logger.error(
                    f"[AgentConfigCache] poll failed, serving stale cache: {exc}"
                )
                if was_dirty:
                    with cls._dirty_lock:
                        cls._dirty = True
                return
            if latest == cls._known_updated_at and not was_dirty:
                return
            try:
                reload_from_db(cls._session_factory)
            except SQLAlchemyError as exc:
                logger.error(
                    f"[AgentConfigCache] reload failed, serving stale cache: {exc}"
                )
                if was_dirty:
                    with cls._dirty_lock:
                        cls._dirty = True
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
        cls._dirty = False


def reload_from_db(session_factory) -> None:
    """Reload :class:`AgentConfigCache` from every stored ``AgentConfig`` row."""
    from app.repositories.agent_config import AgentConfigRepository

    repo = AgentConfigRepository(session_factory)
    cache = {
        row.agent_name: AgentModelOverride(
            provider=row.provider,
            model=row.model,
            base_url=row.base_url,
            temperature=row.temperature,
            max_tokens=row.max_tokens,
            effort=row.effort,
            enabled=row.enabled,
        )
        for row in repo.list_all()
    }
    _warn_unpriced_models(cache)
    AgentConfigCache.sync_from_cache(cache)


def _warn_unpriced_models(cache: dict[str, AgentModelOverride]) -> None:
    """Log a WARNING for each agent pinned to an unpriced model, and for an unpriced env default model that un-pinned agents fall back to (once per agent and model, never raising)."""
    try:
        from app.core.config import get_settings

        s = get_settings()
        pinned = [(name, o.model) for name, o in cache.items() if o.model]
        defaults = [
            ("<default llm_model>", s.effective_llm_model),
            ("<default fast_llm_model>", s.effective_fast_llm_model),
        ]
        for name, model in pinned + defaults:
            if not model or is_priced(model):
                continue
            key = (name, normalize_model(model))
            if key in _WARNED_UNPRICED:
                continue
            _WARNED_UNPRICED.add(key)
            logger.warning(
                "[AgentConfigCache] agent %r uses unpriced model %r — its cost will be NULL",
                name,
                model,
            )
    except Exception as exc:  # the cost warning must never break a reload
        logger.error(f"[AgentConfigCache] unpriced-model check failed: {exc}")


def max_updated_at(session_factory) -> str | None:
    """Return the most recent ``updated_at`` across all rows — a cheap freshness probe before a full reload; ``None`` when the table is empty."""
    from app.repositories.agent_config import AgentConfigRepository

    return AgentConfigRepository(session_factory).max_updated_at()
