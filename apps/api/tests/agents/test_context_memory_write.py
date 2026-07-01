"""Task 1.2 — Context allow_memory_write flag (specs/agent-memory-layers)."""

from app.enums import Tier


def test_default_agent_context_allow_memory_write_true():
    """Default AgentContext() preserves today's behavior (allow_memory_write=True)."""
    from app.agents.context import AgentContext

    ctx = AgentContext()
    assert ctx.allow_memory_write is True


def test_free_tier_does_not_gate_memory_write():
    """Memory write is NOT tier-gated — free users keep it (per D5)."""
    from app.agents.context import resolve_agent_context

    ctx = resolve_agent_context(tier=Tier.FREE)
    assert ctx.allow_memory_write is True
