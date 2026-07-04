"""AgentContext + resolve_agent_context policy (specs/runtime-context-config A.1 / D.1).

Pins the single tier -> capability mapping. D.1 adds tier-level gating: free
loses booking; premium keeps all sub-agents. The user-selectable
"mode" lever was removed in MIN-43 — every run gets the fixed BALANCED
capability set, gated only by tier.
"""

from __future__ import annotations

from app.agents.context import (
    ALL_SUBAGENTS,
    PREMIUM_ONLY_SUBAGENTS,
    AgentContext,
    resolve_agent_context,
)

_FREE_SUBAGENTS = frozenset(ALL_SUBAGENTS) - PREMIUM_ONLY_SUBAGENTS


def test_defaults_equal_todays_behavior():
    # The dataclass default (used when the graph is invoked without context=)
    # must be the permissive, present-day behavior (legacy path: no context= passed).
    ctx = AgentContext()
    assert ctx.tier == "free"
    assert ctx.allow_reflection is True
    assert ctx.allowed_subagents is None
    assert ctx.max_revisions == 1


def test_unknown_tier_falls_back_to_free():
    # Unknown values fall back to free — free policy applies.
    ctx = resolve_agent_context(tier="enterprise")
    assert ctx.tier == "free"
    assert ctx.allow_reflection is True
    assert ctx.max_revisions == 1
    # free tier: booking excluded
    assert ctx.allowed_subagents == _FREE_SUBAGENTS


def test_none_input_falls_back_to_free():
    ctx = resolve_agent_context(tier=None)
    assert ctx.tier == "free"
    assert ctx.allowed_subagents == _FREE_SUBAGENTS


def test_free_gates_booking():
    ctx = resolve_agent_context(tier="free")
    assert ctx.allow_reflection is True
    assert ctx.max_revisions == 1
    # D.1: booking excluded from free
    assert ctx.allowed_subagents is not None
    assert "booking" not in ctx.allowed_subagents
    assert ctx.allowed_subagents == _FREE_SUBAGENTS


def test_premium_unlocks_all_subagents():
    ctx = resolve_agent_context(tier="premium")
    assert ctx.tier == "premium"
    assert ctx.allow_reflection is True
    assert ctx.response_style == "default"
    assert ctx.max_revisions == 1
    # D.1: premium allows all sub-agents (None = unrestricted)
    assert ctx.allowed_subagents is None


def test_resolve_is_pure():
    a = resolve_agent_context(tier="premium")
    b = resolve_agent_context(tier="premium")
    assert a == b


def test_free_subagents_contains_core_agents():
    # Sanity: the free allow-list has the non-premium sub-agents.
    assert "planner" in _FREE_SUBAGENTS
    assert "concierge" in _FREE_SUBAGENTS
    assert "journal" in _FREE_SUBAGENTS
    assert "budget" in _FREE_SUBAGENTS
    assert "booking" not in _FREE_SUBAGENTS
