"""A trailing LLM call must not be dropped behind tool spans once the cap is hit (#270).

A research run is dominated by tool/node spans; its final Haiku grader call used to
fall past MAX_STEPS_PER_TURN and never reached agent_run_steps.
"""

from uuid import uuid4

from app.agents.metrics import MAX_STEPS_PER_TURN, TurnMetricsHandler
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult


def _result(model: str) -> LLMResult:
    msg = AIMessage(
        content="x",
        response_metadata={"model_name": model},
        usage_metadata={"input_tokens": 2, "output_tokens": 1, "total_tokens": 3},
    )
    return LLMResult(generations=[[ChatGeneration(message=msg)]])


def test_late_llm_step_evicts_a_closed_tool_step_at_the_cap():
    h = TurnMetricsHandler()
    for _ in range(MAX_STEPS_PER_TURN):
        rid = uuid4()
        h.on_tool_start({"name": "t"}, "", run_id=rid, metadata={})
        h.on_tool_end("x", run_id=rid)
    rid = uuid4()
    h.on_chat_model_start(
        {}, [], run_id=rid, metadata={"ls_model_name": "claude-haiku-5-5"}
    )
    h.on_llm_end(_result("claude-haiku-5-5"), run_id=rid)

    steps = h.steps()
    assert len(steps) == MAX_STEPS_PER_TURN
    assert steps[-1]["kind"] == "llm" and steps[-1]["model"] == "claude-haiku-5-5"
    assert [s["seq"] for s in steps] == list(range(MAX_STEPS_PER_TURN))
    assert h.steps_dropped == 1
