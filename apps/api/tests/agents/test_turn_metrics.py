"""TurnMetricsHandler unit tests (specs/agent-turn-metrics §4.1, SC-2)."""

import time
from uuid import uuid4

from app.agents import metrics
from app.agents.metrics import TurnMetricsHandler
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult


def _llm_result(
    *,
    model: str | None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read: int | None = None,
    usage: bool = True,
) -> LLMResult:
    """Build an LLMResult carrying one AIMessage, as the callback layer delivers it."""
    kwargs: dict = {"content": "hi"}
    if model is not None:
        kwargs["response_metadata"] = {"model_name": model}
    if usage:
        um: dict = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }
        if cache_read is not None:
            um["input_token_details"] = {"cache_read": cache_read}
        kwargs["usage_metadata"] = um
    message = AIMessage(**kwargs)
    return LLMResult(generations=[[ChatGeneration(message=message)]])


def _end(handler: TurnMetricsHandler, **kwargs) -> None:
    handler.on_llm_end(_llm_result(**kwargs), run_id=uuid4())


def test_two_models_aggregated_separately():
    h = TurnMetricsHandler()
    _end(h, model="gpt-5-mini", input_tokens=10, output_tokens=5)
    _end(h, model="gpt-5-mini", input_tokens=20, output_tokens=7)
    _end(h, model="claude-sonnet-5", input_tokens=100, output_tokens=40)

    snap = h.snapshot()
    assert snap["by_model"]["gpt-5-mini"] == {
        "input_tokens": 30,
        "output_tokens": 12,
        "cached_tokens": 0,
        "calls": 2,
    }
    assert snap["by_model"]["claude-sonnet-5"]["calls"] == 1
    assert snap["input_tokens"] == 130
    assert snap["output_tokens"] == 52
    assert snap["total_tokens"] == 182
    assert snap["llm_calls"] == 3


def test_cached_tokens_summed():
    h = TurnMetricsHandler()
    _end(h, model="gpt-5", input_tokens=100, output_tokens=10, cache_read=40)
    _end(h, model="gpt-5", input_tokens=200, output_tokens=20, cache_read=60)

    snap = h.snapshot()
    assert snap["by_model"]["gpt-5"]["cached_tokens"] == 100
    assert snap["cached_tokens"] == 100


def test_llm_error_counted():
    h = TurnMetricsHandler()
    h.on_llm_error(RuntimeError("boom"), run_id=uuid4())
    _end(h, model="gpt-5", input_tokens=5, output_tokens=1)

    snap = h.snapshot()
    assert snap["llm_errors"] == 1
    assert snap["llm_calls"] == 1


def test_call_without_name_or_usage_counted_not_aggregated():
    h = TurnMetricsHandler()
    _end(h, model=None, usage=False)  # neither name nor usage

    snap = h.snapshot()
    assert snap["llm_calls"] == 1
    assert snap["by_model"] == {}


def test_model_name_from_start_map_when_absent_at_end():
    h = TurnMetricsHandler()
    run_id = uuid4()
    h.on_chat_model_start(
        {}, [], run_id=run_id, metadata={"ls_model_name": "gpt-5-mini"}
    )
    # end message has no response_metadata model_name -> falls back to start map
    result = _llm_result(model=None, input_tokens=8, output_tokens=2)
    h.on_llm_end(result, run_id=run_id)

    snap = h.snapshot()
    assert snap["by_model"]["gpt-5-mini"]["input_tokens"] == 8


def test_node_timing_keyed_by_root():
    h = TurnMetricsHandler()
    run_id = uuid4()
    h.on_chain_start(
        {},
        {},
        run_id=run_id,
        metadata={
            "langgraph_node": "assistant",
            "langgraph_checkpoint_ns": "planner:t1|assistant:t2",
        },
    )
    h.on_chain_end({}, run_id=run_id)

    snap = h.snapshot()
    assert "planner/assistant" in snap["by_node"]
    assert snap["by_node"]["planner/assistant"]["runs"] == 1

    # a root-level node keeps its bare name
    root_id = uuid4()
    h.on_chain_start(
        {},
        {},
        run_id=root_id,
        metadata={
            "langgraph_node": "supervisor",
            "langgraph_checkpoint_ns": "supervisor:t9",
        },
    )
    h.on_chain_end({}, run_id=root_id)
    assert "supervisor" in h.snapshot()["by_node"]


def test_nested_same_namespace_not_double_counted():
    h = TurnMetricsHandler()
    ns = "supervisor:t1"
    outer = uuid4()
    inner = uuid4()
    # outer task run registers the node
    h.on_chain_start(
        {},
        {},
        run_id=outer,
        metadata={"langgraph_node": "supervisor", "langgraph_checkpoint_ns": ns},
    )
    # a nested run inherits the same namespace -> ignored
    h.on_chain_start(
        {},
        {},
        run_id=inner,
        metadata={"langgraph_node": "supervisor", "langgraph_checkpoint_ns": ns},
    )
    h.on_chain_end({}, run_id=inner)  # not tracked -> no-op
    h.on_chain_end({}, run_id=outer)

    assert h.snapshot()["by_node"]["supervisor"]["runs"] == 1


def test_hook_exception_leaves_counters_intact(monkeypatch):
    h = TurnMetricsHandler()
    _end(h, model="gpt-5", input_tokens=10, output_tokens=5)
    before = h.snapshot()["by_model"]["gpt-5"]

    def _boom(*_a, **_k):
        raise ValueError("add_usage exploded")

    monkeypatch.setattr(metrics, "add_usage", _boom)
    # must not raise despite the failing aggregation
    _end(h, model="gpt-5", input_tokens=999, output_tokens=999)

    after = h.snapshot()["by_model"]["gpt-5"]
    assert after == before  # token aggregation untouched by the failed hook


def test_close_sets_latency_ms():
    import time

    h = TurnMetricsHandler()
    assert h.snapshot()["latency_ms"] is None
    h.close(time.monotonic() - 0.05)
    assert h.snapshot()["latency_ms"] >= 50


def test_public_keys_are_exactly_the_documented_set():
    h = TurnMetricsHandler()
    _end(h, model="gpt-5", input_tokens=10, output_tokens=5)
    pub = h.public()
    assert set(pub.keys()) == {
        "input_tokens",
        "output_tokens",
        "cached_tokens",
        "total_tokens",
        "llm_calls",
        "latency_ms",
        "cost_usd",
        "models",
    }
    assert pub["models"] == ["gpt-5"]
    assert pub["cost_usd"] is None


def test_close_if_open_sets_latency_from_creation():
    """A failed turn never calls close(started); close_if_open still records it."""
    h = TurnMetricsHandler()
    assert h.latency_ms is None
    h.close_if_open()
    assert h.latency_ms is not None and h.latency_ms >= 0


def test_close_if_open_does_not_overwrite_an_explicit_close():
    h = TurnMetricsHandler()
    h.close(time.monotonic())
    first = h.latency_ms
    h.close_if_open()
    assert h.latency_ms == first


def test_node_retry_with_same_namespace_is_timed_again():
    """A retried node reuses its deterministic checkpoint_ns; both runs count.

    The namespace dedupe only exists to ignore nested runs that inherit the task
    metadata while the node is in flight — it must not swallow a genuine
    re-execution (MIN-49 RetryPolicy).
    """
    h = TurnMetricsHandler()
    meta = {"langgraph_node": "planner", "langgraph_checkpoint_ns": "planner:abc"}
    for _ in range(2):
        rid = uuid4()
        h.on_chain_start({}, {}, run_id=rid, metadata=meta)
        h.on_chain_end({}, run_id=rid)
    assert h.snapshot()["by_node"]["planner"]["runs"] == 2


def test_nested_run_sharing_the_namespace_is_still_deduped():
    h = TurnMetricsHandler()
    meta = {"langgraph_node": "planner", "langgraph_checkpoint_ns": "planner:abc"}
    outer, inner = uuid4(), uuid4()
    h.on_chain_start({}, {}, run_id=outer, metadata=meta)
    h.on_chain_start({}, {}, run_id=inner, metadata=meta)  # nested — ignored
    h.on_chain_end({}, run_id=inner)
    h.on_chain_end({}, run_id=outer)
    assert h.snapshot()["by_node"]["planner"]["runs"] == 1
