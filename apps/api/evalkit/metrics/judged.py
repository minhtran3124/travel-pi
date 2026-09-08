"""Judge-based (G-Eval) eval metrics: temp-0, k-repeat averaged (task 2.3).

Ports 6 calibrated G-Eval rubrics from the original
``apps/api/eval/metrics_geval.py`` as **DATA** — ``RUBRICS`` below is the
whole rubric definition (criteria + evaluation params + threshold). A
project that wants different rubrics only supplies its own dict to
`make_judged_metric`/`make_all_judged_metrics`, never edits this module's
evaluation logic (`design-portability.md`).

Four (``response_language``, ``search_vs_booking``, ``format_quality``,
``no_hallucination``) are MIN-58's calibrated set. Two more
(``memory_recall``, ``suggestion_relevance``) were designed and registered
in MIN-65 task 1.2 (commit ``9c410e6``, since-removed
``eval/metrics_geval.py``) but never carried over when this module replaced
that file — several `eval/datasets/*.json` goldens (task 2.4) name them in
their ``metrics`` field, which used to crash a full run mid-flight with a
`KeyError` once the judged metrics ran. Ported here verbatim from that
commit; not re-derived.

Judge-variance control (`research-brief.md` §5/§6): the judge always runs at
**temperature 0**, and each `evaluate()` call repeats the judge call `k`
times and averages the scores; pass/fail is a threshold on the *averaged*
score, not a single noisy sample.

``no_hallucination`` previously had no ``retrieval_context`` wired (MIN-58
calibration finding), so its judge only saw input+output and the metric was
unusable. It is now grounded: `build_retrieval_context()` serializes every
captured `Trace.tool_calls[].output` into a readable string, and
``no_hallucination``'s rubric lists `RETRIEVAL_CONTEXT` in its
`evaluation_params` so the judge actually reads it.

``suggestion_relevance`` also requests `RETRIEVAL_CONTEXT`: the runner now
supplies the reply's follow-up suggestion keys via `Trace.meta["suggestions"]`,
and `build_retrieval_context()` appends one ``"suggestion: <key>"`` line per
entry alongside the serialized tool-call lines.

Import-time safety: constructing a `GEvalJudgedMetric` (and therefore
importing/registering this module) never builds a DeepEval `GEval` or
`GPTModel` object — that only happens lazily, inside `evaluate()`, via the
injected `geval_factory`. A keyless environment can safely import this
module; only actually *calling* `.evaluate()` needs a judge key, and that
call is the runner's (task 3.1) decision to make (it skips judged metrics
entirely, with a loud log, when no judge key is configured).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Protocol

from deepeval.metrics import GEval
from deepeval.models import GPTModel
from deepeval.test_case import LLMTestCase, SingleTurnParams

from evalkit.ports import Oracle
from evalkit.registry import register_metric
from evalkit.types import CheckResult, Golden, ToolCall, Trace

logger = logging.getLogger(__name__)

DEFAULT_JUDGE_MODEL = "gpt-4o-mini"
DEFAULT_THRESHOLD = 0.7
DEFAULT_TEMPERATURE = 0.0  # judge-variance control: always temp-0, never sampled hot

_IO = [SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT]
_IO_WITH_CONTEXT = [*_IO, SingleTurnParams.RETRIEVAL_CONTEXT]

# --- Rubric DATA (ported verbatim from eval/metrics_geval.py; MIN-58 calibrated
# criteria text — do not reword without re-running the calibration exercise in
# specs/min-58-eval-calibration/). Swapping rubrics for another project means
# supplying a different dict of this same shape, not editing the code below.

RUBRICS: dict[str, dict[str, Any]] = {
    "response_language": {
        "criteria": (
            "Determine whether the actual output is written in the SAME natural "
            "language as the input. If the input is Vietnamese, the answer must be "
            "Vietnamese; if English, English. Penalize any answer that switches "
            "language or mixes languages against the user's language."
        ),
        "evaluation_params": _IO,
        "threshold": DEFAULT_THRESHOLD,
    },
    "search_vs_booking": {
        "criteria": (
            "The input is a hotel/flight SEARCH or information request, not a "
            "confirmed booking. A good answer stays in search mode: it presents "
            "options/results, or — when nothing matches — clearly says none were "
            "found and offers to adjust the search (widen the budget, change the "
            "dates, relax filters). Reporting no results and offering to broaden "
            "the search is CORRECT behavior, not a failure. Penalize ONLY answers "
            "that push booking, ask for payment/passport/guest details, or assume "
            "the user already decided to book."
        ),
        "evaluation_params": _IO,
        "threshold": DEFAULT_THRESHOLD,
    },
    "no_hallucination": {
        "criteria": (
            "Penalize the actual output if it invents specific hotel or flight "
            "names, prices, times, or availability that a real tool call would "
            "supply. Generic guidance is fine; fabricated concrete facts are not."
        ),
        "evaluation_params": _IO_WITH_CONTEXT,
        "threshold": DEFAULT_THRESHOLD,
    },
    "format_quality": {
        "criteria": (
            "Judge ONLY presentation and formatting: important information (prices, "
            "dates, hotel/flight names) emphasized with bold, tidy structure (short "
            "paragraphs or lists), and tasteful emoji — not a dense wall of plain "
            "text. Do NOT penalize the answer's completeness, item count, or whether "
            "it fully covers the request's scope (e.g. returning fewer items than "
            "asked); those are out of scope for this formatting rubric."
        ),
        "evaluation_params": _IO,
        "threshold": DEFAULT_THRESHOLD,
    },
    "memory_recall": {
        "criteria": (
            "The conversation may already contain facts the traveller provided "
            "earlier (dates, party size/composition, destination, stated "
            "preferences). Penalize the actual output if it re-asks for a fact "
            "already given earlier in the input/conversation history. Asking "
            "about a genuinely NEW field that was never mentioned is CORRECT "
            "behavior and must NOT be penalized."
        ),
        "evaluation_params": _IO,
        "threshold": DEFAULT_THRESHOLD,
    },
    "suggestion_relevance": {
        "criteria": (
            "The retrieval context lists follow-up suggestion keys offered to "
            "the traveller after this reply; each key's final segment reads "
            "as a short EN action phrase (e.g. 'checkWeather' ~ 'Check "
            "weather'). Judge whether these suggested follow-ups are "
            "topically relevant to the input and actual output — i.e. things "
            "a traveller in this exact conversation would plausibly want to "
            "do next. Penalize suggestions that belong to an unrelated flow "
            "or topic."
        ),
        "evaluation_params": _IO_WITH_CONTEXT,
        "threshold": DEFAULT_THRESHOLD,
    },
}


class Judge(Protocol):
    """The slice of `deepeval.metrics.GEval` this module actually uses.

    Naming the seam as a `Protocol` (rather than depending on the concrete
    `GEval` type everywhere) is what makes `evaluate()` trivially testable
    offline: a test's stub judge only needs `.evaluate_params`, `.measure()`,
    and `.score`, never a real network call or judge key.
    """

    evaluation_params: list[SingleTurnParams] | None

    def measure(self, test_case: LLMTestCase) -> float: ...

    score: float | None


def build_retrieval_context(trace: Trace) -> list[str] | None:
    """Serialize every captured `Trace.tool_calls[].output` into a readable
    retrieval_context entry, e.g. ``"search_flights({...}) -> {...}"``, then
    append one ``"suggestion: <key>"`` entry per item in
    `trace.meta["suggestions"]` (the runner-supplied follow-up suggestion
    keys `suggestion_relevance` judges).

    Returns `None` (not `[]`) only when both are empty, so an unrelated
    conversational golden doesn't get an empty-but-present retrieval_context.
    """
    lines = [_tool_call_to_context_line(tc) for tc in trace.tool_calls]
    lines.extend(f"suggestion: {key}" for key in trace.meta.get("suggestions") or [])
    return lines or None


def _tool_call_to_context_line(tool_call: ToolCall) -> str:
    return f"{tool_call.name}({tool_call.args}) -> {tool_call.output}"


def build_geval(
    name: str,
    rubric: dict[str, Any],
    *,
    judge_model: str = DEFAULT_JUDGE_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
) -> GEval:
    """Build a temp-0 DeepEval `GEval` instance from one `RUBRICS` entry.

    This is the default `geval_factory` used in production; tests inject a
    stub factory instead so no `GPTModel`/judge is ever built offline.
    """
    model = GPTModel(model=judge_model, temperature=temperature)
    return GEval(
        name=name,
        criteria=rubric["criteria"],
        evaluation_params=rubric["evaluation_params"],
        threshold=rubric.get("threshold", DEFAULT_THRESHOLD),
        model=model,
    )


class GEvalJudgedMetric:
    """A registered `Metric` wrapping one G-Eval rubric: temp-0, k-repeat averaged.

    The underlying judge (a DeepEval `GEval`) is built lazily on first
    `evaluate()` call via `geval_factory`, then cached — never at
    construction/import time, so registering this metric never needs a judge
    key.
    """

    def __init__(
        self,
        name: str,
        rubric: dict[str, Any],
        *,
        k: int = 1,
        geval_factory: Callable[[str, dict[str, Any]], Judge] = build_geval,
    ) -> None:
        if k < 1:
            raise ValueError(f"k must be >= 1, got {k}")
        self.name = name
        self.rubric = rubric
        self.k = k
        self._geval_factory = geval_factory
        self._judge: Judge | None = None

    def _get_judge(self) -> Judge:
        if self._judge is None:
            logger.info("[judged] building judge for metric=%s k=%d", self.name, self.k)
            self._judge = self._geval_factory(self.name, self.rubric)
        return self._judge

    def _golden_input(self, golden: Golden) -> str:
        if golden.input is not None:
            return golden.input
        return golden.turns[-1] if golden.turns else ""

    def evaluate(
        self, golden: Golden, trace: Trace, oracle: Oracle | None = None
    ) -> CheckResult:
        if not trace.reply.strip():
            # DeepEval's GEval raises MissingTestCaseParamsError on an empty
            # actual_output. An empty reply is a legitimate trace here (a booking
            # golden stops at the HITL plan-approval interrupt), so there is
            # nothing for a rubric to grade — report not_applicable instead of
            # aborting the whole run minutes into a paid full suite.
            return CheckResult(
                name=self.name,
                passed=True,
                detail="not_applicable: empty reply (e.g. HITL interrupt) — judged metric skipped",
            )
        judge = self._get_judge()
        test_case = LLMTestCase(
            input=self._golden_input(golden),
            actual_output=trace.reply,
            retrieval_context=build_retrieval_context(trace),
        )
        scores = [judge.measure(test_case) for _ in range(self.k)]
        avg_score = sum(scores) / len(scores)
        threshold = self.rubric.get("threshold", DEFAULT_THRESHOLD)
        passed = avg_score >= threshold
        return CheckResult(
            name=self.name,
            passed=passed,
            score=avg_score,
            detail=(
                f"k={self.k} scores={[round(s, 3) for s in scores]} "
                f"avg={avg_score:.3f} threshold={threshold}"
            ),
        )


def make_judged_metric(
    name: str,
    *,
    k: int = 1,
    judge_model: str = DEFAULT_JUDGE_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
    rubrics: dict[str, dict[str, Any]] | None = None,
) -> GEvalJudgedMetric:
    """Factory for one project-configured judged metric instance.

    A project (or the runner, task 3.1) calls this with its own ``k``/model/
    temperature and re-registers the result via `register_metric` to
    override the k=1 default registered below — the same override pattern
    `deterministic.ToolArgsShapeMetric`/`make_tool_args_shape_metric` uses for
    project-supplied config.
    """
    rubrics = rubrics if rubrics is not None else RUBRICS
    rubric = rubrics[name]

    def factory(metric_name: str, r: dict[str, Any]) -> Judge:
        return build_geval(
            metric_name, r, judge_model=judge_model, temperature=temperature
        )

    return GEvalJudgedMetric(name, rubric, k=k, geval_factory=factory)


def make_all_judged_metrics(
    *,
    k: int = 1,
    judge_model: str = DEFAULT_JUDGE_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
    rubrics: dict[str, dict[str, Any]] | None = None,
) -> list[GEvalJudgedMetric]:
    """All judged metrics, configured identically — the runner's one-call entrypoint."""
    rubrics = rubrics if rubrics is not None else RUBRICS
    return [
        make_judged_metric(
            name, k=k, judge_model=judge_model, temperature=temperature, rubrics=rubrics
        )
        for name in rubrics
    ]


for _name in RUBRICS:
    register_metric(make_judged_metric(_name))
