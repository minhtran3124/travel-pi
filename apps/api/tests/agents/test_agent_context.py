"""AgentContext + resolve_agent_context policy (specs/runtime-context-config A.1 / D.1).

Pins the single (tier, mode) -> capability mapping. D.1 adds tier-level gating:
free loses RAG and booking; premium keeps all sub-agents and mode-driven RAG.
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
    assert ctx.mode == "balanced"
    assert ctx.model is None
    assert ctx.allow_reflection is True
    assert ctx.allow_rag is True
    assert ctx.allowed_subagents is None
    assert ctx.max_revisions == 1


def test_unknown_tier_and_mode_fall_back_to_free_balanced():
    # Unknown values fall back to free/balanced — free policy applies.
    ctx = resolve_agent_context(tier="enterprise", mode="turbo")
    assert ctx.tier == "free"
    assert ctx.mode == "balanced"
    assert ctx.model is None
    assert ctx.allow_reflection is True
    # free tier: RAG always off
    assert ctx.allow_rag is False
    assert ctx.max_revisions == 1
    # free tier: booking excluded
    assert ctx.allowed_subagents == _FREE_SUBAGENTS


def test_none_inputs_fall_back_to_free_balanced():
    ctx = resolve_agent_context(tier=None, mode=None)
    assert ctx.tier == "free"
    assert ctx.mode == "balanced"
    assert ctx.allow_rag is False
    assert ctx.allowed_subagents == _FREE_SUBAGENTS


def test_free_balanced_gates_rag_and_booking():
    ctx = resolve_agent_context(tier="free", mode="balanced")
    assert ctx.model is None
    assert ctx.allow_reflection is True
    # D.1: free tier always has RAG off
    assert ctx.allow_rag is False
    assert ctx.max_revisions == 1
    # D.1: booking excluded from free
    assert ctx.allowed_subagents is not None
    assert "booking" not in ctx.allowed_subagents
    assert ctx.allowed_subagents == _FREE_SUBAGENTS


def test_free_fast_trims_depth_and_gates_booking():
    ctx = resolve_agent_context(tier="free", mode="fast")
    assert ctx.mode == "fast"
    assert ctx.model == "fast"
    assert ctx.allow_reflection is False
    assert ctx.allow_rag is False
    assert ctx.response_style == "concise"
    assert ctx.max_revisions == 0
    # D.1: booking still excluded even in fast mode
    assert ctx.allowed_subagents == _FREE_SUBAGENTS
    assert "booking" not in ctx.allowed_subagents


def test_free_deep_caps_model_and_gates_booking():
    # Free tier requested deep mode: keep the deeper loop/style but downgrade the
    # premium model to the per-agent default (cost ceiling), and still gate booking.
    ctx = resolve_agent_context(tier="free", mode="deep")
    assert ctx.model is None
    assert ctx.allow_reflection is True
    assert ctx.max_revisions == 2
    assert ctx.allow_rag is False
    assert ctx.allowed_subagents == _FREE_SUBAGENTS
    assert "booking" not in ctx.allowed_subagents


def test_premium_deep_unlocks_full_depth_and_all_subagents():
    ctx = resolve_agent_context(tier="premium", mode="deep")
    assert ctx.tier == "premium"
    assert ctx.model == "deep"
    assert ctx.allow_reflection is True
    assert ctx.allow_rag is True
    assert ctx.response_style == "detailed"
    assert ctx.max_revisions == 2
    # D.1: premium allows all sub-agents (None = unrestricted)
    assert ctx.allowed_subagents is None


def test_premium_balanced_allows_all_subagents():
    ctx = resolve_agent_context(tier="premium", mode="balanced")
    assert ctx.allow_rag is True
    assert ctx.allowed_subagents is None


def test_premium_fast_allows_all_subagents():
    ctx = resolve_agent_context(tier="premium", mode="fast")
    # fast mode still disables RAG even for premium
    assert ctx.allow_rag is False
    # but all sub-agents (including booking) remain reachable
    assert ctx.allowed_subagents is None


def test_resolve_is_pure():
    a = resolve_agent_context(tier="premium", mode="deep")
    b = resolve_agent_context(tier="premium", mode="deep")
    assert a == b


def test_free_subagents_contains_core_agents():
    # Sanity: the free allow-list has the non-premium sub-agents.
    assert "planner" in _FREE_SUBAGENTS
    assert "concierge" in _FREE_SUBAGENTS
    assert "journal" in _FREE_SUBAGENTS
    assert "budget" in _FREE_SUBAGENTS
    assert "booking" not in _FREE_SUBAGENTS
