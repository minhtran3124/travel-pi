"""Context allow_episodic flag."""

from app.enums import Tier


def test_default_agent_context_allow_episodic_true():
    from app.agents.context import AgentContext

    ctx = AgentContext()
    assert ctx.allow_episodic is True


def test_free_tier_does_not_gate_episodic():
    """Episodic recall is not tier-gated — mirrors P1 memory, not RAG."""
    from app.agents.context import resolve_agent_context

    ctx = resolve_agent_context(tier=Tier.FREE)
    assert ctx.allow_episodic is True
