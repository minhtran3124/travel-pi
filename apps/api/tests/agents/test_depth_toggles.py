"""Reflection short-circuit gates (allow_reflection / max_revisions) and response-style directive injection. Offline: FakeLLM only."""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.context import AgentContext
from app.agents.nodes import make_reflection_node
from app.agents.subagents._base import build_subagent
from app.clients.llm import FakeLLM
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.graph import END

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _runtime(ctx: AgentContext | None = None):
    """Minimal runtime stand-in: exposes only .context, which is all nodes read."""
    return SimpleNamespace(context=ctx)


def _base_state(**overrides):
    """Minimal TravelAgentState for testing."""
    state = {
        "messages": [HumanMessage(content="hi")],
        "revisions": 0,
        "current_flow": None,
        "user_id": None,
        "trip_id": None,
        "summary": None,
        "trip_context": None,
    }
    state.update(overrides)
    return state


# ---------------------------------------------------------------------------
# Reflection node — allow_reflection / max_revisions gates
# ---------------------------------------------------------------------------


def test_reflection_skips_when_allow_reflection_false():
    llm = FakeLLM(responses=["REVISE please"])  # would trigger a loop if reached
    reflect = make_reflection_node(llm)

    state = _base_state(messages=[AIMessage(content="answer")])
    ctx = AgentContext(allow_reflection=False, max_revisions=1)
    result = reflect(state, _runtime(ctx))

    assert result.goto == END


def test_reflection_skips_when_max_revisions_zero():
    llm = FakeLLM(responses=["REVISE please"])
    reflect = make_reflection_node(llm)

    state = _base_state(messages=[AIMessage(content="answer")], revisions=0)
    ctx = AgentContext(allow_reflection=True, max_revisions=0)
    result = reflect(state, _runtime(ctx))

    assert result.goto == END


def test_reflection_skips_when_revisions_reached():
    llm = FakeLLM(responses=["REVISE please"])
    reflect = make_reflection_node(llm)

    state = _base_state(messages=[AIMessage(content="answer")], revisions=2)
    ctx = AgentContext(allow_reflection=True, max_revisions=2)
    result = reflect(state, _runtime(ctx))

    assert result.goto == END


def test_reflection_runs_with_default_context():
    llm = FakeLLM(responses=["LGTM"])
    reflect = make_reflection_node(llm)

    state = _base_state(messages=[AIMessage(content="answer")], revisions=0)
    # default AgentContext: allow_reflection=True, max_revisions=1
    result = reflect(state, _runtime(AgentContext()))

    assert result.goto == END


def test_reflection_loops_on_revise_verdict():
    llm = FakeLLM(responses=["REVISE this answer"])
    reflect = make_reflection_node(llm)

    state = _base_state(
        messages=[AIMessage(content="answer")],
        revisions=0,
        current_flow="concierge",
    )
    ctx = AgentContext(allow_reflection=True, max_revisions=1)
    result = reflect(state, _runtime(ctx))

    assert result.goto == "concierge"
    assert result.update["revisions"] == 1


def test_reflection_skips_when_awaiting_user():
    """A turn blocked on the traveller ends at END before the judge, so its clarifying question is not REVISEd away."""
    llm = FakeLLM(responses=["REVISE this answer"])  # would loop if reflection ran
    reflect = make_reflection_node(llm)

    state = _base_state(
        messages=[AIMessage(content="Which exact date do you want to depart?")],
        revisions=0,
        current_flow="planner",
        awaiting_user=True,
    )
    ctx = AgentContext(allow_reflection=True, max_revisions=1)
    result = reflect(state, _runtime(ctx))

    assert result.goto == END


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
