"""AgentContext + resolve_agent_context policy (specs/runtime-context-config A.1).

Pins the single (tier, mode) -> capability mapping. Nothing reads the context yet
(plumbing only), so these tests guard the policy itself, not runtime behavior.
"""

from __future__ import annotations

from app.agents.context import AgentContext, resolve_agent_context


def test_defaults_equal_todays_behavior():
    # The dataclass default (used when the graph is invoked without context=)
    # must be the permissive, present-day behavior.
    ctx = AgentContext()
    assert ctx.tier == "free"
    assert ctx.mode == "balanced"
    assert ctx.model is None
    assert ctx.allow_reflection is True
    assert ctx.allow_rag is True
    assert ctx.allowed_subagents is None
    assert ctx.max_revisions == 1


def test_unknown_tier_and_mode_fall_back_to_defaults():
    ctx = resolve_agent_context(tier="enterprise", mode="turbo")
    assert ctx.tier == "free"
    assert ctx.mode == "balanced"
    assert ctx.model is None
    assert ctx.allow_reflection is True
    assert ctx.allow_rag is True
    assert ctx.max_revisions == 1


def test_none_inputs_fall_back_to_defaults():
    ctx = resolve_agent_context(tier=None, mode=None)
    assert ctx.tier == "free"
    assert ctx.mode == "balanced"


def test_free_balanced_matches_present_behavior():
    ctx = resolve_agent_context(tier="free", mode="balanced")
    assert ctx.model is None
    assert ctx.allow_reflection is True
    assert ctx.allow_rag is True
    assert ctx.max_revisions == 1


def test_free_fast_trims_depth():
    ctx = resolve_agent_context(tier="free", mode="fast")
    assert ctx.mode == "fast"
    assert ctx.model == "fast"
    assert ctx.allow_reflection is False
    assert ctx.allow_rag is False
    assert ctx.response_style == "concise"
    assert ctx.max_revisions == 0


def test_premium_deep_unlocks_full_depth():
    ctx = resolve_agent_context(tier="premium", mode="deep")
    assert ctx.tier == "premium"
    assert ctx.model == "deep"
    assert ctx.allow_reflection is True
    assert ctx.allow_rag is True
    assert ctx.response_style == "detailed"
    assert ctx.max_revisions == 2


def test_free_deep_is_capped_to_default_model():
    # Free tier requested deep mode: keep the deeper loop/style but downgrade the
    # premium model to the per-agent default (cost ceiling).
    ctx = resolve_agent_context(tier="free", mode="deep")
    assert ctx.model is None
    assert ctx.allow_reflection is True
    assert ctx.max_revisions == 2


def test_resolve_is_pure():
    a = resolve_agent_context(tier="premium", mode="deep")
    b = resolve_agent_context(tier="premium", mode="deep")
    assert a == b
