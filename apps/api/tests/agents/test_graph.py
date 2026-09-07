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
    # fast llm: reflection verdict (+ would handle summarize, not triggered here)
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


def test_graph_redacts_user_input_before_persisting():
    graph = _build(intent_target="concierge", answer="acknowledged")
    cfg = {"configurable": {"thread_id": "u1_pii"}}
    out = graph.invoke(
        {
            "messages": [
                HumanMessage(content="my email is secret@leak.com and card 4111 1111 1111 1111")
            ],
            "user_id": "u1",
            "trip_id": None,
        },
        cfg,
    )
    human = next(m for m in out["messages"] if isinstance(m, HumanMessage))
    assert "secret@leak.com" not in human.content
    assert "4111 1111 1111 1111" not in human.content
    assert "[REDACTED_EMAIL]" in human.content
    assert "****-****-****-1111" in human.content
