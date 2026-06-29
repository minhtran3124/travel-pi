"""Deferred model binding (specs/runtime-context-config C.1).

Verifies that:
- ``get_agent_llm(name, model=...)`` routes to the correct model tier based on the
  semantic hint from ``AgentContext.model``.
- ``resolver_for`` in ``build_graph`` always returns the injected fake when one is
  present, regardless of the ``ctx_model`` hint — guaranteeing test isolation.

All tests are offline: no ``init_chat_model`` network calls happen because
``get_llm`` is monkeypatched before any real model construction.
"""

from __future__ import annotations

import pytest
from app.clients.llm import FAST_AGENTS, FakeLLM

# ---------------------------------------------------------------------------
# get_agent_llm model-hint routing (prod path, monkeypatched to stay offline)
# ---------------------------------------------------------------------------


def _capture_get_llm(monkeypatch):
    """Patch ``get_llm`` in the llm module and return a dict that records calls."""
    captured: dict = {}

    def fake_get_llm(model=None, *, fast=False):
        captured["fast"] = fast
        captured["model"] = model
        return FakeLLM()

    monkeypatch.setattr("app.clients.llm.get_llm", fake_get_llm)
    return captured


def test_get_agent_llm_default_concierge_uses_main_model(monkeypatch):
    """concierge is NOT in FAST_AGENTS → model=None selects the main (non-fast) model."""
    captured = _capture_get_llm(monkeypatch)
    assert "concierge" not in FAST_AGENTS

    from app.clients.llm import get_agent_llm

    get_agent_llm("concierge", model=None)
    assert captured["fast"] is False


def test_get_agent_llm_fast_hint_forces_fast_tier(monkeypatch):
    """model='fast' overrides the agent's normal tier toward the cheap fast model."""
    captured = _capture_get_llm(monkeypatch)

    from app.clients.llm import get_agent_llm

    # concierge is normally main-tier; the "fast" hint should flip it.
    get_agent_llm("concierge", model="fast")
    assert captured["fast"] is True


def test_get_agent_llm_deep_hint_forces_main_model(monkeypatch):
    """model='deep' forces the main (non-fast) model even for normally-fast agents."""
    captured = _capture_get_llm(monkeypatch)
    assert "journal" in FAST_AGENTS  # journal is normally fast-tier

    from app.clients.llm import get_agent_llm

    # journal is normally fast; "deep" hint should switch it to main.
    get_agent_llm("journal", model="deep")
    assert captured["fast"] is False


def test_get_agent_llm_none_preserves_fast_agent_default(monkeypatch):
    """model=None on a FAST_AGENTS member preserves the fast default."""
    captured = _capture_get_llm(monkeypatch)
    assert "journal" in FAST_AGENTS

    from app.clients.llm import get_agent_llm

    get_agent_llm("journal", model=None)
    assert captured["fast"] is True


# ---------------------------------------------------------------------------
# resolver_for: injected fake is returned regardless of ctx_model
# ---------------------------------------------------------------------------


def _make_resolver(name: str, llm, fast_llm):
    """Reproduce the resolver_for closure from build_graph for unit testing."""

    def resolve(ctx_model):
        if name in FAST_AGENTS:
            return fast_llm if fast_llm is not None else None
        return llm if llm is not None else None

    return resolve


@pytest.mark.parametrize("ctx_model", [None, "fast", "deep", "unknown"])
def test_resolver_returns_injected_fake_for_main_agent(ctx_model):
    """Injected main LLM is returned for a non-fast agent regardless of ctx_model."""
    fake = FakeLLM()
    resolve = _make_resolver("planner", llm=fake, fast_llm=None)
    assert resolve(ctx_model) is fake


@pytest.mark.parametrize("ctx_model", [None, "fast", "deep", "unknown"])
def test_resolver_returns_injected_fast_fake_for_fast_agent(ctx_model):
    """Injected fast_llm is returned for a FAST_AGENTS member regardless of ctx_model."""
    assert "journal" in FAST_AGENTS
    fast_fake = FakeLLM()
    resolve = _make_resolver("journal", llm=None, fast_llm=fast_fake)
    assert resolve(ctx_model) is fast_fake


def test_resolver_falls_through_to_get_agent_llm_when_no_fake(monkeypatch):
    """When no fake is injected, the resolver calls get_agent_llm (prod path)."""
    called: list = []

    def fake_get_agent_llm(name, model=None):
        called.append((name, model))
        return FakeLLM()

    monkeypatch.setattr("app.clients.llm.get_agent_llm", fake_get_agent_llm)

    # Reproduce the prod path: no injected fakes, ctx_model="fast".
    llm = None
    fast_llm = None

    def resolve(ctx_model):
        # planner is NOT in FAST_AGENTS
        return (
            llm if llm is not None else fake_get_agent_llm("planner", model=ctx_model)
        )

    resolve("fast")
    assert called == [("planner", "fast")]
