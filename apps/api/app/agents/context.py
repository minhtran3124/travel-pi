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

# Recognised values; anything else falls back to the safe default.
MODES = ("fast", "balanced", "deep")
TIERS = ("free", "premium")
DEFAULT_MODE = "balanced"
DEFAULT_TIER = "free"


@dataclass(frozen=True)
class AgentContext:
    """Resolved per-run capabilities. Defaults == today's behavior."""

    tier: str = DEFAULT_TIER
    mode: str = DEFAULT_MODE
    # Semantic model hint resolved to a concrete model in Phase C.1:
    # None -> per-agent default (settings.agent_llm_configs); "fast"/"deep" tiers.
    model: str | None = None
    allow_reflection: bool = True
    allow_rag: bool = True
    response_style: str = "default"
    # None means "all sub-agents allowed"; a frozenset restricts routing (Phase D.1).
    allowed_subagents: frozenset[str] | None = None
    max_revisions: int = 1


# mode -> the depth/model/style it requests (before any tier ceiling).
_MODE_POLICY: dict[str, dict] = {
    "fast": {
        "model": "fast",
        "allow_reflection": False,
        "allow_rag": False,
        "response_style": "concise",
        "max_revisions": 0,
    },
    "balanced": {
        "model": None,
        "allow_reflection": True,
        "allow_rag": True,
        "response_style": "default",
        "max_revisions": 1,
    },
    "deep": {
        "model": "deep",
        "allow_reflection": True,
        "allow_rag": True,
        "response_style": "detailed",
        "max_revisions": 2,
    },
}


def resolve_agent_context(*, tier: str | None, mode: str | None) -> AgentContext:
    """Map (tier, mode) -> concrete ``AgentContext`` (the single policy function).

    Unknown/None tier or mode fall back to the safe defaults (``free`` /
    ``balanced``), which equal today's behavior. ``mode`` is the user-chosen
    depth lever; ``tier`` is the BE-resolved ceiling. Pure + deterministic.

    Tier ceiling (proposed default — confirmed at D.1 before wiring): ``free``
    cannot use the premium ``deep`` model (downgraded to the per-agent default);
    the costlier ``deep`` mode is otherwise honored. Sub-agent/tool gating and
    quota are layered on in D.1/D.2; this function stays the one place to change
    the policy.
    """
    tier = tier if tier in TIERS else DEFAULT_TIER
    mode = mode if mode in _MODE_POLICY else DEFAULT_MODE
    p = _MODE_POLICY[mode]

    model = p["model"]
    if tier == "free" and model == "deep":
        # Free tier may not select the premium (expensive) model.
        model = None

    return AgentContext(
        tier=tier,
        mode=mode,
        model=model,
        allow_reflection=p["allow_reflection"],
        allow_rag=p["allow_rag"],
        response_style=p["response_style"],
        allowed_subagents=None,
        max_revisions=p["max_revisions"],
    )
