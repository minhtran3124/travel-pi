"""In-process cache of per-agent LLM config overrides, loaded from the DB.

Core-level singleton: no ``app.agents`` / ``app.clients`` imports, so
``get_agent_llm`` (in ``app.clients.llm``) can import this without a cycle.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentModelOverride:
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None


class AgentConfigCache:
    """Process-wide cache of ``agent_name -> AgentModelOverride``."""

    _cache: dict[str, AgentModelOverride] = {}

    @classmethod
    def sync_from_cache(cls, cache: dict[str, AgentModelOverride]) -> None:
        """Replace the cached map wholesale.

        :param cache: The new ``agent_name -> AgentModelOverride`` map.
        """
        cls._cache = dict(cache)

    @classmethod
    def get(cls, agent_name: str) -> AgentModelOverride | None:
        """Return the override for *agent_name*, or ``None`` if uncached.

        :param agent_name: The agent name to look up.
        :return: The cached override, or ``None``.
        """
        return cls._cache.get(agent_name)

    @classmethod
    def clear(cls) -> None:
        """Empty the cache."""
        cls._cache = {}


def reload_from_db(session_factory) -> None:
    """Reload :class:`AgentConfigCache` from every stored ``AgentConfig`` row.

    :param session_factory: Callable returning a new session (context manager).
    """
    from app.repositories.agent_config import AgentConfigRepository

    repo = AgentConfigRepository(session_factory)
    cache = {
        row.agent_name: AgentModelOverride(
            provider=row.provider, model=row.model, base_url=row.base_url
        )
        for row in repo.list_all()
    }
    AgentConfigCache.sync_from_cache(cache)
