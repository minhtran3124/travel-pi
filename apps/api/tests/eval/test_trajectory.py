"""Deterministic trajectory metric: pass + fail cases per mode
(agent-eval-pipeline task 2.2). Offline — no network, no LLM.
"""

from __future__ import annotations

from evalkit.metrics.trajectory import TrajectoryMatchMetric
from evalkit.registry import get_metric, list_metrics
from evalkit.types import Golden, Trace


def _golden(**overrides):
    defaults = {
        "id": "case-001",
        "capability": "flight_search",
        "scenario": "happy",
        "language": "en",
        "suite": "smoke",
        "input": "find me a flight",
    }
    defaults.update(overrides)
    return Golden(**defaults)


def _ai_tool_call(name: str, call_id: str) -> dict:
    return {
        "type": "ai",
        "content": "",
        "tool_calls": [{"name": name, "args": {}, "id": call_id, "type": "tool_call"}],
    }


def _tool_result(call_id: str, name: str) -> dict:
    return {"type": "tool", "content": "ok", "tool_call_id": call_id, "name": name}


def _messages_for(tool_names: list[str]) -> list[dict]:
    """A realistic interleaved message list: human -> (ai tool_call, tool
    result) per tool -> final ai reply. Exercises that the extractor drops
    the non-assistant-tool-call noise rather than needing a flat list.
    """
    messages: list[dict] = [{"type": "human", "content": "find me a flight"}]
    for i, name in enumerate(tool_names):
        call_id = f"call-{i}"
        messages.append(_ai_tool_call(name, call_id))
        messages.append(_tool_result(call_id, name))
    messages.append({"type": "ai", "content": "Here are your options."})
    return messages


def _trace(tool_names: list[str]) -> Trace:
    return Trace(reply="Here are your options.", messages=_messages_for(tool_names))


# --- registration --------------------------------------------------------


def test_all_three_trajectory_variants_are_registered():
    names = list_metrics()
    assert "trajectory_match" in names
    assert "trajectory_match_strict" in names
    assert "trajectory_match_unordered" in names
    assert isinstance(get_metric("trajectory_match"), TrajectoryMatchMetric)


def test_invalid_mode_raises():
    try:
        TrajectoryMatchMetric(mode="bogus")
    except ValueError:
        return
    raise AssertionError("expected ValueError for invalid mode")


# --- not_applicable --------------------------------------------------------


def test_not_applicable_when_no_expected_trajectory():
    golden = _golden()  # no expected_trajectory
    trace = _trace(["geocode_city", "search_flights"])
    result = TrajectoryMatchMetric(mode="subset").evaluate(golden, trace, None)
    assert result.passed
    assert result.detail.startswith("not_applicable")


# --- exact match: all modes pass ------------------------------------------


def test_exact_match_passes_in_all_modes():
    golden = _golden(expected_trajectory=["geocode_city", "search_flights"])
    trace = _trace(["geocode_city", "search_flights"])
    for mode in ("strict", "unordered", "subset"):
        result = TrajectoryMatchMetric(mode=mode).evaluate(golden, trace, None)
        assert result.passed, f"mode={mode} detail={result.detail}"


# --- extra tool call: subset passes, strict (and unordered) fail ---------


def test_extra_tool_call_subset_passes_strict_fails():
    golden = _golden(expected_trajectory=["geocode_city", "search_flights"])
    trace = _trace(["geocode_city", "search_flights", "search_hotels"])

    subset_result = TrajectoryMatchMetric(mode="subset").evaluate(golden, trace, None)
    assert subset_result.passed

    strict_result = TrajectoryMatchMetric(mode="strict").evaluate(golden, trace, None)
    assert not strict_result.passed
    assert "unexpected" in strict_result.detail
    assert "search_hotels" in strict_result.detail


def test_extra_tool_call_fails_unordered_too():
    golden = _golden(expected_trajectory=["geocode_city", "search_flights"])
    trace = _trace(["geocode_city", "search_flights", "search_hotels"])
    result = TrajectoryMatchMetric(mode="unordered").evaluate(golden, trace, None)
    assert not result.passed
    assert "search_hotels" in result.detail


# --- wrong order: unordered passes, strict fails --------------------------


def test_wrong_order_unordered_passes_strict_fails():
    golden = _golden(expected_trajectory=["geocode_city", "search_flights"])
    trace = _trace(["search_flights", "geocode_city"])

    unordered_result = TrajectoryMatchMetric(mode="unordered").evaluate(
        golden, trace, None
    )
    assert unordered_result.passed

    strict_result = TrajectoryMatchMetric(mode="strict").evaluate(golden, trace, None)
    assert not strict_result.passed
    assert "order mismatch" in strict_result.detail
    assert "geocode_city" in strict_result.detail


# --- missing tool: all modes fail -----------------------------------------


def test_missing_tool_fails_in_all_modes():
    golden = _golden(
        expected_trajectory=["geocode_city", "search_flights", "book_flight"]
    )
    trace = _trace(["geocode_city", "search_flights"])

    for mode in ("strict", "unordered", "subset"):
        result = TrajectoryMatchMetric(mode=mode).evaluate(golden, trace, None)
        assert not result.passed, f"mode={mode} unexpectedly passed"
        assert "missing" in result.detail
        assert "book_flight" in result.detail
