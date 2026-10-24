#!/usr/bin/env python3
"""Seed per-agent LLM config rows so the DB, not env globals, drives each node.

The startup seeder leaves these columns NULL (fresh DBs inherit global defaults);
this is the operational way to flip a deployment over to DB-driven config. Restart
the app afterwards so the in-process ``AgentConfigCache`` picks up the change.

Run as a module from ``apps/api/`` (idempotent upsert against ``settings.database_url``)::

    python -m scripts.seed_agent_config
    python -m scripts.seed_agent_config --provider claude --model claude-sonnet-5
    python -m scripts.seed_agent_config --temperature 0.2 --max-tokens 2048
    python -m scripts.seed_agent_config --nodes concierge planner
    python -m scripts.seed_agent_config --preset anthropic-local   # tiered Claude 5.5 map
"""

from __future__ import annotations

import argparse

from app.agents.constants import FAST_MODEL_AGENTS
from app.core.config import get_settings
from app.core.llm_providers import default_model_for, get_provider
from app.data.agent_config import AGENT_CONFIG_NODES
from app.db.engine import get_session_factory
from app.repositories.agent_config import AgentConfigRepository

DEFAULT_PROVIDER = "clinepass"
DEFAULT_MODEL = "openai/gpt-5.4-nano"

# Local Anthropic tiering (``--preset anthropic-local``): Haiku 5.5 for routing/utility nodes,
# Sonnet 5.5 for the specialists and the research agent. Opus 5.5 is deliberately unused:
# research is Sonnet-first and only worth Opus (~5x cost) if Sonnet proves inadequate.
_HAIKU = "claude-haiku-5-5"
_SONNET = "claude-sonnet-5-5"
ANTHROPIC_LOCAL_PRESET: dict[str, str] = {
    "supervisor": _HAIKU,
    "summarize": _HAIKU,
    "reflection": _HAIKU,
    "extract_memory": _HAIKU,
    "date_resolution": _HAIKU,
    "trip_research_grader": _HAIKU,
    "planner": _SONNET,
    "concierge": _SONNET,
    "journal": _SONNET,
    "booking": _SONNET,
    "budget": _SONNET,
    "synthesize": _SONNET,
    "trip_research": _SONNET,
}

# Sentinel for "derive base_url from the provider profile" vs. an explicit value
# (including ``None`` to store NULL).
_DERIVE_FROM_PROFILE = object()


def _resolve_base_url(provider: str, base_url: object) -> str | None:
    """Pick the base_url to store: the profile's gateway by default."""
    if base_url is _DERIVE_FROM_PROFILE:
        profile = get_provider(provider)
        return profile.base_url if profile else None
    return base_url or None  # normalise "" -> None


def _model_for(provider: str, model: str | None, node: str) -> str | None:
    """Explicit *model* wins; else the clinepass default, else the provider's own tiered default (never another vendor's model)."""
    if model:
        return model
    if provider == DEFAULT_PROVIDER:
        return DEFAULT_MODEL
    return default_model_for(provider, fast=node in FAST_MODEL_AGENTS)


def seed_agent_config(
    provider: str = DEFAULT_PROVIDER,
    model: str | None = None,
    base_url: object = _DERIVE_FROM_PROFILE,
    temperature: float | None = None,
    max_tokens: int | None = None,
    nodes: list[str] | None = None,
) -> list[dict[str, str | float | int | None]]:
    """Upsert an ``agent_config`` row per node; defaults to all ``AGENT_CONFIG_NODES``."""
    targets = nodes or list(AGENT_CONFIG_NODES)
    resolved_base_url = _resolve_base_url(provider, base_url)
    factory = get_session_factory(get_settings().database_url)
    repo = AgentConfigRepository(factory)
    rows = []
    for name in targets:
        row = repo.upsert(
            name,
            provider=provider,
            model=_model_for(provider, model, name),
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


def seed_anthropic_local() -> list[dict[str, str | float | int | None]]:
    """Upsert every node (incl. research) onto Anthropic with ``ANTHROPIC_LOCAL_PRESET``; idempotent."""
    rows: list[dict[str, str | float | int | None]] = []
    for node, model in ANTHROPIC_LOCAL_PRESET.items():
        rows += seed_agent_config("anthropic", model, nodes=[node])
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
        default=None,
        help=f"Model name for every node (default: {DEFAULT_MODEL} on {DEFAULT_PROVIDER}, "
        "else the provider's own default, fast tier for fast nodes).",
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
    parser.add_argument(
        "--preset",
        choices=["anthropic-local"],
        default=None,
        help="Apply a named per-node map (ignores the other flags).",
    )
    args = parser.parse_args()

    if args.preset == "anthropic-local":
        rows = seed_anthropic_local()
    else:
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
