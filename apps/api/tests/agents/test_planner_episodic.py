"""Task 2.4 — Planner episodic recall integration + gating (specs/agent-memory-layers P2)."""

from langchain_core.messages import AIMessage, HumanMessage


def _build_planner_graph(store):
    """Build a graph routing to the planner with a capturing main LLM."""
    from app.agents.graph import build_graph
    from app.agents.supervisor import SupervisorIntent
    from app.clients.llm import FakeLLM
    from langgraph.checkpoint.memory import MemorySaver

    main = FakeLLM(
        structured_responses=[SupervisorIntent(target_agent="planner")] * 4,
        responses=[
            # planner assistant: emit a recall_past_trips tool call
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "recall_past_trips",
                        "args": {"query": "beach trip"},
                        "id": "r1",
                    }
                ],
            ),
            # planner assistant: final answer after the tool returns
            "Based on your past trips, I suggest a relaxed beach itinerary.",
        ],
    )
    fast = FakeLLM(
        responses=["OK", '{"preferences": [], "instructions": [], "episodes": []}']
    )
    graph = build_graph(
        llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=store
    )
    return graph


def test_planner_recalls_seeded_episode():
    """A seeded episode is returned by recall_past_trips during a planner turn."""
    from app.memory.store import upsert_episode
    from langgraph.store.memory import InMemoryStore

    store = InMemoryStore()
    upsert_episode(
        store,
        "u_plan",
        "trip_abc",
        {"text": "Da Nang slow beach trip", "city": "Da Nang", "outcome": "approved"},
    )
    graph = _build_planner_graph(store)

    result = graph.invoke(
        {
            "messages": [HumanMessage(content="Plan me a beach trip")],
            "user_id": "u_plan",
        },
        {"configurable": {"thread_id": "t_plan"}},
    )
    # The tool call was executed and its result is in the messages.
    messages = result["messages"]
    tool_msgs = [m for m in messages if m.__class__.__name__ == "ToolMessage"]
    assert any("Da Nang slow beach trip" in str(m.content) for m in tool_msgs)


def test_planner_empty_user_no_episode():
    """A user with no episodes: recall returns [] and the planner proceeds."""
    from langgraph.store.memory import InMemoryStore

    store = InMemoryStore()
    graph = _build_planner_graph(store)

    result = graph.invoke(
        {
            "messages": [HumanMessage(content="Plan me a trip")],
            "user_id": "u_empty_plan",
        },
        {"configurable": {"thread_id": "t_empty_plan"}},
    )
    messages = result["messages"]
    tool_msgs = [m for m in messages if m.__class__.__name__ == "ToolMessage"]
    # The recall tool was still called (planner prompt instructs it), but returned
    # an empty list (serialized as "[]" or similar empty representation).
    assert tool_msgs, "expected at least one ToolMessage from the recall call"
    assert any("[]" in str(m.content) or m.content == "[]" for m in tool_msgs), (
        f"expected an empty-list tool result, got: {[str(m.content) for m in tool_msgs]}"
    )


def _build_tool_spy_subagent():
    """Build a planner subagent whose bound tool names are captured.

    Returns ``(subgraph, bind_calls, restore)`` where ``restore`` resets the
    patched ``bind_tools`` (call it in a ``finally``).
    """
    from app.agents.subagents._base import build_subagent
    from app.clients.llm import FakeLLM
    from app.prompts.registry import registry
    from app.tools.registry import get_tools_for

    bind_calls: list[list[str]] = []
    _orig_bind = FakeLLM.bind_tools

    def capturing_bind(self, tools, **kwargs):
        bind_calls.append([t.name for t in tools])
        return _orig_bind(self, tools, **kwargs)

    FakeLLM.bind_tools = capturing_bind
    fake = FakeLLM(responses=["answer"])
    subgraph = build_subagent(
        "test_episodic",
        get_tools_for("planner"),
        lambda _: fake,
        registry.get("planner"),
    )

    def restore():
        FakeLLM.bind_tools = _orig_bind

    return subgraph, bind_calls, restore


def test_allow_episodic_false_strips_recall_tool():
    """When allow_episodic=False, recall_past_trips is filtered from the planner's tools."""
    from app.agents.context import AgentContext

    subgraph, bind_calls, restore = _build_tool_spy_subagent()
    try:
        state = {"messages": [HumanMessage(content="hi")]}
        subgraph.invoke(state, context=AgentContext(allow_episodic=False))
        assert bind_calls, "bind_tools was never called"
        assert "recall_past_trips" not in bind_calls[-1], (
            f"recall_past_trips was not filtered out: {bind_calls[-1]}"
        )
    finally:
        restore()


def test_allow_episodic_true_keeps_recall_tool():
    """When allow_episodic=True (default), recall_past_trips IS bound to the planner."""
    from app.agents.context import AgentContext

    subgraph, bind_calls, restore = _build_tool_spy_subagent()
    try:
        state = {"messages": [HumanMessage(content="hi")]}
        subgraph.invoke(state, context=AgentContext(allow_episodic=True))
        assert bind_calls, "bind_tools was never called"
        assert "recall_past_trips" in bind_calls[-1]
    finally:
        restore()
