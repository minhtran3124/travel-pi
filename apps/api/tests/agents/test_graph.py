"""End-to-end agent graph (specs/travel-agent Task 5.4)."""

from langchain_core.messages import HumanMessage


def _build(intent_target="concierge", answer="here you go", verdict="OK"):
    from app.agents.graph import build_graph
    from app.agents.supervisor import SupervisorIntent
    from app.clients.llm import FakeLLM
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.store.memory import InMemoryStore

    # main llm: supervisor (structured) + sub-agent answer (responses)
    main = FakeLLM(
        structured_responses=[SupervisorIntent(target_agent=intent_target)] * 4,
        responses=[answer] * 4,
    )
    # fast llm: would handle summarize (not triggered here)
    fast = FakeLLM(responses=[verdict] * 4)
    graph = build_graph(
        llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=InMemoryStore()
    )
    return graph


def test_graph_compiles_and_routes_to_subagent():
    graph = _build(intent_target="concierge", answer="visit Senso-ji")
    cfg = {"configurable": {"thread_id": "u1_t1"}}
    out = graph.invoke(
        {
            "messages": [HumanMessage(content="what to see in Tokyo?")],
            "user_id": "u1",
            "trip_id": None,
        },
        cfg,
    )
    assert out["current_flow"] == "concierge"
    assert any("Senso-ji" in (m.content or "") for m in out["messages"])


def test_graph_persists_across_turns():
    graph = _build(intent_target="concierge", answer="answer")
    cfg = {"configurable": {"thread_id": "u1_t2"}}
    first = graph.invoke(
        {"messages": [HumanMessage(content="hi")], "user_id": "u1", "trip_id": None},
        cfg,
    )
    n_after_first = len(first["messages"])
    second = graph.invoke({"messages": [HumanMessage(content="again")]}, cfg)
    # history accumulated across the two turns (checkpointer resumed the thread)
    assert len(second["messages"]) > n_after_first


def test_graph_has_no_reflection_node():
    """#112: the reflection node is gone from the compiled topology.

    Guards against it creeping back via an import or a stray add_node — the
    node name must not appear in the compiled graph at all.
    """
    graph = _build()
    assert "reflection" not in graph.get_graph().nodes


def test_normal_turn_makes_no_fast_llm_call():
    """#112: a plain sub-agent turn costs exactly one LLM round per node it needs.

    Reflection was the only per-turn consumer of the fast model on a short
    conversation (summarize skips its call while the history is short), so the
    fast LLM must now go untouched. Asserted on the call count rather than on
    node names so the guarantee survives a topology rename.
    """
    from app.agents.graph import build_graph
    from app.agents.supervisor import SupervisorIntent
    from app.clients.llm import FakeLLM
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.store.memory import InMemoryStore

    calls: list[int] = []

    class CountingFake(FakeLLM):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            calls.append(1)
            return super()._generate(
                messages, stop=stop, run_manager=run_manager, **kwargs
            )

    main = FakeLLM(
        structured_responses=[SupervisorIntent(target_agent="concierge")] * 4,
        responses=["here you go"] * 4,
    )
    fast = CountingFake(responses=["OK"] * 4)
    graph = build_graph(
        llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=InMemoryStore()
    )
    graph.invoke(
        {
            "messages": [HumanMessage(content="what to see in Tokyo?")],
            "user_id": "u1",
            "trip_id": None,
        },
        {"configurable": {"thread_id": "u1-no-fast"}},
    )
    assert calls == [], f"fast LLM was invoked {len(calls)} time(s) on a normal turn"
