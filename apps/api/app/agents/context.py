"""Per-run agent context — LangGraph 1.0 ``context`` channel (specs/runtime-context-config).

``AgentContext`` is the typed, per-request, read-only context the graph is invoked
with (``graph.ainvoke(..., context=AgentContext(...))``). Unlike state it is NOT
persisted in the checkpoint, and unlike ``config["configurable"]`` it is the 1.0
home for *application* context. It carries the BE-resolved **tier**, already
reduced to concrete capabilities so nodes/tools stay dumb (they just read flags).

The user-selectable "mode" lever (MIN-43) has been removed: every run now gets
the fixed BALANCED capability set, gated only by the tier ceiling below. Model
selection comes from the DB/env-backed ``get_agent_llm`` config, not from a
per-request hint.

The tier -> capability mapping lives in ONE place, ``resolve_agent_context``, so
the policy never drifts across nodes.
"""

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
    allow_reflection: bool = True
    allow_memory_write: bool = True
    # P2: episodic recall (planner's recall_past_trips). Default ON for everyone.
    allow_episodic: bool = True
    response_style: ResponseStyle = ResponseStyle.DEFAULT
    # None means "all sub-agents allowed"; a frozenset restricts routing (Phase D.1).
    allowed_subagents: frozenset[str] | None = None
    max_revisions: int = 1
    # Per-request IANA timezone used to ground "today" for relative-date
    # resolution; None keeps the legacy UTC behavior.
    timezone: str | None = None


def resolve_agent_context(
    *,
    tier: Tier | str | None,
    allow_reflection: bool = True,
    timezone: str | None = None,
) -> AgentContext:
    """Map tier -> concrete ``AgentContext`` (the single policy function).

    Unknown/None tier falls back to the safe default (``free``). Pure +
    deterministic. Every run gets the fixed BALANCED capability set below;
    ``tier`` is the only ceiling applied on top.

    Tier ceilings (D.1 confirmed product decision):
    - **free**: ``allowed_subagents`` excludes all premium-only sub-agents
      (currently: "booking").
    - **premium**: ``allowed_subagents=None`` (all permitted).

    :param tier: BE-resolved tier (raw string, enum, or None); falls back to
        ``DEFAULT_TIER`` when unknown/None.
    :param allow_reflection: DB-config-driven reflection gate (from
        ``agent_config.enabled``); defaults True.
    :param timezone: Per-request IANA timezone for relative-date resolution;
        None keeps the legacy UTC behavior.
    :return: The resolved ``AgentContext`` for this request.
    """
    # Coerce a raw string (from the DB) to the enum; unknown or None values
    # fall back to the safe default.
    try:
        tier = Tier(tier)
    except ValueError:
        tier = DEFAULT_TIER

    allowed_subagents: frozenset[str] | None

    if tier == Tier.FREE:
        # Free cannot reach premium-only sub-agents.
        allowed_subagents = frozenset(ALL_SUBAGENTS) - PREMIUM_ONLY_SUBAGENTS
    else:
        # Premium: all sub-agents permitted.
        allowed_subagents = None

    return AgentContext(
        tier=tier,
        allow_reflection=allow_reflection,
        allow_memory_write=True,
        allow_episodic=True,
        response_style=ResponseStyle.DEFAULT,
        allowed_subagents=allowed_subagents,
        max_revisions=1,
        timezone=timezone,
    )
