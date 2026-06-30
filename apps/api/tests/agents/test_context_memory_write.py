"""Task 1.2 — Context allow_memory_write flag (specs/agent-memory-layers)."""

from app.enums import ChatMode, Tier


def test_default_agent_context_allow_memory_write_true():
    """Default AgentContext() preserves today's behavior (allow_memory_write=True)."""
    from app.agents.context import AgentContext

    ctx = AgentContext()
    assert ctx.allow_memory_write is True


def test_fast_mode_resolves_to_false():
    """FAST mode → allow_memory_write = False."""
    from app.agents.context import resolve_agent_context

    ctx = resolve_agent_context(tier=Tier.FREE, mode=ChatMode.FAST)
    assert ctx.allow_memory_write is False


def test_balanced_mode_resolves_to_true():
    """BALANCED mode → allow_memory_write = True."""
    from app.agents.context import resolve_agent_context

    ctx = resolve_agent_context(tier=Tier.FREE, mode=ChatMode.BALANCED)
    assert ctx.allow_memory_write is True


def test_deep_mode_resolves_to_true():
    """DEEP mode → allow_memory_write = True."""
    from app.agents.context import resolve_agent_context

    ctx = resolve_agent_context(tier=Tier.PREMIUM, mode=ChatMode.DEEP)
    assert ctx.allow_memory_write is True


def test_free_tier_does_not_gate_memory_write():
    """Memory write is NOT tier-gated — free users keep it (per D5)."""
    from app.agents.context import resolve_agent_context

    ctx = resolve_agent_context(tier=Tier.FREE, mode=ChatMode.BALANCED)
    assert ctx.allow_memory_write is True
