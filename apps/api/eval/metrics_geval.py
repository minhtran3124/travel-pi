"""G-Eval + tool-correctness metrics for the offline eval harness (MIN-58).

Judge = OpenAI `gpt-4o-mini` passed as a `model=` string (DeepEval-native, no
custom DeepEvalBaseLLM adapter). GEval derives evaluation steps from the
natural-language `criteria`. `ToolCorrectnessMetric` is deterministic (no judge).
Building these objects does no network I/O; only `.measure()` / `evaluate()` does.
"""

from __future__ import annotations

from deepeval.metrics import GEval, ToolCorrectnessMetric
from deepeval.test_case import SingleTurnParams

JUDGE_MODEL = "gpt-4o-mini"  # OpenAI-native judge; swap via a custom model later (MIN-58 follow-up)
DEFAULT_THRESHOLD = 0.7

_IO = [SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT]


def response_language_metric() -> GEval:
    """Answer must be in the same natural language as the user's input (MIN-57)."""
    return GEval(
        name="Response Language",
        criteria=(
            "Determine whether the actual output is written in the SAME natural "
            "language as the input. If the input is Vietnamese, the answer must be "
            "Vietnamese; if English, English. Penalize any answer that switches "
            "language or mixes languages against the user's language."
        ),
        evaluation_params=_IO,
        threshold=DEFAULT_THRESHOLD,
        model=JUDGE_MODEL,
    )


def search_vs_booking_metric() -> GEval:
    """Search intent must not be answered with booking/payment prompts (MIN-51)."""
    return GEval(
        name="Search vs Booking Intent",
        criteria=(
            "The input is a hotel/flight SEARCH or information request, not a "
            "confirmed booking. A good answer stays in search mode: it presents "
            "options/results, or — when nothing matches — clearly says none were "
            "found and offers to adjust the search (widen the budget, change the "
            "dates, relax filters). Reporting no results and offering to broaden "
            "the search is CORRECT behavior, not a failure. Penalize ONLY answers "
            "that push booking, ask for payment/passport/guest details, or assume "
            "the user already decided to book."
        ),
        evaluation_params=_IO,
        threshold=DEFAULT_THRESHOLD,
        model=JUDGE_MODEL,
    )


def no_hallucination_metric() -> GEval:
    """No invented hotel/flight facts not grounded in tool results."""
    return GEval(
        name="Fact Grounding",
        criteria=(
            "Penalize the actual output if it invents specific hotel or flight "
            "names, prices, times, or availability that a real tool call would "
            "supply. Generic guidance is fine; fabricated concrete facts are not."
        ),
        evaluation_params=_IO,
        threshold=DEFAULT_THRESHOLD,
        model=JUDGE_MODEL,
    )


def format_quality_metric() -> GEval:
    """Important info emphasized, tidy structure, tasteful emoji (MIN-54)."""
    return GEval(
        name="Format Quality",
        criteria=(
            "Judge ONLY presentation and formatting: important information (prices, "
            "dates, hotel/flight names) emphasized with bold, tidy structure (short "
            "paragraphs or lists), and tasteful emoji — not a dense wall of plain "
            "text. Do NOT penalize the answer's completeness, item count, or whether "
            "it fully covers the request's scope (e.g. returning fewer items than "
            "asked); those are out of scope for this formatting rubric."
        ),
        evaluation_params=_IO,
        threshold=DEFAULT_THRESHOLD,
        model=JUDGE_MODEL,
    )


def tool_correctness_metric() -> ToolCorrectnessMetric:
    """Deterministic: compares tools_called vs expected_tools (MIN-46). No judge."""
    return ToolCorrectnessMetric()


# Registry: metric-name -> factory. Runners select by dataset needs.
GEVAL_METRICS = {
    "response_language": response_language_metric,
    "search_vs_booking": search_vs_booking_metric,
    "no_hallucination": no_hallucination_metric,
    "format_quality": format_quality_metric,
}
