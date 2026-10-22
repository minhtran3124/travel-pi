"""AgentContext + resolve_agent_context tier -> capability policy."""

from __future__ import annotations

from app.agents.context import (
    ALL_SUBAGENTS,
    PREMIUM_ONLY_SUBAGENTS,
    AgentContext,
    resolve_agent_context,
)

_FREE_SUBAGENTS = frozenset(ALL_SUBAGENTS) - PREMIUM_ONLY_SUBAGENTS


def test_defaults_equal_todays_behavior():
    # The default (no context= passed) must stay the permissive legacy behavior.
    ctx = AgentContext()
    assert ctx.tier == "free"
    assert ctx.allow_reflection is True
    assert ctx.allowed_subagents is None
    assert ctx.max_revisions == 1


def test_unknown_tier_falls_back_to_free():
    ctx = resolve_agent_context(tier="enterprise")
    assert ctx.tier == "free"
    assert ctx.allow_reflection is True
    assert ctx.max_revisions == 1
    assert ctx.allowed_subagents == _FREE_SUBAGENTS


def test_none_input_falls_back_to_free():
    ctx = resolve_agent_context(tier=None)
    assert ctx.tier == "free"
    assert ctx.allowed_subagents == _FREE_SUBAGENTS


def test_free_gates_booking():
    ctx = resolve_agent_context(tier="free")
    assert ctx.allow_reflection is True
    assert ctx.max_revisions == 1
    assert ctx.allowed_subagents is not None
    assert "booking" not in ctx.allowed_subagents
    assert ctx.allowed_subagents == _FREE_SUBAGENTS


def test_premium_unlocks_all_subagents():
    ctx = resolve_agent_context(tier="premium")
    assert ctx.tier == "premium"
    assert ctx.allow_reflection is True
    assert ctx.response_style == "default"
    assert ctx.max_revisions == 1
    # None = unrestricted
    assert ctx.allowed_subagents is None


def test_resolve_is_pure():
    a = resolve_agent_context(tier="premium")
    b = resolve_agent_context(tier="premium")
    assert a == b


def test_free_subagents_contains_core_agents():
    assert "planner" in _FREE_SUBAGENTS
    assert "concierge" in _FREE_SUBAGENTS
    assert "journal" in _FREE_SUBAGENTS
    assert "budget" in _FREE_SUBAGENTS
    assert "booking" not in _FREE_SUBAGENTS


def test_resolve_agent_context_honors_allow_reflection():
    """The keyword flag threads into the resolved context; default stays True."""
    from app.agents.context import resolve_agent_context

    assert resolve_agent_context(tier="free").allow_reflection is True
    assert (
        resolve_agent_context(tier="free", allow_reflection=False).allow_reflection
        is False
    )


def test_resolve_context_disables_reflection_from_db_config():
    """`_resolve_context` reads reflection.enabled from the cache (None → on)."""
    from app.core.agent_config_cache import AgentConfigCache, AgentModelOverride
    from app.routers import agent as agent_router

    AgentConfigCache.clear()
    AgentConfigCache.sync_from_cache({"reflection": AgentModelOverride(enabled=False)})
    try:
        ctx = agent_router._resolve_context("anon", False, session=None)
        assert ctx.allow_reflection is False
    finally:
        AgentConfigCache.clear()
