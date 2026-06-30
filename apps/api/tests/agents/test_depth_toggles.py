"""Depth toggle tests (specs/runtime-context-config C.2).

Verifies that:
- Reflection node short-circuits (goes to END) when allow_reflection=False.
- Reflection node short-circuits when max_revisions is reached.
- Reflection node runs the LLM and routes normally with default context.
- Assistant node drops the RAG tool when allow_rag=False.
- Assistant node keeps the RAG tool when allow_rag=True.
- Response style "concise" injects "Be brief." into the system prompt.
- Response style "detailed" injects "Be thorough." into the system prompt.
- Response style "default" adds no extra directive.

All tests are offline: FakeLLM is used, no network calls.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.context import AgentContext
from app.agents.nodes import make_reflection_node
from app.agents.subagents._base import RAG_TOOL_NAME, build_subagent
from app.clients.llm import FakeLLM
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool as lc_tool
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
    """Reflection node goes to extract_memory when allow_reflection=False."""
    llm = FakeLLM(responses=["REVISE please"])  # would trigger a loop if reached
    reflect = make_reflection_node(llm)

    state = _base_state(messages=[AIMessage(content="answer")])
    ctx = AgentContext(allow_reflection=False, max_revisions=1)
    result = reflect(state, _runtime(ctx))

    assert result.goto == "extract_memory"


def test_reflection_skips_when_max_revisions_zero():
    """Reflection node goes to extract_memory when max_revisions=0 (fast mode)."""
    llm = FakeLLM(responses=["REVISE please"])
    reflect = make_reflection_node(llm)

    state = _base_state(messages=[AIMessage(content="answer")], revisions=0)
    ctx = AgentContext(allow_reflection=True, max_revisions=0)
    result = reflect(state, _runtime(ctx))

    assert result.goto == "extract_memory"


def test_reflection_skips_when_revisions_reached():
    """Reflection node exits to extract_memory when revisions >= max_revisions."""
    llm = FakeLLM(responses=["REVISE please"])
    reflect = make_reflection_node(llm)

    state = _base_state(messages=[AIMessage(content="answer")], revisions=2)
    ctx = AgentContext(allow_reflection=True, max_revisions=2)
    result = reflect(state, _runtime(ctx))

    assert result.goto == "extract_memory"


def test_reflection_runs_with_default_context():
    """Reflection node invokes LLM and goes to extract_memory on LGTM verdict."""
    llm = FakeLLM(responses=["LGTM"])
    reflect = make_reflection_node(llm)

    state = _base_state(messages=[AIMessage(content="answer")], revisions=0)
    # default AgentContext: allow_reflection=True, max_revisions=1
    result = reflect(state, _runtime(AgentContext()))

    assert result.goto == "extract_memory"


def test_reflection_loops_on_revise_verdict():
    """Reflection node returns Command(goto=current_flow) when verdict is REVISE."""
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


# ---------------------------------------------------------------------------
# RAG tool gating in assistant node
# ---------------------------------------------------------------------------


@lc_tool
def search_destination_knowledge(query: str) -> list:  # noqa: D401
    """Fake RAG tool with canonical name."""
    return []


@lc_tool
def get_weather(city: str) -> str:  # noqa: D401
    """Non-RAG tool."""
    return "sunny"


def test_assistant_drops_rag_tool_when_allow_rag_false(monkeypatch):
    """RAG tool is excluded from bind_tools when allow_rag=False."""
    bind_calls: list[list[str]] = []

    _orig_bind = FakeLLM.bind_tools

    def capturing_bind(self, tools, **kwargs):
        bind_calls.append([t.name for t in tools])
        return _orig_bind(self, tools, **kwargs)

    monkeypatch.setattr(FakeLLM, "bind_tools", capturing_bind)

    fake = FakeLLM(responses=["answer"])
    subgraph = build_subagent(
        "test_rag_off",
        [search_destination_knowledge, get_weather],
        lambda _: fake,
        "test prompt",
    )
    state = {"messages": [HumanMessage(content="hi")]}
    subgraph.invoke(state, context=AgentContext(allow_rag=False))

    assert bind_calls, "bind_tools was never called"
    assert RAG_TOOL_NAME not in bind_calls[-1], (
        f"RAG tool was not filtered out: {bind_calls[-1]}"
    )
    assert "get_weather" in bind_calls[-1]


def test_assistant_keeps_rag_tool_when_allow_rag_true(monkeypatch):
    """RAG tool is included in bind_tools when allow_rag=True (default)."""
    bind_calls: list[list[str]] = []

    _orig_bind = FakeLLM.bind_tools

    def capturing_bind(self, tools, **kwargs):
        bind_calls.append([t.name for t in tools])
        return _orig_bind(self, tools, **kwargs)

    monkeypatch.setattr(FakeLLM, "bind_tools", capturing_bind)

    fake = FakeLLM(responses=["answer"])
    subgraph = build_subagent(
        "test_rag_on",
        [search_destination_knowledge, get_weather],
        lambda _: fake,
        "test prompt",
    )
    state = {"messages": [HumanMessage(content="hi")]}
    subgraph.invoke(state, context=AgentContext(allow_rag=True))

    assert bind_calls, "bind_tools was never called"
    assert RAG_TOOL_NAME in bind_calls[-1], (
        f"RAG tool was unexpectedly filtered: {bind_calls[-1]}"
    )


# ---------------------------------------------------------------------------
# Response style — system prompt directive injection
# ---------------------------------------------------------------------------


def _make_capturing_generate(captured: list):
    """Return a _generate replacement that records messages and returns 'ok'."""

    def spy(self, messages, stop=None, run_manager=None, **kwargs):
        captured.extend(messages)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="ok"))])

    return spy


def test_response_style_concise_adds_be_brief(monkeypatch):
    """'concise' response_style appends 'Be brief.' to the system prompt."""
    captured: list = []
    monkeypatch.setattr(FakeLLM, "_generate", _make_capturing_generate(captured))

    fake = FakeLLM()
    subgraph = build_subagent("style_concise", [], lambda _: fake, "base prompt")
    state = {"messages": [HumanMessage(content="hi")]}
    subgraph.invoke(state, context=AgentContext(response_style="concise"))

    assert captured, "LLM was never invoked"
    system_content = captured[0].content
    assert "Be brief." in system_content


def test_response_style_detailed_adds_be_thorough(monkeypatch):
    """'detailed' response_style appends 'Be thorough.' to the system prompt."""
    captured: list = []
    monkeypatch.setattr(FakeLLM, "_generate", _make_capturing_generate(captured))

    fake = FakeLLM()
    subgraph = build_subagent("style_detailed", [], lambda _: fake, "base prompt")
    state = {"messages": [HumanMessage(content="hi")]}
    subgraph.invoke(state, context=AgentContext(response_style="detailed"))

    assert captured, "LLM was never invoked"
    system_content = captured[0].content
    assert "Be thorough." in system_content


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
