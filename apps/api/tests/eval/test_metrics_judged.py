"""Judged (G-Eval) metrics: rubric registration, k-repeat averaging, and
retrieval_context grounding (agent-eval-pipeline task 2.3).

No network: every test injects a stub judge (a `geval_factory`) instead of
letting `GEvalJudgedMetric` build a real DeepEval `GEval`/`GPTModel`. This
also guards the real prior failure mode — a `.env` with a live-looking
OPENAI_API_KEY sitting in `apps/api/` means monkeypatching the env var alone
would NOT stop an accidental real judge call; only never constructing/
calling a real `GEval` does.
"""

from __future__ import annotations

import pytest
from evalkit.metrics.judged import (
    DEFAULT_THRESHOLD,
    RUBRICS,
    GEvalJudgedMetric,
    build_retrieval_context,
    make_all_judged_metrics,
    make_judged_metric,
)
from evalkit.registry import get_metric, list_metrics
from evalkit.types import Golden, ToolCall, Trace


def _golden(**overrides):
    defaults = {
        "id": "case-001",
        "capability": "hotels",
        "scenario": "happy",
        "language": "en",
        "suite": "smoke",
        "input": "Find me a hotel in Da Nang",
    }
    defaults.update(overrides)
    return Golden(**defaults)


def _trace(**overrides):
    defaults = {"reply": "Here are your options."}
    defaults.update(overrides)
    return Trace(**defaults)


class _StubJudge:
    """Fake `Judge`: returns a fixed score per `.measure()` call, no network.

    `scores` is consumed one at a time (one per k-repeat), so a test can
    assert exactly what gets averaged.
    """

    def __init__(self, scores: list[float], evaluation_params=None):
        self._scores = list(scores)
        self.evaluation_params = evaluation_params
        self.calls: list = []
        self.score = None

    def measure(self, test_case) -> float:
        self.calls.append(test_case)
        self.score = self._scores.pop(0)
        return self.score


def _stub_factory(scores: list[float]):
    judge = _StubJudge(scores)

    def factory(name, rubric):
        return judge

    factory.judge = judge  # type: ignore[attr-defined]
    return factory


# --- rubric DATA + registration ------------------------------------------


ALL_RUBRIC_NAMES = {
    "response_language",
    "search_vs_booking",
    "no_hallucination",
    "format_quality",
    "memory_recall",
    "suggestion_relevance",
    "ask_coverage",
}


def test_all_seven_rubrics_are_data():
    assert set(RUBRICS) == ALL_RUBRIC_NAMES
    for _name, rubric in RUBRICS.items():
        assert "criteria" in rubric and rubric["criteria"]
        assert "evaluation_params" in rubric and rubric["evaluation_params"]
        assert rubric.get("threshold", DEFAULT_THRESHOLD) == DEFAULT_THRESHOLD


def test_no_hallucination_rubric_requests_retrieval_context():
    from deepeval.test_case import SingleTurnParams

    assert (
        SingleTurnParams.RETRIEVAL_CONTEXT
        in RUBRICS["no_hallucination"]["evaluation_params"]
    )


def test_suggestion_relevance_rubric_requests_retrieval_context():
    """MIN-65 task 1.2: relevance is judged against the suggestion keys
    carried in retrieval_context, same grounding pattern as no_hallucination."""
    from deepeval.test_case import SingleTurnParams

    assert (
        SingleTurnParams.RETRIEVAL_CONTEXT
        in RUBRICS["suggestion_relevance"]["evaluation_params"]
    )


def test_other_rubrics_do_not_request_retrieval_context():
    from deepeval.test_case import SingleTurnParams

    for name in (
        "response_language",
        "search_vs_booking",
        "format_quality",
        "memory_recall",
        "ask_coverage",
    ):
        assert (
            SingleTurnParams.RETRIEVAL_CONTEXT not in RUBRICS[name]["evaluation_params"]
        )


def test_all_seven_metrics_are_registered_by_module_import():
    names = list_metrics()
    for expected in ALL_RUBRIC_NAMES:
        assert expected in names
    assert isinstance(get_metric("response_language"), GEvalJudgedMetric)
    assert isinstance(get_metric("memory_recall"), GEvalJudgedMetric)
    assert isinstance(get_metric("suggestion_relevance"), GEvalJudgedMetric)
    assert isinstance(get_metric("ask_coverage"), GEvalJudgedMetric)


def test_registering_never_builds_a_real_judge_without_a_key(monkeypatch):
    # Importing/registering this module must not require OPENAI_API_KEY at
    # all: the default `build_geval` factory is stored but never called until
    # `.evaluate()` runs. Simulate "no key anywhere" and simply re-run the
    # registration path used at import time.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    metric = make_judged_metric("format_quality")  # must not raise, no network
    assert metric.name == "format_quality"
    assert metric._judge is None  # judge not built yet


# --- k-repeat averaging ----------------------------------------------------


def test_k1_uses_a_single_score_directly():
    factory = _stub_factory([0.9])
    metric = GEvalJudgedMetric(
        "format_quality", RUBRICS["format_quality"], k=1, geval_factory=factory
    )
    result = metric.evaluate(_golden(), _trace(), None)
    assert result.score == 0.9
    assert result.passed  # 0.9 >= 0.7


def test_k_repeat_averages_scores_not_last_value():
    # k=3 with scores 0.9, 0.3, 0.9 -> mean 0.7, exactly at threshold: passes.
    # This also proves it's an AVERAGE, not e.g. the last or first sample.
    factory = _stub_factory([0.9, 0.3, 0.9])
    metric = GEvalJudgedMetric(
        "format_quality", RUBRICS["format_quality"], k=3, geval_factory=factory
    )
    result = metric.evaluate(_golden(), _trace(), None)
    assert result.score == pytest.approx(0.7)
    assert result.passed
    assert "k=3" in result.detail


def test_k_repeat_calls_measure_exactly_k_times():
    factory = _stub_factory([0.8, 0.8, 0.8, 0.8, 0.8])
    metric = GEvalJudgedMetric(
        "format_quality", RUBRICS["format_quality"], k=5, geval_factory=factory
    )
    metric.evaluate(_golden(), _trace(), None)
    assert len(factory.judge.calls) == 5  # type: ignore[attr-defined]


def test_averaged_score_below_threshold_fails():
    factory = _stub_factory([0.2, 0.3])
    metric = GEvalJudgedMetric(
        "format_quality", RUBRICS["format_quality"], k=2, geval_factory=factory
    )
    result = metric.evaluate(_golden(), _trace(), None)
    assert result.score == pytest.approx(0.25)
    assert not result.passed


def test_judge_is_built_once_and_cached_across_evaluate_calls():
    build_count = {"n": 0}

    def factory(name, rubric):
        build_count["n"] += 1
        return _StubJudge([0.8, 0.8])

    metric = GEvalJudgedMetric(
        "format_quality", RUBRICS["format_quality"], k=1, geval_factory=factory
    )
    metric.evaluate(_golden(), _trace(), None)
    metric.evaluate(_golden(), _trace(), None)
    assert build_count["n"] == 1  # lazy-built once, reused — not rebuilt per call


def test_k_must_be_at_least_one():
    try:
        GEvalJudgedMetric("format_quality", RUBRICS["format_quality"], k=0)
    except ValueError:
        return
    raise AssertionError("expected ValueError for k=0")


# --- make_judged_metric / make_all_judged_metrics --------------------------


def test_make_judged_metric_builds_configured_instance():
    metric = make_judged_metric(
        "no_hallucination", k=3, judge_model="gpt-4o", temperature=0.0
    )
    assert metric.name == "no_hallucination"
    assert metric.k == 3


def test_make_all_judged_metrics_returns_all_seven():
    metrics = make_all_judged_metrics(k=3)
    assert {m.name for m in metrics} == set(RUBRICS)
    assert all(m.k == 3 for m in metrics)


# --- retrieval_context assembly from Trace.tool_calls ----------------------


def test_build_retrieval_context_serializes_tool_outputs():
    trace = _trace(
        tool_calls=[
            ToolCall(
                name="search_hotels",
                args={"city": "Da Nang"},
                output={"count": 2, "hotels": ["A", "B"]},
            ),
            ToolCall(name="geocode_city", args={"city": "Da Nang"}, output={"lat": 1}),
        ]
    )
    context = build_retrieval_context(trace)
    assert context is not None
    assert len(context) == 2
    assert "search_hotels" in context[0]
    assert "Da Nang" in context[0]
    assert "count" in context[0]
    assert "geocode_city" in context[1]


def test_build_retrieval_context_is_none_with_no_tool_calls():
    assert build_retrieval_context(_trace(tool_calls=[])) is None


def test_build_retrieval_context_includes_suggestion_keys():
    trace = _trace(meta={"suggestions": ["planner.checkWeather", "planner.addPlace"]})
    context = build_retrieval_context(trace)
    assert context == [
        "suggestion: planner.checkWeather",
        "suggestion: planner.addPlace",
    ]


def test_build_retrieval_context_still_none_without_tools_or_suggestions():
    assert build_retrieval_context(_trace(tool_calls=[], meta={})) is None


def test_evaluate_passes_retrieval_context_into_the_test_case():
    trace = _trace(
        reply="The Sunrise Hotel costs $80/night.",
        tool_calls=[
            ToolCall(
                name="search_hotels",
                args={"city": "Da Nang"},
                output={"hotels": [{"name": "Sunrise Hotel", "price": 80}]},
            )
        ],
    )
    factory = _stub_factory([0.9])
    metric = GEvalJudgedMetric(
        "no_hallucination", RUBRICS["no_hallucination"], k=1, geval_factory=factory
    )
    metric.evaluate(_golden(), trace, None)
    seen_case = factory.judge.calls[0]  # type: ignore[attr-defined]
    assert seen_case.retrieval_context is not None
    assert any("Sunrise Hotel" in line for line in seen_case.retrieval_context)


def test_evaluate_uses_last_turn_for_multi_turn_goldens():
    golden = _golden(input=None, turns=["hi", "book me a hotel in Hue"])
    factory = _stub_factory([0.9])
    metric = GEvalJudgedMetric(
        "format_quality", RUBRICS["format_quality"], k=1, geval_factory=factory
    )
    metric.evaluate(golden, _trace(), None)
    seen_case = factory.judge.calls[0]  # type: ignore[attr-defined]
    assert seen_case.input == "book me a hotel in Hue"


# --- empty reply (HITL interrupt) -------------------------------------------


def test_empty_reply_is_not_applicable_and_never_calls_the_judge():
    """A booking golden stops at the HITL interrupt with no AIMessage text;
    GEval would raise MissingTestCaseParamsError on the empty actual_output."""
    factory = _stub_factory([0.9])
    metric = GEvalJudgedMetric(
        "suggestion_relevance",
        RUBRICS["suggestion_relevance"],
        k=3,
        geval_factory=factory,
    )
    result = metric.evaluate(_golden(), _trace(reply="   "), None)
    assert result.passed is True
    assert result.score is None
    assert result.detail.startswith("not_applicable: empty reply")
    assert factory.judge.calls == []
