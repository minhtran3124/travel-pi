"""Deterministic (judge-free) metrics: pass + fail cases per metric
(agent-eval-pipeline task 1.2).
"""

from __future__ import annotations

from evalkit.metrics.deterministic import (
    FlowMatchMetric,
    NonEmptyReplyMetric,
    ReplyLanguageMetric,
    TasksExpectedMetric,
    ToolArgsShapeMetric,
    ToolsExpectedMetric,
    make_tool_args_shape_metric,
)
from evalkit.registry import get_metric, list_metrics
from evalkit.types import Golden, ToolCall, Trace


def _golden(**overrides):
    defaults = {
        "id": "case-001",
        "capability": "flight_search",
        "scenario": "happy",
        "language": "en",
        "suite": "smoke",
        "input": "hello",
    }
    defaults.update(overrides)
    return Golden(**defaults)


def _trace(**overrides):
    defaults = {"reply": "Here are your options."}
    defaults.update(overrides)
    return Trace(**defaults)


def test_all_five_metrics_are_registered():
    names = list_metrics()
    assert "flow_match" in names
    assert "tools_expected" in names
    assert "tools_expected_exact" in names
    assert "reply_language" in names
    assert "non_empty_reply" in names
    assert "tool_args_shape" in names
    # sanity: registry lookup returns the same instances directly imported
    assert isinstance(get_metric("flow_match"), FlowMatchMetric)


# --- flow_match ---------------------------------------------------------


def test_flow_match_passes_on_match():
    golden = _golden(expected_flow="concierge")
    trace = _trace(flow="concierge")
    result = FlowMatchMetric().evaluate(golden, trace, None)
    assert result.passed
    assert "not_applicable" not in (result.detail or "")


def test_flow_match_fails_on_mismatch():
    golden = _golden(expected_flow="concierge")
    trace = _trace(flow="booking")
    result = FlowMatchMetric().evaluate(golden, trace, None)
    assert not result.passed


def test_flow_match_not_applicable_when_unconfigured():
    golden = _golden()  # no expected_flow
    trace = _trace(flow="concierge")
    result = FlowMatchMetric().evaluate(golden, trace, None)
    assert result.passed
    assert result.detail.startswith("not_applicable")


# --- tools_expected (subset + exact) ------------------------------------


def test_tools_expected_subset_passes_with_extra_tools():
    golden = _golden(expected_tools=["search_flights"])
    trace = _trace(
        tool_calls=[
            ToolCall(name="search_flights", args={}, output={}),
            ToolCall(name="geocode_city", args={}, output={}),
        ]
    )
    result = ToolsExpectedMetric(mode="subset").evaluate(golden, trace, None)
    assert result.passed


def test_tools_expected_subset_fails_on_missing_tool():
    golden = _golden(expected_tools=["search_flights"])
    trace = _trace(tool_calls=[ToolCall(name="geocode_city", args={}, output={})])
    result = ToolsExpectedMetric(mode="subset").evaluate(golden, trace, None)
    assert not result.passed


def test_tools_expected_exact_fails_on_extra_tool():
    golden = _golden(expected_tools=["search_flights"])
    trace = _trace(
        tool_calls=[
            ToolCall(name="search_flights", args={}, output={}),
            ToolCall(name="geocode_city", args={}, output={}),
        ]
    )
    result = ToolsExpectedMetric(mode="exact").evaluate(golden, trace, None)
    assert not result.passed


def test_tools_expected_exact_passes_on_exact_set():
    golden = _golden(expected_tools=["search_flights"])
    trace = _trace(tool_calls=[ToolCall(name="search_flights", args={}, output={})])
    result = ToolsExpectedMetric(mode="exact").evaluate(golden, trace, None)
    assert result.passed


def test_tools_expected_not_applicable_when_unconfigured():
    golden = _golden()  # no expected_tools
    trace = _trace(tool_calls=[])
    result = ToolsExpectedMetric().evaluate(golden, trace, None)
    assert result.passed
    assert result.detail.startswith("not_applicable")


def test_tools_expected_invalid_mode_raises():
    try:
        ToolsExpectedMetric(mode="bogus")
    except ValueError:
        return
    raise AssertionError("expected ValueError for invalid mode")


# --- reply_language ------------------------------------------------------


def test_reply_language_detects_vietnamese_with_diacritics():
    golden = _golden(language="vi")
    trace = _trace(reply="Chào bạn, đây là chuyến bay giá tốt nhất cho bạn.")
    result = ReplyLanguageMetric().evaluate(golden, trace, None)
    assert result.passed


def test_reply_language_detects_english():
    golden = _golden(language="en")
    trace = _trace(reply="Here are the best flights for your trip.")
    result = ReplyLanguageMetric().evaluate(golden, trace, None)
    assert result.passed


def test_reply_language_fails_on_mismatch():
    golden = _golden(language="vi")
    trace = _trace(reply="Here are the best flights for your trip.")
    result = ReplyLanguageMetric().evaluate(golden, trace, None)
    assert not result.passed


def test_reply_language_unaccented_vietnamese_via_function_words():
    golden = _golden(language="vi")
    trace = _trace(reply="Toi khong biet cho ban cai nay duoc.")
    result = ReplyLanguageMetric().evaluate(golden, trace, None)
    assert result.passed


# --- non_empty_reply -------------------------------------------------------


def test_non_empty_reply_passes_on_real_reply():
    result = NonEmptyReplyMetric().evaluate(
        _golden(), _trace(reply="A real answer."), None
    )
    assert result.passed


def test_non_empty_reply_fails_on_empty_string():
    result = NonEmptyReplyMetric().evaluate(_golden(), _trace(reply="   "), None)
    assert not result.passed


def test_non_empty_reply_fails_on_bare_error_marker():
    result = NonEmptyReplyMetric().evaluate(_golden(), _trace(reply="[error]"), None)
    assert not result.passed


# --- tool_args_shape -------------------------------------------------------


def test_tool_args_shape_not_applicable_with_no_schemas():
    metric = ToolArgsShapeMetric()  # default, no schemas configured
    trace = _trace(tool_calls=[ToolCall(name="search_flights", args={}, output={})])
    result = metric.evaluate(_golden(), trace, None)
    assert result.passed
    assert result.detail.startswith("not_applicable")


def test_tool_args_shape_passes_on_valid_args():
    metric = make_tool_args_shape_metric(
        {
            "search_flights": {
                "required": ["origin", "destination"],
                "properties": {
                    "origin": {"type": "string"},
                    "destination": {"type": "string"},
                },
            }
        }
    )
    trace = _trace(
        tool_calls=[
            ToolCall(
                name="search_flights",
                args={"origin": "HAN", "destination": "DAD"},
                output={},
            )
        ]
    )
    result = metric.evaluate(_golden(), trace, None)
    assert result.passed


def test_tool_args_shape_fails_on_missing_required_arg():
    metric = make_tool_args_shape_metric(
        {"search_flights": {"required": ["origin", "destination"]}}
    )
    trace = _trace(
        tool_calls=[ToolCall(name="search_flights", args={"origin": "HAN"}, output={})]
    )
    result = metric.evaluate(_golden(), trace, None)
    assert not result.passed
    assert "destination" in result.detail


def test_tool_args_shape_fails_on_wrong_type():
    metric = make_tool_args_shape_metric(
        {"search_flights": {"properties": {"origin": {"type": "string"}}}}
    )
    trace = _trace(
        tool_calls=[ToolCall(name="search_flights", args={"origin": 123}, output={})]
    )
    result = metric.evaluate(_golden(), trace, None)
    assert not result.passed


def test_tool_args_shape_ignores_tool_without_configured_schema():
    metric = make_tool_args_shape_metric({"search_flights": {"required": ["origin"]}})
    trace = _trace(tool_calls=[ToolCall(name="geocode_city", args={}, output={})])
    result = metric.evaluate(_golden(), trace, None)
    assert result.passed
    assert result.detail.startswith("not_applicable")


# --- tasks_expected -------------------------------------------------------


def test_tasks_expected_passes_order_independent():
    golden = _golden(expected_tasks=["budget", "concierge"])
    trace = _trace(meta={"tasks": ["concierge", "budget"]})
    result = TasksExpectedMetric().evaluate(golden, trace, None)
    assert result.passed


def test_tasks_expected_fails_on_mismatch():
    golden = _golden(expected_tasks=["planner"])
    trace = _trace(meta={"tasks": ["planner", "concierge"]})
    result = TasksExpectedMetric().evaluate(golden, trace, None)
    assert not result.passed
    assert "expected=" in result.detail
    assert "got=" in result.detail


def test_tasks_expected_fails_when_meta_has_no_tasks():
    golden = _golden(expected_tasks=["planner"])
    trace = _trace(meta={})
    result = TasksExpectedMetric().evaluate(golden, trace, None)
    assert not result.passed
    assert "no meta.tasks" in result.detail


def test_tasks_expected_not_applicable_when_unconfigured():
    golden = _golden()  # no expected_tasks
    trace = _trace(meta={"tasks": ["planner"]})
    result = TasksExpectedMetric().evaluate(golden, trace, None)
    assert result.passed
    assert result.detail.startswith("not_applicable:")


def test_reply_language_empty_reply_is_not_applicable():
    """A HITL interrupt leaves reply == ""; that is non_empty_reply's job to
    report, not a language mismatch."""
    metric = ReplyLanguageMetric()
    result = metric.evaluate(_golden(language="vi"), _trace(reply=""), None)
    assert result.passed is True
    assert result.detail.startswith("not_applicable: empty reply")
