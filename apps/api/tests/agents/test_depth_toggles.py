"""Depth toggle tests (specs/runtime-context-config C.2).

Verifies that:
- Response style "default" adds no extra directive (the only value reachable
  now that MIN-43 removed the mode-driven CONCISE/DETAILED prompt injection).

The reflection-gate tests that used to live here went away with the reflection
node itself (#112) — there is no longer an ``allow_reflection`` /
``max_revisions`` toggle to exercise.

All tests are offline: FakeLLM is used, no network calls.
"""

from __future__ import annotations

from app.agents.context import AgentContext
from app.agents.subagents._base import build_subagent
from app.clients.llm import FakeLLM
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult

# ---------------------------------------------------------------------------
# Response style — system prompt directive injection
# ---------------------------------------------------------------------------


def _make_capturing_generate(captured: list):
    """Return a _generate replacement that records messages and returns 'ok'."""

    def spy(self, messages, stop=None, run_manager=None, **kwargs):
        captured.extend(messages)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="ok"))])

    return spy


def test_response_style_default_adds_no_directive(monkeypatch):
    """'default' response_style adds no extra directive to the system prompt."""
    captured: list = []
    monkeypatch.setattr(FakeLLM, "_generate", _make_capturing_generate(captured))

    fake = FakeLLM()
    subgraph = build_subagent("style_default", [], lambda _: fake, "base prompt")
    state = {"messages": [HumanMessage(content="hi")]}
    subgraph.invoke(state, context=AgentContext(response_style="default"))

    assert captured, "LLM was never invoked"
    system_content = captured[0].content
    assert "Be brief." not in system_content
    assert "Be thorough." not in system_content
