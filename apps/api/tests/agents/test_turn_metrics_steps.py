"""Ordered step capture in TurnMetricsHandler (specs/agent-run-trace-detail §4.1, SC-1/SC-3)."""

from uuid import uuid4

from app.agents import metrics
from app.agents.metrics import MAX_STEPS_PER_TURN, TurnMetricsHandler
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

STEP_KEYS = {
    "seq",
    "kind",
    "node",
    "ns",
    "model",
    "input_tokens",
    "output_tokens",
    "cached_tokens",
    "offset_ms",
    "ms",
    "status",
    "error_type",
    "tool_name",
    "meta",
}


def _llm_result(
    *,
    model: str = "gpt-5-mini",
    input_tokens: int = 10,
    output_tokens: int = 4,
    cache_read: int = 3,
    finish_reason: str | None = "stop",
) -> LLMResult:
    response_metadata: dict = {"model_name": model}
    if finish_reason is not None:
        response_metadata["finish_reason"] = finish_reason
    message = AIMessage(
        content="hi",
        response_metadata=response_metadata,
        usage_metadata={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "input_token_details": {"cache_read": cache_read},
        },
    )
    return LLMResult(generations=[[ChatGeneration(message=message)]])


def test_step_dict_has_exactly_the_documented_keys():
    h = TurnMetricsHandler()
    rid = uuid4()
    h.on_chat_model_start({}, [], run_id=rid, metadata={"ls_model_name": "gpt-5"})
    h.on_llm_end(_llm_result(model="gpt-5"), run_id=rid)

    (step,) = h.steps()
    assert set(step.keys()) == STEP_KEYS


def test_seq_follows_start_order_so_a_node_precedes_its_children():
    """A node span opens before the LLM/tool runs it brackets and closes after them."""
    h = TurnMetricsHandler()
    node_id, llm_id, tool_id = uuid4(), uuid4(), uuid4()
    meta = {"langgraph_node": "concierge", "langgraph_checkpoint_ns": "concierge:t1"}

    h.on_chain_start({}, {}, run_id=node_id, metadata=meta)
    h.on_chat_model_start(
        {}, [], run_id=llm_id, metadata={**meta, "ls_model_name": "gpt-5-mini"}
    )
    h.on_llm_end(_llm_result(), run_id=llm_id)
    h.on_tool_start({"name": "search_hotels"}, "", run_id=tool_id, metadata=meta)
    h.on_tool_end("ok", run_id=tool_id)
    h.on_chain_end({}, run_id=node_id)  # closes LAST but must sort FIRST

    steps = h.steps()
    assert [s["seq"] for s in steps] == [0, 1, 2]
    assert [s["kind"] for s in steps] == ["node", "llm", "tool"]
    assert all(s["status"] == "ok" for s in steps)


def test_llm_step_takes_node_and_model_from_chat_model_start():
    h = TurnMetricsHandler()
    rid = uuid4()
    h.on_chat_model_start(
        {},
        [],
        run_id=rid,
        metadata={
            "langgraph_node": "assistant",
            "langgraph_checkpoint_ns": "planner:t1|assistant:t2",
            "ls_model_name": "gpt-5-mini",
        },
    )
    h.on_llm_end(_llm_result(model="gpt-5-mini", cache_read=3), run_id=rid)

    (step,) = h.steps()
    assert step["kind"] == "llm"
    assert step["node"] == "assistant"
    assert step["ns"] == "planner:t1|assistant:t2"
    assert step["model"] == "gpt-5-mini"
    assert (step["input_tokens"], step["output_tokens"], step["cached_tokens"]) == (
        10,
        4,
        3,
    )
    assert step["meta"] == {"finish_reason": "stop"}
    assert step["error_type"] is None


def test_llm_error_closes_the_step_with_the_exception_type_only():
    h = TurnMetricsHandler()
    rid = uuid4()
    h.on_chat_model_start({}, [], run_id=rid, metadata={"ls_model_name": "gpt-5"})
    h.on_llm_error(TimeoutError("upstream stalled"), run_id=rid)

    (step,) = h.steps()
    assert step["status"] == "error"
    assert step["error_type"] == "TimeoutError"
    assert h.snapshot()["llm_errors"] == 1


def test_tool_step_takes_node_from_its_own_metadata():
    h = TurnMetricsHandler()
    node_id, tool_id = uuid4(), uuid4()
    # the node registered in the chain map is a DIFFERENT namespace: the tool must
    # not rely on parent_run_id to resolve its node.
    h.on_chain_start(
        {},
        {},
        run_id=node_id,
        metadata={
            "langgraph_node": "supervisor",
            "langgraph_checkpoint_ns": "supervisor:t0",
        },
    )
    h.on_tool_start(
        {"name": "search_flights"},
        "",
        run_id=tool_id,
        parent_run_id=uuid4(),  # an unregistered parent
        metadata={
            "langgraph_node": "tools",
            "langgraph_checkpoint_ns": "concierge:t1|tools:t2",
        },
    )
    h.on_tool_end("whatever", run_id=tool_id)

    tool_step = [s for s in h.steps() if s["kind"] == "tool"][0]
    assert tool_step["tool_name"] == "search_flights"
    assert tool_step["node"] == "tools"
    assert tool_step["ns"] == "concierge:t1|tools:t2"
    assert tool_step["status"] == "ok"


def test_tool_name_falls_back_to_kwargs_name():
    h = TurnMetricsHandler()
    rid = uuid4()
    h.on_tool_start({}, "", run_id=rid, name="get_weather")
    h.on_tool_end("x", run_id=rid)

    (step,) = h.steps()
    assert step["tool_name"] == "get_weather"


def test_tool_error_closes_via_the_run_id_map():
    """on_tool_error carries neither name nor metadata — only the run_id map can close it."""
    h = TurnMetricsHandler()
    rid = uuid4()
    h.on_tool_start({"name": "book_flight"}, "", run_id=rid, metadata={})
    h.on_tool_error(ValueError("bad arg"), run_id=rid)

    (step,) = h.steps()
    assert step["tool_name"] == "book_flight"  # preserved from start
    assert step["status"] == "error"
    assert step["error_type"] == "ValueError"


def test_chain_error_closes_the_node_step():
    h = TurnMetricsHandler()
    rid = uuid4()
    h.on_chain_start(
        {},
        {},
        run_id=rid,
        metadata={"langgraph_node": "planner", "langgraph_checkpoint_ns": "planner:t1"},
    )
    h.on_chain_error(RuntimeError("node blew up"), run_id=rid)

    (step,) = h.steps()
    assert step["kind"] == "node"
    assert step["status"] == "error"
    assert step["error_type"] == "RuntimeError"


def test_unclosed_step_stays_open():
    h = TurnMetricsHandler()
    h.on_tool_start({"name": "slow_tool"}, "", run_id=uuid4(), metadata={})
    (step,) = h.steps()
    assert step["status"] == "open"
    assert step["ms"] == 0


def test_offset_ms_is_monotonic_across_steps():
    h = TurnMetricsHandler()
    for _ in range(3):
        rid = uuid4()
        h.on_tool_start({"name": "t"}, "", run_id=rid, metadata={})
        h.on_tool_end("x", run_id=rid)
    offsets = [s["offset_ms"] for s in h.steps()]
    assert offsets == sorted(offsets)
    assert offsets[0] >= 0


def test_step_cap_stops_at_max_and_counts_dropped_while_totals_stay_exact():
    h = TurnMetricsHandler()
    overflow = 25
    for _ in range(MAX_STEPS_PER_TURN + overflow):
        rid = uuid4()
        h.on_chat_model_start({}, [], run_id=rid, metadata={"ls_model_name": "gpt-5"})
        h.on_llm_end(
            _llm_result(model="gpt-5", input_tokens=2, output_tokens=1, cache_read=0),
            run_id=rid,
        )

    steps = h.steps()
    assert len(steps) == MAX_STEPS_PER_TURN
    assert h.steps_dropped == overflow

    # totals stay exact past the cap
    snap = h.snapshot()
    assert snap["llm_calls"] == MAX_STEPS_PER_TURN + overflow
    assert snap["input_tokens"] == 2 * (MAX_STEPS_PER_TURN + overflow)
    assert snap["output_tokens"] == MAX_STEPS_PER_TURN + overflow
    assert snap["by_model"]["gpt-5"]["calls"] == MAX_STEPS_PER_TURN + overflow


def test_cap_does_not_change_snapshot_or_public_shape():
    h = TurnMetricsHandler()
    for _ in range(MAX_STEPS_PER_TURN + 5):
        rid = uuid4()
        h.on_tool_start({"name": "t"}, "", run_id=rid, metadata={})
        h.on_tool_end("x", run_id=rid)

    assert h.steps_dropped == 5
    assert "steps" not in h.snapshot()
    assert "steps_dropped" not in h.public()


def test_a_raising_hook_leaves_other_steps_intact(monkeypatch):
    h = TurnMetricsHandler()
    first = uuid4()
    h.on_chat_model_start({}, [], run_id=first, metadata={"ls_model_name": "gpt-5"})
    h.on_llm_end(_llm_result(model="gpt-5"), run_id=first)
    before = h.steps()

    def _boom(*_a, **_k):
        raise ValueError("add_usage exploded")

    monkeypatch.setattr(metrics, "add_usage", _boom)
    second = uuid4()
    h.on_chat_model_start({}, [], run_id=second, metadata={"ls_model_name": "gpt-5"})
    h.on_llm_end(_llm_result(model="gpt-5"), run_id=second)  # must not raise

    steps = h.steps()
    assert steps[0] == before[0]  # the earlier step is untouched
    assert len(steps) == 2
    assert steps[1]["status"] == "ok"  # closed before the failing aggregation


def test_llm_end_without_usage_still_closes_the_step():
    h = TurnMetricsHandler()
    rid = uuid4()
    h.on_chat_model_start({}, [], run_id=rid, metadata={"ls_model_name": "gpt-5"})
    h.on_llm_end(LLMResult(generations=[[]]), run_id=rid)  # no message at all

    (step,) = h.steps()
    assert step["status"] == "ok"
    assert step["model"] == "gpt-5"
    assert step["meta"] == {}


def test_close_sweeps_a_step_whose_end_hook_never_fired():
    """A cancelled turn must not leave a step stranded as `open`.

    Without the sweep the row persists with status "open" and ms 0, which the
    waterfall would draw as a zero-width bar of unknown outcome.
    """
    h = TurnMetricsHandler()
    rid = uuid4()
    h.on_chat_model_start(
        {}, [], run_id=rid, metadata={"langgraph_node": "supervisor", "ls_model_name": "m"}
    )
    # no on_llm_end / on_llm_error — the stream was cancelled mid-call
    h.close_if_open()

    step = h.steps()[0]
    assert step["status"] == "unfinished"
    assert step["ms"] >= 0
