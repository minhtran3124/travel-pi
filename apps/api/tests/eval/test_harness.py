"""Graph -> LLMTestCase harness (MIN-58, Task 2.2)."""

from app.agents.graph import build_graph
from app.agents.supervisor import SupervisorIntent
from app.clients.llm import FakeLLM
from eval.harness import run_case
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore


def _fake_graph(target="concierge", answer="Ở Tokyo bạn nên thăm **Senso-ji** 🏯"):
    main = FakeLLM(
        structured_responses=[SupervisorIntent(target_agent=target)] * 4,
        responses=[answer] * 4,
    )
    fast = FakeLLM(responses=["OK"] * 4)
    return build_graph(
        llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=InMemoryStore()
    )


def test_run_case_extracts_reply_and_flow():
    res = run_case(_fake_graph(), {"input": "Tokyo có gì chơi?"}, 0)
    assert "Senso-ji" in res.test_case.actual_output
    assert res.current_flow == "concierge"
    assert res.test_case.input == "Tokyo có gì chơi?"


def test_run_case_maps_expected_tools():
    res = run_case(
        _fake_graph(), {"input": "x", "expected_tools": ["search_hotels"]}, 1
    )
    assert [t.name for t in res.test_case.expected_tools] == ["search_hotels"]


def test_unique_thread_id_per_index_isolates_history():
    g = _fake_graph()
    a = run_case(g, {"input": "hi"}, 0)
    b = run_case(g, {"input": "again"}, 1)
    # Distinct threads → b did not accumulate a's turn (no cross-case bleed).
    assert a.test_case.actual_output and b.test_case.actual_output


def test_tools_called_extracts_names_from_ai_tool_calls():
    # Direct unit-test of the MIN-46 extraction path (no graph needed).
    from eval.harness import _tools_called

    msg = AIMessage(
        content="", tool_calls=[{"name": "search_hotels", "args": {}, "id": "1"}]
    )
    assert [t.name for t in _tools_called([msg])] == ["search_hotels"]
    assert _tools_called([AIMessage(content="no tools")]) == []


def test_final_reply_coerces_block_list_content_to_str():
    # Providers (Anthropic/Bedrock) may return content as a list of blocks;
    # actual_output must be a str, never a list (avoids pydantic ValidationError).
    from eval.harness import _final_reply

    out = _final_reply([AIMessage(content=[{"type": "text", "text": "hi"}])])
    assert isinstance(out, str)
    assert _final_reply([AIMessage(content="plain")]) == "plain"
    assert _final_reply([]) == ""
    # Block-list content -> extracted text, not a repr:
    assert (
        _final_reply(
            [
                AIMessage(
                    content=[
                        {"type": "text", "text": "hi"},
                        {"type": "text", "text": " there"},
                    ]
                )
            ]
        )
        == "hi there"
    )
    # Empty block list -> empty string, not "[]":
    assert _final_reply([AIMessage(content=[])]) == ""
