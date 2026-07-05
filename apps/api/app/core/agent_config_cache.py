"""In-process cache of per-agent LLM config overrides, loaded from the DB.

Core-level singleton: no ``app.agents`` / ``app.clients`` imports, so
``get_agent_llm`` (in ``app.clients.llm``) can import this without a cycle.

Loaded once at startup, then **refreshed lazily on read once past the TTL**
(MIN-47): the first reader after the TTL elapses triggers a single bulk reload
from the DB, so config edits (via ``scripts/seed_agent_config.py`` or the
future MIN-48 UI) take effect within ~1h without a restart, while normal reads
stay in-memory. A ``generation`` counter is bumped whenever a reload actually
changes the data, so callers that memoise built models (the agent graph) can
detect the change and rebuild.
"""

import time
from dataclasses import dataclass

# Fallback TTL (seconds) until ``configure`` wires the settings-driven value.
_DEFAULT_TTL_SECONDS = 3600.0


@dataclass(frozen=True)
class AgentModelOverride:
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    enabled: bool | None = None  # None = enabled (coalesced on the read side)


class AgentConfigCache:
    """Process-wide, TTL-refreshed cache of ``agent_name -> AgentModelOverride``."""

    _cache: dict[str, AgentModelOverride] = {}
    _generation: int = 0
    _loaded_at: float | None = None
    _ttl_seconds: float = _DEFAULT_TTL_SECONDS
    _session_factory = None

    @classmethod
    def configure(cls, session_factory, ttl_seconds: float) -> None:
        """Wire the DB loader + TTL used for lazy refresh (called at startup).

        :param session_factory: Callable returning a session (context manager).
        :param ttl_seconds: Max cache age before the next read reloads from DB.
        """
        cls._session_factory = session_factory
        cls._ttl_seconds = ttl_seconds

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
        """Reload from the DB when the cache is older than the TTL."""
        if cls._session_factory is None:
            return  # no loader wired (tests drive the cache via sync_from_cache)
        if (
            cls._loaded_at is not None
            and time.monotonic() - cls._loaded_at < cls._ttl_seconds
        ):
            return
        # Stamp first so a slow reload doesn't let concurrent readers stampede.
        cls._loaded_at = time.monotonic()
        reload_from_db(cls._session_factory)

    @classmethod
    def clear(cls) -> None:
        """Reset the cache and all refresh state (tests)."""
        cls._cache = {}
        cls._generation = 0
        cls._loaded_at = None
        cls._session_factory = None
        cls._ttl_seconds = _DEFAULT_TTL_SECONDS


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
