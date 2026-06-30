"""Task 2.1 — Background memory extraction node (specs/agent-memory-layers)."""

from langchain_core.messages import AIMessage, HumanMessage

from app.agents.context import AgentContext
from app.enums import ChatMode, Tier


def _build_memory_graph(
    *,
    extractor_json: str = '{"preferences": [], "instructions": []}',
):
    """Build a graph with FakeLLMs and InMemoryStore for extraction tests."""
    from app.agents.graph import build_graph
    from app.agents.supervisor import SupervisorIntent
    from app.clients.llm import FakeLLM
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.store.memory import InMemoryStore

    main = FakeLLM(
        structured_responses=[SupervisorIntent(target_agent="journal")] * 4,
        responses=["All noted!"] * 4,
    )
    # fast LLM: journal tool-call + answer + reflection OK + extractor JSON
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
            AIMessage(content="Preference saved."),
            "OK",  # reflection verdict
            extractor_json,  # extractor output
        ]
    )
    store = InMemoryStore()
    graph = build_graph(
        llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=store
    )
    return graph, store


def test_extract_memory_writes_prefs_to_store():
    """A non-FAST turn writes extracted preferences to the store."""
    json_str = (
        '{"preferences": [{"key": "airline", "text": "prefers ANA"}],'
        '"instructions": []}'
    )
    graph, store = _build_memory_graph(extractor_json=json_str)
    from app.memory.store import search_preferences

    graph.invoke(
        {
            "messages": [HumanMessage(content="I like ANA")],
            "user_id": "u42",
        },
        {"configurable": {"thread_id": "t42"}},
    )
    prefs = search_preferences(store, "u42")
    assert any(p["text"] == "prefers ANA" for p in prefs)


def test_extract_memory_writes_instructions_to_store():
    """A non-FAST turn writes extracted instructions to the store."""
    json_str = (
        '{"preferences": [],'
        '"instructions": [{"key": "currency", "text": "always EUR"}]}'
    )
    graph, store = _build_memory_graph(extractor_json=json_str)
    from app.memory.store import get_instructions

    graph.invoke(
        {
            "messages": [HumanMessage(content="Show me prices in EUR")],
            "user_id": "u43",
        },
        {"configurable": {"thread_id": "t43"}},
    )
    instrs = get_instructions(store, "u43")
    assert any(i["text"] == "always EUR" for i in instrs)


def test_extract_memory_writes_both_prefs_and_instructions():
    """Both preferences and instructions are persisted in one turn."""
    json_str = (
        '{"preferences": [{"key": "diet", "text": "vegetarian"}],'
        '"instructions": [{"key": "style", "text": "keep short"}]}'
    )
    graph, store = _build_memory_graph(extractor_json=json_str)
    from app.memory.store import get_instructions, search_preferences

    graph.invoke(
        {
            "messages": [HumanMessage(content="I'm vegetarian, keep replies short")],
            "user_id": "u44",
        },
        {"configurable": {"thread_id": "t44"}},
    )
    prefs = search_preferences(store, "u44")
    instrs = get_instructions(store, "u44")
    assert any(p["text"] == "vegetarian" for p in prefs)
    assert any(i["text"] == "keep short" for i in instrs)


def test_fast_mode_writes_nothing():
    """When allow_memory_write=False (FAST mode), nothing is written."""
    from app.memory.store import get_instructions, search_preferences

    # Build graph fresh with FAST context — the extractor should skip entirely.
    from app.agents.graph import build_graph
    from app.agents.supervisor import SupervisorIntent
    from app.clients.llm import FakeLLM
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.store.memory import InMemoryStore

    main = FakeLLM(
        structured_responses=[SupervisorIntent(target_agent="concierge")] * 4,
        responses=["Concierge answer."] * 4,
    )
    # FAST mode: reflection capped at 0, so no revision, then extractor skips.
    # But reflection still calls the LLM once for verdict (which is "OK" →
    # routes to extract_memory, then extract_memory checks allow_memory_write
    # and returns {} without calling the LLM).
    fast = FakeLLM(responses=["OK"] * 10)  # enough for any calls
    store = InMemoryStore()
    graph = build_graph(
        llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=store
    )

    ctx = AgentContext(
        tier=Tier.FREE, mode=ChatMode.FAST, allow_memory_write=False
    )
    graph.invoke(
        {
            "messages": [HumanMessage(content="I'm vegetarian")],
            "user_id": "u_fast",
        },
        {
            "configurable": {"thread_id": "t_fast"},
            "context": ctx,
        },
    )
    assert search_preferences(store, "u_fast") == []
    assert get_instructions(store, "u_fast") == []


def test_extract_memory_empty_json_writes_nothing():
    """Empty arrays in extractor output → nothing persisted."""
    from app.agents.graph import build_graph
    from app.agents.supervisor import SupervisorIntent
    from app.clients.llm import FakeLLM
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.store.memory import InMemoryStore
    from app.memory.store import get_instructions, search_preferences

    # Route to concierge (no save_user_preference tool) so only the extractor
    # could write anything — and it won't with empty JSON.
    main = FakeLLM(
        structured_responses=[SupervisorIntent(target_agent="concierge")] * 4,
        responses=["Concierge answer."] * 4,
    )
    fast = FakeLLM(
        responses=[
            "OK",  # reflection
            '{"preferences": [], "instructions": []}',  # extractor
        ]
    )
    store = InMemoryStore()
    graph = build_graph(
        llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=store
    )

    graph.invoke(
        {
            "messages": [HumanMessage(content="What time is it?")],
            "user_id": "u45",
        },
        {"configurable": {"thread_id": "t45"}},
    )
    assert search_preferences(store, "u45") == []
    assert get_instructions(store, "u45") == []
