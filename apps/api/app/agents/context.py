"""Per-run agent context — LangGraph 1.0 ``context`` channel (specs/runtime-context-config).

``AgentContext`` is the typed, per-request, read-only context the graph is invoked
with (``graph.ainvoke(..., context=AgentContext(...))``). Unlike state it is NOT
persisted in the checkpoint, and unlike ``config["configurable"]`` it is the 1.0
home for *application* context. It carries the user-selectable **mode** and the
BE-resolved **tier**, already reduced to concrete capabilities so nodes/tools stay
dumb (they just read flags) — see D3 in the plan.

Nothing reads this yet (Task A.1 is plumbing only); nodes/tools start reading it
in Phase C/D. Until then, invoking the graph without ``context=`` uses the
dataclass defaults below, which equal today's behavior (no change).

The (tier, mode) -> capability mapping lives in ONE place, ``resolve_agent_context``,
so the policy never drifts across nodes. The concrete tier-gating values (what
``free`` loses vs ``premium``) are the proposed default and are confirmed at the
D.1 wiring step before they take effect.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.agents.constants import (
    ALL_SUBAGENTS,
    DEFAULT_MODE,
    DEFAULT_TIER,
    PREMIUM_ONLY_SUBAGENTS,
)
from app.enums import ChatMode, ModelHint, ResponseStyle, Tier


@dataclass(frozen=True)
class AgentContext:
    """Resolved per-run capabilities. Defaults == today's behavior."""

    tier: Tier = DEFAULT_TIER
    mode: ChatMode = DEFAULT_MODE
    # Semantic model hint resolved to a concrete model in Phase C.1:
    # None -> per-agent default (settings.agent_llm_configs); FAST/DEEP tiers.
    model: ModelHint | None = None
    allow_reflection: bool = True
    allow_rag: bool = True
    response_style: ResponseStyle = ResponseStyle.DEFAULT
    # None means "all sub-agents allowed"; a frozenset restricts routing (Phase D.1).
    allowed_subagents: frozenset[str] | None = None
    max_revisions: int = 1


# mode -> the depth/model/style it requests (before any tier ceiling).
_MODE_POLICY: dict[ChatMode, dict] = {
    ChatMode.FAST: {
        "model": ModelHint.FAST,
        "allow_reflection": False,
        "allow_rag": False,
        "response_style": ResponseStyle.CONCISE,
        "max_revisions": 0,
    },
    ChatMode.BALANCED: {
        "model": None,
        "allow_reflection": True,
        "allow_rag": True,
        "response_style": ResponseStyle.DEFAULT,
        "max_revisions": 1,
    },
    ChatMode.DEEP: {
        "model": ModelHint.DEEP,
        "allow_reflection": True,
        "allow_rag": True,
        "response_style": ResponseStyle.DETAILED,
        "max_revisions": 2,
    },
}


def resolve_agent_context(
    *, tier: Tier | str | None, mode: ChatMode | str | None
) -> AgentContext:
    """Map (tier, mode) -> concrete ``AgentContext`` (the single policy function, D3).

    Unknown/None tier or mode fall back to the safe defaults (``free`` /
    ``balanced``). ``mode`` is the user-chosen depth lever; ``tier`` is the
    BE-resolved ceiling applied on top. Pure + deterministic.

    Tier ceilings (D.1 confirmed product decision):
    - **free**: ``allow_rag=False`` always; ``allowed_subagents`` excludes all
      premium-only sub-agents (currently: "booking"); model downgraded from
      "deep" to the per-agent default.
    - **premium**: ``allowed_subagents=None`` (all permitted); ``allow_rag``
      follows the mode setting; model unrestricted.
    """
    # Coerce raw strings (from the DB / client body) to enums; unknown or None
    # values fall back to the safe defaults.
    try:
        tier = Tier(tier)
    except ValueError:
        tier = DEFAULT_TIER
    try:
        mode = ChatMode(mode)
    except ValueError:
        mode = DEFAULT_MODE
    p = _MODE_POLICY[mode]

    model = p["model"]
    allow_rag = p["allow_rag"]
    allowed_subagents: frozenset[str] | None

    if tier == Tier.FREE:
        # Free cannot use the expensive deep model.
        if model == ModelHint.DEEP:
            model = None
        # Free cannot use RAG regardless of mode.
        allow_rag = False
        # Free cannot reach premium-only sub-agents.
        allowed_subagents = frozenset(ALL_SUBAGENTS) - PREMIUM_ONLY_SUBAGENTS
    else:
        # Premium: all sub-agents permitted; allow_rag follows mode.
        allowed_subagents = None

    return AgentContext(
        tier=tier,
        mode=mode,
        model=model,
        allow_reflection=p["allow_reflection"],
        allow_rag=allow_rag,
        response_style=p["response_style"],
        allowed_subagents=allowed_subagents,
        max_revisions=p["max_revisions"],
    )
