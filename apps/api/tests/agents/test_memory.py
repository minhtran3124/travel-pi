"""Long-term store + summarizer."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


def test_summarize_conversation_keeps_tool_call_pairs_intact():
    """A naive messages[:-keep_last] slice can orphan a ToolMessage whose parent AIMessage(tool_calls=...) falls just before the cut, which the provider rejects."""
    from app.clients.llm import FakeLLM
    from app.memory.summarizer import summarize_conversation

    msgs = [
        HumanMessage(content="q0", id="h0"),
        AIMessage(
            content="",
            id="a0",
            tool_calls=[
                {"name": "search_places", "args": {}, "id": "c1"},
                {"name": "get_weather", "args": {}, "id": "c2"},
            ],
        ),
        ToolMessage(content="places found", id="t0", tool_call_id="c1"),
        ToolMessage(content="sunny", id="t1", tool_call_id="c2"),
        AIMessage(content="Here you go", id="a1"),
        HumanMessage(content="q1", id="h1"),
    ]

    llm = FakeLLM(responses=["SUMMARY: ..."])
    # a0 must survive whenever either of its ToolMessages does.
    _, to_remove = summarize_conversation(msgs, llm, keep_last=3)

    removed_ids = {rm.id for rm in to_remove}
    assert "a0" not in removed_ids
    assert "t0" not in removed_ids
    assert "t1" not in removed_ids
    assert removed_ids == {"h0"}


def test_store_falls_back_to_in_memory():
    from app.memory.store import get_store
    from langgraph.store.memory import InMemoryStore

    assert isinstance(get_store("sqlite:///:memory:"), InMemoryStore)


def test_upsert_and_search_preferences():
    from app.memory.store import get_store, search_preferences, upsert_preference

    store = get_store("sqlite:///:memory:")
    upsert_preference(store, "u1", "diet", {"text": "vegetarian"})
    upsert_preference(store, "u1", "airline", {"text": "prefers ANA"})
    upsert_preference(store, "u2", "diet", {"text": "halal"})

    prefs = search_preferences(store, "u1")
    texts = {p["text"] for p in prefs}
    assert texts == {"vegetarian", "prefers ANA"}
    assert [p["text"] for p in search_preferences(store, "u2")] == ["halal"]


def test_search_with_query_uses_index_and_stays_isolated():
    """A `query` search runs against the semantic index and stays namespace-isolated per user."""
    from app.memory.store import get_store, search_preferences, upsert_preference

    store = get_store("sqlite:///:memory:")
    upsert_preference(store, "u1", "diet", {"text": "vegetarian, no pork"})
    upsert_preference(store, "u1", "airline", {"text": "prefers ANA window seat"})
    upsert_preference(store, "u2", "diet", {"text": "halal"})

    u1_hits = {p["text"] for p in search_preferences(store, "u1", query="food choices")}
    assert u1_hits == {"vegetarian, no pork", "prefers ANA window seat"}
    u2_hits = [p["text"] for p in search_preferences(store, "u2", query="food choices")]
    assert u2_hits == ["halal"]


def test_user_id_injected_from_graph_state_not_model():
    """save_user_preference writes under state['user_id'], never a model-supplied id."""
    from app.agents.graph import build_graph
    from app.agents.supervisor import SupervisorIntent
    from app.clients.llm import FakeLLM
    from app.memory.store import get_store, search_preferences
    from langgraph.checkpoint.memory import MemorySaver

    store = get_store("sqlite:///:memory:")
    # Journal sub-agent runs on the fast LLM, so its tool-call + answer are scripted there.
    main = FakeLLM(structured_responses=[SupervisorIntent(target_agent="journal")])
    fast = FakeLLM(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "save_user_preference",
                        "args": {"key": "diet", "text": "vegetarian"},
                        "id": "c1",
                    }
                ],
            ),
            AIMessage(content="Saved."),
            "OK",
        ]
    )
    graph = build_graph(
        llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=store
    )
    graph.invoke(
        {
            "messages": [HumanMessage(content="remember I'm vegetarian")],
            "user_id": "u-42",
        },
        {"configurable": {"thread_id": "t-mem"}},
    )

    assert any(p["text"] == "vegetarian" for p in search_preferences(store, "u-42"))
    assert search_preferences(store, "someone-else") == []


def test_should_summarize_threshold():
    from app.memory.summarizer import should_summarize

    msgs = [HumanMessage(content="x") for _ in range(6)]
    assert should_summarize(msgs, threshold=5) is True
    assert should_summarize(msgs, threshold=10) is False


def test_summarize_conversation_uses_llm_and_trims():
    from app.clients.llm import FakeLLM
    from app.memory.summarizer import summarize_conversation

    msgs = []
    for i in range(8):
        msgs.append(HumanMessage(content=f"q{i}", id=f"h{i}"))
        msgs.append(AIMessage(content=f"a{i}", id=f"a{i}"))

    llm = FakeLLM(responses=["SUMMARY: trip to Tokyo, vegetarian, budget 2000USD"])
    summary, to_remove = summarize_conversation(msgs, llm, keep_last=4)

    assert "SUMMARY" in summary
    assert len(to_remove) == len(msgs) - 4
