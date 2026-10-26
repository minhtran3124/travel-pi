"""LangGraphRunner AgentRunner adapter (agent-eval-pipeline task 2.1).

FakeLLM-only, no network. `agent_db` (from `tests/tools/conftest.py`) is an
isolated temp SQLite DB — required for the real `browse_hotels` tool call,
not an external dependency.
"""

from app.agents.context import AgentContext
from app.agents.supervisor import SupervisorIntent
from app.agents.tool_output import wrap_tool_output
from app.clients.llm import FakeLLM
from app.core.text import escape_angle_brackets
from eval.adapters.langgraph_runner import (
    LangGraphRunner,
    _final_reply,
    _pair_tool_calls,
    _serialize_message,
)
from evalkit.types import Golden
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from tests.tools.conftest import (
    agent_db,  # noqa: F401 — fixture not visible cross-package
)


def _golden(**overrides):
    defaults = {
        "id": "g-1",
        "capability": "hotels",
        "scenario": "happy",
        "language": "en",
        "suite": "smoke",
        "input": "hi",
        "turns": None,
        "expected_flow": None,
        "expected_tools": None,
        "expected_tasks": None,
        "hitl": None,
        "expected_trajectory": None,
        "oracle_checks": None,
        "metrics": None,
        "notes": None,
    }
    defaults.update(overrides)
    return Golden(**defaults)


def _build_runner(target="concierge", answer="here you go", verdict="OK"):
    main = FakeLLM(
        structured_responses=[SupervisorIntent(target_agent=target)] * 4,
        responses=[answer] * 4,
    )
    fast = FakeLLM(responses=[verdict] * 4)
    return LangGraphRunner(llm=main, fast_llm=fast)


# --- unit tests for the pure serialization/pairing helpers -----------------


def test_pair_tool_calls_matches_by_id_not_position():
    ai = AIMessage(
        content="",
        tool_calls=[
            {"name": "tool_a", "args": {"x": 1}, "id": "a"},
            {"name": "tool_b", "args": {"x": 2}, "id": "b"},
        ],
    )
    # Results arrive out of order relative to the tool_calls list.
    tool_b_result = ToolMessage(content="result-b", tool_call_id="b", name="tool_b")
    tool_a_result = ToolMessage(content="result-a", tool_call_id="a", name="tool_a")

    calls = _pair_tool_calls([ai, tool_b_result, tool_a_result])

    by_name = {c.name: c for c in calls}
    assert by_name["tool_a"].output == "result-a"
    assert by_name["tool_a"].args == {"x": 1}
    assert by_name["tool_b"].output == "result-b"


def test_pair_tool_calls_strips_wrapper_but_keeps_escaping():
    # A tool result the subagent hook wrapped must reach EvalToolCall.output with
    # NO wrapper text, so the judge's retrieval context matches the pre-hook text.
    raw = "Great stay <b>near</b> the beach"
    wrapped = wrap_tool_output("browse_hotels", raw)
    ai = AIMessage(
        content="",
        tool_calls=[{"name": "browse_hotels", "args": {}, "id": "h1"}],
    )
    tool_result = ToolMessage(content=wrapped, tool_call_id="h1", name="browse_hotels")

    calls = _pair_tool_calls([ai, tool_result])

    output = calls[0].output
    assert "<tool_output" not in output
    assert "</tool_output>" not in output
    # Unwrapped, but NOT unescaped (D7): re-importing a literal `<` would re-open
    # tag forgery in the judge's retrieval context.
    assert output == escape_angle_brackets(raw)
    assert "&lt;b&gt;" in output


def test_pair_tool_calls_output_byte_identical_when_no_angle_brackets():
    # The load-bearing baseline assertion: for content with no angle brackets,
    # escaping was a no-op, so stripping the wrapper yields a value byte-identical
    # to the pre-change output — this is what keeps eval/baselines/main.json
    # comparable.
    inner = "Here are some hotels in Da Nang. Prices from $80/night."
    wrapped = wrap_tool_output("browse_hotels", inner)
    ai = AIMessage(
        content="",
        tool_calls=[{"name": "browse_hotels", "args": {}, "id": "h1"}],
    )
    tool_result = ToolMessage(content=wrapped, tool_call_id="h1", name="browse_hotels")

    calls = _pair_tool_calls([ai, tool_result])

    assert calls[0].output == inner


def test_pair_tool_calls_passes_block_list_content_through():
    # ToolMessage.content can be a provider block list; strip_wrappers' regex over
    # a list raises TypeError, so non-str content must pass through untouched
    # (mirrors the hook's own str-only type guard).
    blocks = [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]
    ai = AIMessage(
        content="",
        tool_calls=[{"name": "t", "args": {}, "id": "x"}],
    )
    tool_result = ToolMessage(content=blocks, tool_call_id="x", name="t")

    calls = _pair_tool_calls([ai, tool_result])

    assert calls[0].output == blocks


def test_serialize_message_shapes():
    ai = AIMessage(
        content="thinking",
        tool_calls=[{"name": "tool_a", "args": {"x": 1}, "id": "a"}],
    )
    tool_msg = ToolMessage(content="the answer", tool_call_id="a", name="tool_a")
    human = HumanMessage(content="hello")

    d_ai = _serialize_message(ai)
    d_tool = _serialize_message(tool_msg)
    d_human = _serialize_message(human)

    assert d_ai["type"] == "ai"
    assert d_ai["tool_calls"][0]["name"] == "tool_a"
    assert d_tool["type"] == "tool"
    assert d_tool["tool_call_id"] == "a"
    assert d_tool["name"] == "tool_a"
    assert d_tool["content"] == "the answer"
    assert d_human == {"type": "human", "content": "hello"}


def test_final_reply_flattens_block_list_content():
    assert _final_reply([]) == ""
    assert _final_reply([AIMessage(content="plain")]) == "plain"
    out = _final_reply(
        [
            AIMessage(
                content=[
                    {"type": "text", "text": "hi"},
                    {"type": "text", "text": " there"},
                ]
            )
        ]
    )
    assert out == "hi there"


# --- LangGraphRunner.run() integration tests (FakeLLM-backed graph) --------


def test_run_returns_populated_trace():
    runner = _build_runner(target="concierge", answer="Senso-ji is worth a visit")
    trace = runner.run(_golden(input="what to see in Tokyo?"))

    assert "Senso-ji" in trace.reply
    assert trace.flow == "concierge"
    assert trace.messages, "ordered message list must be populated"
    assert trace.messages[0]["type"] == "human"
    assert trace.meta["thread_id"]
    assert trace.meta["model"] == "FakeLLM"
    assert trace.meta["n_turns"] == 1


def test_run_captures_tool_call_output(agent_db):
    main = FakeLLM(
        structured_responses=[SupervisorIntent(target_agent="concierge")],
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "browse_hotels",
                        "args": {"city": "Da Nang", "max_price": 200},
                        "id": "h1",
                    }
                ],
            ),
            "Here are some hotels in Da Nang.",
        ],
    )
    fast = FakeLLM(responses=["OK"])
    runner = LangGraphRunner(llm=main, fast_llm=fast)

    trace = runner.run(
        _golden(id="hotels-browse-1", input="find me a hotel in Da Nang")
    )

    assert trace.reply
    assert trace.flow == "concierge"
    browse = next(tc for tc in trace.tool_calls if tc.name == "browse_hotels")
    assert browse.args == {"city": "Da Nang", "max_price": 200}
    assert browse.output, "ToolMessage content must be captured as the tool output"
    assert any(m.get("type") == "tool" for m in trace.messages)


def test_run_multi_turn_replays_on_one_thread():
    runner = _build_runner(target="concierge", answer="ok noted")
    trace = runner.run(
        _golden(id="multi-1", input=None, turns=["first turn", "second turn"])
    )

    assert trace.meta["n_turns"] == 2
    human_contents = [m["content"] for m in trace.messages if m["type"] == "human"]
    assert human_contents == ["first turn", "second turn"], (
        "both turns must appear in order on the same accumulated thread"
    )


def test_run_uses_unique_thread_id_per_golden_no_state_bleed():
    runner = _build_runner(target="concierge", answer="ok")
    trace_1 = runner.run(_golden(id="case-1", input="only in case one"))
    trace_2 = runner.run(_golden(id="case-2", input="only in case two"))

    assert trace_1.meta["thread_id"] != trace_2.meta["thread_id"]
    contents_2 = [m["content"] for m in trace_2.messages]
    assert "only in case one" not in contents_2, "no cross-golden state bleed"


def test_run_accepts_injected_context():
    main = FakeLLM(
        structured_responses=[SupervisorIntent(target_agent="concierge")] * 2,
        responses=["answer"] * 2,
    )
    fast = FakeLLM(responses=["OK"] * 2)
    runner = LangGraphRunner(
        llm=main, fast_llm=fast, context=AgentContext(timezone="Asia/Ho_Chi_Minh")
    )
    trace = runner.run(_golden())
    assert trace.reply == "answer"


def test_run_meta_records_tasks_and_suggestions(agent_db):
    # A multi-intent turn (target + one independent follow-on) dispatches two
    # parallel synthesis workers and ends at the "synthesize" flow — not a
    # key in suggestions.py's static per-flow map, so `suggestions` legitimately
    # comes back empty here without trip_facts/profile/preferences context to
    # trigger a D6 rule (see test_run_meta_single_intent_has_one_task below for
    # the non-empty case). `tasks` still reflects both dispatched agents.
    main = FakeLLM(
        structured_responses=[
            SupervisorIntent(target_agent="budget", plan=["concierge"])
        ],
        responses=["budget findings", "concierge findings", "combined answer"],
    )
    fast = FakeLLM(responses=["OK"])
    runner = LangGraphRunner(llm=main, fast_llm=fast)

    trace = runner.run(
        _golden(id="multi-intent-1", input="plan my trip: budget and local tips")
    )

    assert trace.meta["tasks"] == ["budget", "concierge"]
    assert isinstance(trace.meta["suggestions"], list)
    assert all(isinstance(s, str) for s in trace.meta["suggestions"])


def test_run_meta_single_intent_has_one_task(agent_db):
    runner = _build_runner(target="concierge", answer="here you go")
    trace = runner.run(_golden(id="single-intent-1", input="find me a hotel"))

    assert trace.meta["tasks"] == ["concierge"]
    assert trace.meta["suggestions"], "known flow must yield non-empty suggestions"
    assert all(isinstance(s, str) for s in trace.meta["suggestions"])


# --- HITL plan-approval resume (task 1.2) -----------------------------------


def test_booking_interrupt_is_recorded_without_hitl():
    runner = _build_runner(target="booking", answer="Hotel booked!")
    golden = _golden(id="hitl-1", input="book me a hotel in Paris")

    trace = runner.run(golden)

    assert trace.reply == ""
    assert trace.meta["interrupts"] == [
        {"type": "plan_approval", "draft": golden.input, "turn": 0}
    ]


def test_hitl_approve_resumes_and_captures_reply():
    runner = _build_runner(target="booking", answer="Hotel booked!")
    golden = _golden(id="hitl-2", input="book me a hotel in Paris", hitl="approve")

    trace = runner.run(golden)

    assert "Hotel booked" in trace.reply
    assert trace.meta["interrupts"] == [
        {"type": "plan_approval", "draft": golden.input, "turn": 0}
    ]


def test_hitl_reject_captures_cancellation():
    runner = _build_runner(target="booking", answer="Hotel booked!")
    golden = _golden(id="hitl-3", input="book me a hotel in Paris", hitl="reject")

    trace = runner.run(golden)

    assert "cancelled" in trace.reply.lower()
    assert "Hotel booked" not in trace.reply
