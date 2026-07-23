"""Registry tests for the MIN-65 metrics: memory_recall + suggestion_relevance.

Construction-only, like ``test_metrics_geval.py``: deepeval 4.0.7 eagerly
instantiates the judge GPTModel when a GEval is built, so every test here uses
a dummy ``OPENAI_API_KEY`` and never calls ``.measure()``/``evaluate()`` (which
would hit the network).
"""

import pytest
from deepeval.test_case import LLMTestCase, SingleTurnParams
from eval.metrics_geval import (
    GEVAL_METRICS,
    memory_recall_metric,
    suggestion_relevance_metric,
)
from eval.run_deepeval import (
    build_test_cases,
    cases_for_metric,
    known_suggestion_keys,
    suggestion_relevance_deterministic,
)


@pytest.fixture(autouse=True)
def _dummy_judge_key(monkeypatch):
    # See test_metrics_geval.py — a dummy key keeps GEval construction offline.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy-eval-key")


def test_registry_has_six_dimensions():
    assert set(GEVAL_METRICS) == {
        "response_language",
        "search_vs_booking",
        "no_hallucination",
        "format_quality",
        "memory_recall",
        "suggestion_relevance",
    }


def test_registry_dispatches_new_factories():
    assert GEVAL_METRICS["memory_recall"] is memory_recall_metric
    assert GEVAL_METRICS["suggestion_relevance"] is suggestion_relevance_metric


def test_memory_recall_metric_shape():
    m = memory_recall_metric()
    assert m.name == "Memory Recall"
    assert SingleTurnParams.INPUT in m.evaluation_params
    assert SingleTurnParams.ACTUAL_OUTPUT in m.evaluation_params
    assert m.threshold == 0.7


def test_suggestion_relevance_metric_shape():
    m = suggestion_relevance_metric()
    assert m.name == "Suggestion Relevance"
    assert SingleTurnParams.INPUT in m.evaluation_params
    assert SingleTurnParams.ACTUAL_OUTPUT in m.evaluation_params
    assert SingleTurnParams.RETRIEVAL_CONTEXT in m.evaluation_params
    assert m.threshold == 0.7


def test_cases_for_metric_filters_memory_recall_and_suggestion_relevance():
    a = LLMTestCase(
        input="a", actual_output="x", metadata={"metrics": ["memory_recall"]}
    )
    b = LLMTestCase(
        input="b", actual_output="y", metadata={"metrics": ["suggestion_relevance"]}
    )
    c = LLMTestCase(input="c", actual_output="z", metadata={"metrics": []})
    assert cases_for_metric("memory_recall", [a, b, c]) == [a]
    assert cases_for_metric("suggestion_relevance", [a, b, c]) == [b]


def test_known_suggestion_keys_matches_current_catalog():
    from app.agents.suggestions import _FLOW_SUGGESTIONS

    expected = {key for keys in _FLOW_SUGGESTIONS.values() for key in keys}
    assert known_suggestion_keys() == expected
    assert "concierge.checkWeather" in known_suggestion_keys()


def _case(metrics, suggestions):
    return LLMTestCase(
        input="i",
        actual_output="o",
        metadata={"metrics": metrics, "suggestions": suggestions},
    )


def test_suggestion_relevance_deterministic_passes_nonempty_known_keys():
    cases = [_case(["suggestion_relevance"], ["concierge.checkWeather"])]
    assert suggestion_relevance_deterministic(cases) == {
        "total": 1,
        "passed": 1,
        "rate": 1.0,
    }


def test_suggestion_relevance_deterministic_fails_empty_suggestions():
    cases = [_case(["suggestion_relevance"], [])]
    assert suggestion_relevance_deterministic(cases) == {
        "total": 1,
        "passed": 0,
        "rate": 0.0,
    }


def test_suggestion_relevance_deterministic_fails_unknown_key():
    cases = [_case(["suggestion_relevance"], ["not.a_real_key"])]
    assert suggestion_relevance_deterministic(cases) == {
        "total": 1,
        "passed": 0,
        "rate": 0.0,
    }


def test_suggestion_relevance_deterministic_ignores_cases_not_declaring_metric():
    # Not opted into the rubric via `metrics` -> excluded from the denominator.
    cases = [_case([], ["concierge.checkWeather"])]
    assert suggestion_relevance_deterministic(cases) == {
        "total": 0,
        "passed": 0,
        "rate": 0.0,
    }


def test_suggestion_relevance_deterministic_mixed_rate():
    cases = [
        _case(["suggestion_relevance"], ["concierge.checkWeather"]),
        _case(["suggestion_relevance"], []),
    ]
    assert suggestion_relevance_deterministic(cases) == {
        "total": 2,
        "passed": 1,
        "rate": 0.5,
    }


class _StubGraph:
    """Minimal graph stand-in: .invoke returns a canned result (no network)."""

    def invoke(self, state, cfg, context=None):
        from langchain_core.messages import AIMessage

        return {"messages": [AIMessage(content="ok")], "current_flow": "concierge"}


def test_build_test_cases_attaches_suggestions_and_retrieval_context():
    cases = build_test_cases(_StubGraph(), {"d": [{"input": "a"}]})
    expected_keys = [
        "concierge.nearbyPlaces",
        "concierge.checkWeather",
        "concierge.getThere",
    ]
    assert cases[0].metadata["suggestions"] == expected_keys
    assert cases[0].retrieval_context == expected_keys
    assert cases[0].metadata["metrics"] == []
