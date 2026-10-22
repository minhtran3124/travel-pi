"""Per-run agent context — LangGraph ``context`` channel carrying resolved capabilities."""

from __future__ import annotations

from dataclasses import dataclass

from app.agents.constants import (
    ALL_SUBAGENTS,
    DEFAULT_TIER,
    PREMIUM_ONLY_SUBAGENTS,
)
from app.enums import ResponseStyle, Tier


@dataclass(frozen=True)
class AgentContext:
    """Resolved per-run capabilities. Defaults == today's behavior."""

    tier: Tier = DEFAULT_TIER
    # Defaults False so a path that forgets to resolve identity is treated as
    # anonymous — a missing flag must not silently grant trip creation.
    authenticated: bool = False
    allow_reflection: bool = True
    allow_memory_write: bool = True
    allow_episodic: bool = True
    response_style: ResponseStyle = ResponseStyle.DEFAULT
    # None means "all sub-agents allowed"; a frozenset restricts routing.
    allowed_subagents: frozenset[str] | None = None
    max_revisions: int = 1
    # Per-request IANA timezone grounding "today"; None keeps UTC.
    timezone: str | None = None


def resolve_agent_context(
    *,
    tier: Tier | str | None,
    authenticated: bool = False,
    allow_reflection: bool = True,
    timezone: str | None = None,
) -> AgentContext:
    """Map tier -> concrete ``AgentContext``; free excludes premium-only sub-agents."""
    # Coerce a raw string (from the DB) to the enum; unknown/None -> safe default.
    try:
        tier = Tier(tier)
    except ValueError:
        tier = DEFAULT_TIER

    allowed_subagents: frozenset[str] | None

    if tier == Tier.FREE:
        allowed_subagents = frozenset(ALL_SUBAGENTS) - PREMIUM_ONLY_SUBAGENTS
    else:
        allowed_subagents = None

    return AgentContext(
        tier=tier,
        authenticated=authenticated,
        allow_reflection=allow_reflection,
        allow_memory_write=True,
        allow_episodic=True,
        response_style=ResponseStyle.DEFAULT,
        allowed_subagents=allowed_subagents,
        max_revisions=1,
        timezone=timezone,
    )
