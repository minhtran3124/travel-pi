import pytest
from deepeval.test_case import SingleTurnParams
from eval.metrics_geval import (
    GEVAL_METRICS,
    JUDGE_MODEL,
    response_language_metric,
    tool_correctness_metric,
)


@pytest.fixture(autouse=True)
def _dummy_judge_key(monkeypatch):
    # deepeval 4.0.7 eagerly instantiates the judge GPTModel when a GEval is
    # built, which requires OPENAI_API_KEY to be present. A dummy key keeps
    # construction offline — these tests never call .measure()/evaluate(), so
    # no request is ever sent to OpenAI.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy-eval-key")


def test_judge_is_openai_native_string():
    assert JUDGE_MODEL == "gpt-4o-mini"


def test_geval_registry_has_six_dimensions():
    # MIN-65 D9 adds memory_recall + suggestion_relevance to the MIN-58 four.
    assert set(GEVAL_METRICS) == {
        "response_language",
        "search_vs_booking",
        "no_hallucination",
        "format_quality",
        "memory_recall",
        "suggestion_relevance",
    }


def test_response_language_metric_shape():
    m = response_language_metric()
    assert m.name == "Response Language"
    assert SingleTurnParams.INPUT in m.evaluation_params
    assert SingleTurnParams.ACTUAL_OUTPUT in m.evaluation_params
    assert m.threshold == 0.7


def test_tool_correctness_is_deterministic_metric():
    # Constructs without a judge model (no OpenAI key needed).
    assert tool_correctness_metric() is not None
