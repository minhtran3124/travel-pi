"""``--provider {openai,anthropic}`` for the keyed entrypoints: which provider the agent UNDER TEST runs on.

The judge is untouched — it builds its own OpenAI ``GPTModel`` (``evalkit/metrics/judged.py``) and never reads ``LLM_PROVIDER``.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import replace

PROVIDER_CHOICES = ("openai", "anthropic")
_FLAG = "--provider"


def extract_provider(argv: Sequence[str]) -> tuple[str | None, list[str]]:
    """Pull ``--provider X`` / ``--provider=X`` out of *argv*; returns ``(provider, remaining argv)``.

    Done before ``evalkit.cli`` parses argv, which stays framework-free and knows nothing about providers.
    """
    provider: str | None = None
    rest: list[str] = []
    it = iter(argv)
    for arg in it:
        if arg == _FLAG:
            provider = next(it, "")
        elif arg.startswith(f"{_FLAG}="):
            provider = arg.split("=", 1)[1]
        else:
            rest.append(arg)
    if provider is None:
        # `LLM_PROVIDER=anthropic make eval-smoke`: honour a non-default provider from the environment too.
        env = os.environ.get("LLM_PROVIDER", "")
        provider = env if env in PROVIDER_CHOICES and env != "openai" else None
    if provider is not None and provider not in PROVIDER_CHOICES:
        raise SystemExit(
            f"error: {_FLAG} must be one of {', '.join(PROVIDER_CHOICES)} (got {provider!r})"
        )
    return provider, rest


def apply_provider(provider: str) -> None:
    """Point the global ``LLM_PROVIDER`` at *provider* and drop the cached settings."""
    from app.core.config import get_settings

    os.environ["LLM_PROVIDER"] = provider
    get_settings.cache_clear()


def pin_agent_config_to_provider(provider: str) -> None:
    """Re-point every DB per-agent override at *provider* and stop polling the DB.

    Seeded ``agent_config`` rows pin ``provider``/``model`` explicitly, so changing ``LLM_PROVIDER`` alone
    would leave every agent on its stored OpenAI model. Model, base URL, temperature and max_tokens are
    cleared so the provider's own defaults apply; ``enabled`` is kept.
    """
    from app.core.agent_config_cache import AgentConfigCache

    AgentConfigCache.sync_from_cache(
        {
            name: replace(
                o,
                provider=provider,
                model=None,
                base_url=None,
                temperature=None,
                max_tokens=None,
            )
            for name, o in AgentConfigCache._cache.items()  # noqa: SLF001 - eval harness owns this process
        }
    )
    AgentConfigCache._session_factory = None  # noqa: SLF001 - no lazy reload over the pinned map
