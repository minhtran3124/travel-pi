"""Long-term store + summarizer (specs/travel-agent Task 2.2)."""

from langchain_core.messages import AIMessage, HumanMessage


def test_store_falls_back_to_in_memory():
    from app.memory.store import get_store
    from langgraph.store.memory import InMemoryStore

    assert isinstance(get_store("sqlite:///:memory:"), InMemoryStore)


def test_upsert_and_search_preferences():
    from app.memory.store import get_store, search_preferences, upsert_preference

    store = get_store("sqlite:///:memory:")
    upsert_preference(store, "u1", "diet", {"text": "vegetarian"})
    upsert_preference(store, "u1", "airline", {"text": "prefers ANA"})
    # another user is isolated
    upsert_preference(store, "u2", "diet", {"text": "halal"})

    prefs = search_preferences(store, "u1")
    texts = {p["text"] for p in prefs}
    assert texts == {"vegetarian", "prefers ANA"}
    assert [p["text"] for p in search_preferences(store, "u2")] == ["halal"]


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
    # keeps the last 4, removes the rest (12 of 16)
    assert len(to_remove) == len(msgs) - 4
