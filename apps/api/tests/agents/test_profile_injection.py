"""MIN-53 — personalization profile injection into the sub-agent system prompt."""

from langchain_core.messages import HumanMessage, SystemMessage


def _capturing_graph(store):
    from app.agents.graph import build_graph
    from app.agents.supervisor import SupervisorIntent
    from app.clients.llm import FakeLLM
    from langgraph.checkpoint.memory import MemorySaver

    captured: dict = {}

    class CapturingFakeLLM(FakeLLM):
        def _generate(self, messages, *args, **kwargs):
            captured["messages"] = messages
            return super()._generate(messages, *args, **kwargs)

    main = CapturingFakeLLM(
        structured_responses=[SupervisorIntent(target_agent="concierge")] * 4,
        responses=["Here are some options"] * 4,
    )
    fast = FakeLLM(responses=["OK"])
    graph = build_graph(
        llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=store
    )
    return graph, captured


def _system_content(captured):
    system_msgs = [m for m in captured["messages"] if isinstance(m, SystemMessage)]
    assert len(system_msgs) == 1, "expected exactly one leading SystemMessage"
    return system_msgs[0].content


def test_profile_reaches_system_prompt():
    from app.memory.store import get_store, upsert_preference

    store = get_store("sqlite:///:memory:")
    upsert_preference(store, "u_prof", "name", {"text": "Minh"})
    upsert_preference(
        store, "u_prof", "travel_group", {"text": "family with young children"}
    )

    graph, captured = _capturing_graph(store)
    graph.invoke(
        {"messages": [HumanMessage(content="hotels in Da Nang?")], "user_id": "u_prof"},
        {"configurable": {"thread_id": "t_prof"}},
    )
    content = _system_content(captured)
    assert "Traveller profile:" in content
    assert "Minh" in content
    assert "family with young children" in content


def test_no_profile_block_for_empty_user():
    from langgraph.store.memory import InMemoryStore

    graph, captured = _capturing_graph(InMemoryStore())
    graph.invoke(
        {"messages": [HumanMessage(content="hi")], "user_id": "u_empty_prof"},
        {"configurable": {"thread_id": "t_empty_prof"}},
    )
    assert "Traveller profile:" not in _system_content(captured)
