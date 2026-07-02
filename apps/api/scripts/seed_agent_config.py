#!/usr/bin/env python3
"""Seed per-agent LLM config rows for every graph node (MIN-43).

Populates the ``agent_config`` table so the **DB** — not env globals — drives
each node's provider, model, base_url, and model knobs (temperature,
max_tokens). By default all nine nodes
(``app.data.agent_config.AGENT_CONFIG_NODES``) are set to the ``clinepass``
gateway profile on ``openai/gpt-5.4-nano``, with ``base_url`` taken from that
profile's catalog entry (so each row is self-contained) and temperature /
max_tokens left NULL (provider defaults). Pass ``--provider`` / ``--model`` /
``--base-url`` / ``--temperature`` / ``--max-tokens`` to change that, or
``--nodes`` for a subset.

The startup seeder (``app/db/seed.py``) deliberately leaves these columns NULL
so a fresh DB inherits the global defaults; this script is the operational way
to flip a deployment over to DB-driven config.

Run as a module from ``apps/api/`` so ``app`` is importable::

    python -m scripts.seed_agent_config
    python -m scripts.seed_agent_config --provider claude --model claude-sonnet-5
    python -m scripts.seed_agent_config --temperature 0.2 --max-tokens 2048
    python -m scripts.seed_agent_config --nodes concierge planner

Runs against ``settings.database_url`` (respects ``DATABASE_URL`` / ``.env``).
Idempotent: re-running upserts the same rows. ``provider`` is validated against
the profile catalog (``app.core.llm_providers.PROVIDER_NAMES``); the other
fields are not. Restart the app — or have MIN-48 call ``reload_from_db`` — so
the in-process ``AgentConfigCache`` picks up the change.
"""

from __future__ import annotations

import argparse

from app.core.config import get_settings
from app.core.llm_providers import get_provider
from app.data.agent_config import AGENT_CONFIG_NODES
from app.db.engine import get_session_factory
from app.repositories.agent_config import AgentConfigRepository

# Requested defaults: every node on the Cline gateway + its nano model.
DEFAULT_PROVIDER = "clinepass"
DEFAULT_MODEL = "openai/gpt-5.4-nano"

# Sentinel for "derive base_url from the provider profile" (vs. an explicit
# value, including ``None`` to store NULL).
_DERIVE_FROM_PROFILE = object()


def _resolve_base_url(provider: str, base_url: object) -> str | None:
    """Pick the base_url to store: the profile's gateway by default.

    :param provider: The provider profile whose base_url to derive.
    :param base_url: An explicit value, or ``_DERIVE_FROM_PROFILE``.
    :return: The base_url to persist (``None`` stores NULL).
    """
    if base_url is _DERIVE_FROM_PROFILE:
        profile = get_provider(provider)
        return profile.base_url if profile else None
    return base_url or None  # normalise "" -> None


def seed_agent_config(
    provider: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    base_url: object = _DERIVE_FROM_PROFILE,
    temperature: float | None = None,
    max_tokens: int | None = None,
    nodes: list[str] | None = None,
) -> list[dict[str, str | float | int | None]]:
    """Upsert an ``agent_config`` row per node.

    :param provider: The provider profile to store for every targeted node.
    :param model: The model name to store for every targeted node.
    :param base_url: Explicit base_url, or ``_DERIVE_FROM_PROFILE`` (default) to
        use the provider profile's own gateway URL.
    :param temperature: Sampling temperature, or ``None`` to store NULL.
    :param max_tokens: Max output tokens, or ``None`` to store NULL.
    :param nodes: Node names to seed; defaults to all ``AGENT_CONFIG_NODES``.
    :return: One dict of the stored fields per upserted row.
    :raises DomainValidationError: If *provider* is not a known profile.
    """
    targets = nodes or list(AGENT_CONFIG_NODES)
    resolved_base_url = _resolve_base_url(provider, base_url)
    factory = get_session_factory(get_settings().database_url)
    repo = AgentConfigRepository(factory)
    rows = []
    for name in targets:
        row = repo.upsert(
            name,
            provider=provider,
            model=model,
            base_url=resolved_base_url,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        rows.append(
            {
                "agent_name": row.agent_name,
                "provider": row.provider,
                "model": row.model,
                "base_url": row.base_url,
                "temperature": row.temperature,
                "max_tokens": row.max_tokens,
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed per-agent LLM config into the agent_config table."
    )
    parser.add_argument(
        "--provider",
        default=DEFAULT_PROVIDER,
        help=f"Provider profile for every node (default: {DEFAULT_PROVIDER}).",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Model name for every node (default: {DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "--base-url",
        default=_DERIVE_FROM_PROFILE,
        metavar="URL",
        help="base_url to store; default is the provider profile's own URL. "
        "Pass an empty string to store NULL.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="Sampling temperature; default NULL (provider default).",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="Max output tokens; default NULL (provider default).",
    )
    parser.add_argument(
        "--nodes",
        nargs="*",
        default=None,
        metavar="NODE",
        help="Subset of node names to seed; default is all nine.",
    )
    args = parser.parse_args()

    rows = seed_agent_config(
        args.provider,
        args.model,
        args.base_url,
        args.temperature,
        args.max_tokens,
        args.nodes,
    )
    for r in rows:
        print(
            f"{r['agent_name']:16} -> provider={r['provider']} model={r['model']} "
            f"base_url={r['base_url']} temperature={r['temperature']} "
            f"max_tokens={r['max_tokens']}"
        )
    print(f"seeded {len(rows)} agent_config rows")


if __name__ == "__main__":
    main()
