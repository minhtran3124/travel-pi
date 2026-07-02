#!/usr/bin/env python3
"""Seed per-agent LLM config rows for every graph node (MIN-43).

Populates the ``agent_config`` table so the **DB** — not the ``LLM_PROVIDER`` /
``LLM_MODEL`` env globals — drives each node's provider + model. By default all
nine nodes (``app.data.agent_config.AGENT_CONFIG_NODES``) are set to the
``clinepass`` gateway profile on ``openai/gpt-5.4-nano``; pass ``--provider`` /
``--model`` to change that, or ``--nodes`` to target a subset.

The startup seeder (``app/db/seed.py``) deliberately leaves these columns NULL
so a fresh DB inherits the env globals; this script is the operational way to
flip a deployment over to DB-driven config.

Run as a module from ``apps/api/`` so ``app`` is importable::

    python -m scripts.seed_agent_config
    python -m scripts.seed_agent_config --provider claude --model claude-sonnet-5
    python -m scripts.seed_agent_config --nodes concierge planner

Runs against ``settings.database_url`` (respects ``DATABASE_URL`` / ``.env``).
Idempotent: re-running upserts the same rows. ``provider`` is validated against
the profile catalog (``app.core.llm_providers.PROVIDER_NAMES``); ``model`` is
not (the catalog is a reference list, not an allowlist). Restart the app — or
have MIN-48 call ``reload_from_db`` — so the in-process ``AgentConfigCache``
picks up the change.
"""

from __future__ import annotations

import argparse

from app.core.config import get_settings
from app.data.agent_config import AGENT_CONFIG_NODES
from app.db.engine import get_session_factory
from app.repositories.agent_config import AgentConfigRepository

# Requested defaults: every node on the Cline gateway + its nano model.
DEFAULT_PROVIDER = "clinepass"
DEFAULT_MODEL = "openai/gpt-5.4-nano"


def seed_agent_config(
    provider: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    nodes: list[str] | None = None,
) -> list[tuple[str, str | None, str | None]]:
    """Upsert an ``agent_config`` row per node.

    :param provider: The provider profile to store for every targeted node.
    :param model: The model name to store for every targeted node.
    :param nodes: Node names to seed; defaults to all ``AGENT_CONFIG_NODES``.
    :return: A ``(agent_name, provider, model)`` tuple per upserted row.
    :raises DomainValidationError: If *provider* is not a known profile.
    """
    targets = nodes or list(AGENT_CONFIG_NODES)
    factory = get_session_factory(get_settings().database_url)
    repo = AgentConfigRepository(factory)
    rows = []
    for name in targets:
        row = repo.upsert(name, provider=provider, model=model)
        rows.append((row.agent_name, row.provider, row.model))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed per-agent LLM provider/model into agent_config."
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
        "--nodes",
        nargs="*",
        default=None,
        metavar="NODE",
        help="Subset of node names to seed; default is all nine.",
    )
    args = parser.parse_args()

    rows = seed_agent_config(args.provider, args.model, args.nodes)
    for name, provider, model in rows:
        print(f"{name:16} -> provider={provider} model={model}")
    print(f"seeded {len(rows)} agent_config rows")


if __name__ == "__main__":
    main()
