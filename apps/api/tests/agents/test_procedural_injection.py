"""Task 2.1 — Procedural instruction injection (specs/agent-memory-layers)."""

from langchain_core.messages import HumanMessage, SystemMessage


def test_instructions_reach_system_prompt():
    """Seed an instruction in store → it appears in the sub-agent's system prompt."""
    from app.agents.graph import build_graph
    from app.agents.supervisor import SupervisorIntent
    from app.clients.llm import FakeLLM
    from app.memory.store import get_store, upsert_instruction
    from langgraph.checkpoint.memory import MemorySaver

    store = get_store("sqlite:///:memory:")
    upsert_instruction(store, "u_inst", "price_display", {"text": "always show EUR"})

    # Capture the messages the sub-agent LLM receives.
    captured: dict = {}

    class CapturingFakeLLM(FakeLLM):
        def _generate(self, messages, *args, **kwargs):
            captured["messages"] = messages
            return super()._generate(messages, *args, **kwargs)

    main = CapturingFakeLLM(
        structured_responses=[SupervisorIntent(target_agent="concierge")] * 4,
        responses=["Concierge says hello"] * 4,
    )
    # fast: journal, budget, summarize won't be triggered for the concierge
    # route; only reflection uses fast here (memory extraction now runs as a
    # post-response background task, not as an in-graph node).
    fast = FakeLLM(
        responses=[
            "OK",  # reflection verdict
        ]
    )
    graph = build_graph(
        llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=store
    )

    graph.invoke(
        {
            "messages": [HumanMessage(content="What's the weather?")],
            "user_id": "u_inst",
        },
        {"configurable": {"thread_id": "t_inst"}},
    )

    # The sub-agent (concierge) should have received a system message
    # containing the seed instruction.
    msgs = captured["messages"]
    system_msgs = [m for m in msgs if isinstance(m, SystemMessage)]
    assert len(system_msgs) == 1, "expected exactly one leading SystemMessage"
    content = system_msgs[0].content
    assert "Standing traveller instructions" in content
    assert "always show EUR" in content


def test_no_instructions_for_empty_user():
    """User with no stored instructions → system prompt unchanged."""
    from app.agents.graph import build_graph
    from app.agents.supervisor import SupervisorIntent
    from app.clients.llm import FakeLLM
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.store.memory import InMemoryStore

    captured: dict = {}

    class CapturingFakeLLM(FakeLLM):
        def _generate(self, messages, *args, **kwargs):
            captured["messages"] = messages
            return super()._generate(messages, *args, **kwargs)

    main = CapturingFakeLLM(
        structured_responses=[SupervisorIntent(target_agent="concierge")] * 4,
        responses=["Answer"] * 4,
    )
    fast = FakeLLM(
        responses=[
            "OK",
            '{"preferences": [], "instructions": []}',
        ]
    )
    graph = build_graph(
        llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=InMemoryStore()
    )

    graph.invoke(
        {
            "messages": [HumanMessage(content="hello")],
            "user_id": "u_empty",
        },
        {"configurable": {"thread_id": "t_empty"}},
    )

    msgs = captured["messages"]
    system_msgs = [m for m in msgs if isinstance(m, SystemMessage)]
    assert len(system_msgs) == 1
    # No "Standing traveller instructions" block for an empty user.
    assert "Standing traveller instructions" not in system_msgs[0].content


def test_multiple_instructions_reach_system_prompt():
    """Multiple instructions are concatenated in the system prompt."""
    from app.agents.graph import build_graph
    from app.agents.supervisor import SupervisorIntent
    from app.clients.llm import FakeLLM
    from app.memory.store import get_store, upsert_instruction
    from langgraph.checkpoint.memory import MemorySaver

    store = get_store("sqlite:///:memory:")
    upsert_instruction(store, "u_multi", "price_display", {"text": "always show EUR"})
    upsert_instruction(store, "u_multi", "address_as", {"text": "address as Captain"})

    captured: dict = {}

    class CapturingFakeLLM(FakeLLM):
        def _generate(self, messages, *args, **kwargs):
            captured["messages"] = messages
            return super()._generate(messages, *args, **kwargs)

    main = CapturingFakeLLM(
        structured_responses=[SupervisorIntent(target_agent="concierge")] * 4,
        responses=["Sure thing, Captain!"] * 4,
    )
    fast = FakeLLM(
        responses=[
            "OK",
            '{"preferences": [], "instructions": []}',
        ]
    )
    graph = build_graph(
        llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=store
    )

    graph.invoke(
        {
            "messages": [HumanMessage(content="hello")],
            "user_id": "u_multi",
        },
        {"configurable": {"thread_id": "t_multi"}},
    )

    msgs = captured["messages"]
    system_msgs = [m for m in msgs if isinstance(m, SystemMessage)]
    content = system_msgs[0].content
    assert "always show EUR" in content
    assert "address as Captain" in content
