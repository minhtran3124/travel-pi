"""Task 2.5 — Context allow_episodic flag (specs/agent-memory-layers P2)."""

from app.enums import ChatMode, Tier


def test_default_agent_context_allow_episodic_true():
    """Default AgentContext() is allow_episodic=True (on for everyone in P2 v1)."""
    from app.agents.context import AgentContext

    ctx = AgentContext()
    assert ctx.allow_episodic is True


def test_fast_mode_resolves_to_true():
    """FAST mode → allow_episodic = True (episodic recall stays on, unlike allow_rag)."""
    from app.agents.context import resolve_agent_context

    ctx = resolve_agent_context(tier=Tier.FREE, mode=ChatMode.FAST)
    assert ctx.allow_episodic is True


def test_balanced_mode_resolves_to_true():
    """BALANCED mode → allow_episodic = True."""
    from app.agents.context import resolve_agent_context

    ctx = resolve_agent_context(tier=Tier.FREE, mode=ChatMode.BALANCED)
    assert ctx.allow_episodic is True


def test_deep_mode_resolves_to_true():
    """DEEP mode → allow_episodic = True."""
    from app.agents.context import resolve_agent_context

    ctx = resolve_agent_context(tier=Tier.PREMIUM, mode=ChatMode.DEEP)
    assert ctx.allow_episodic is True


def test_free_tier_does_not_gate_episodic():
    """Episodic recall is NOT tier-gated — free users keep it (mirrors P1 memory, not RAG)."""
    from app.agents.context import resolve_agent_context

    ctx = resolve_agent_context(tier=Tier.FREE, mode=ChatMode.BALANCED)
    assert ctx.allow_episodic is True
    # Contrast: RAG IS gated off for free, to prove episodic is a separate concern.
    assert ctx.allow_rag is False


def test_episodic_independent_of_memory_write_gate():
    """allow_episodic is a separate flag from allow_memory_write."""
    from app.agents.context import resolve_agent_context

    fast = resolve_agent_context(tier=Tier.FREE, mode=ChatMode.FAST)
    # FAST turns off memory WRITE, but episodic READ stays on.
    assert fast.allow_memory_write is False
    assert fast.allow_episodic is True
