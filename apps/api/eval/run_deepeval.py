"""Keyed DeepEval runner for the offline eval harness (MIN-58).

Skips gracefully when no real OpenAI judge key is present (the repo ships a fake
`OPENAI_API_KEY=test`, and CI has no network) so this never breaks a no-key run.
`main()` is manual/keyed only; it is NOT wired into CI in this ticket.
"""

from __future__ import annotations

import os
import sys

_PLACEHOLDER_KEYS = {"", "test", "changeme", "placeholder"}


def has_real_openai_key() -> bool:
    """True only when OPENAI_API_KEY is set to a non-placeholder value."""
    return (
        os.environ.get("OPENAI_API_KEY") or ""
    ).strip().lower() not in _PLACEHOLDER_KEYS


def build_test_cases(graph, datasets: dict[str, list[dict]]) -> list:
    """Run each case through the graph → LLMTestCases, skipping empty replies.

    A case whose final reply is empty — e.g. a HITL plan-approval interrupt that
    pauses before any assistant text — is dropped and logged: GEval rejects an
    empty ``actual_output`` (``MissingTestCaseParamsError``). Each case gets a
    globally-unique index → unique checkpointer thread id (no cross-case bleed).
    """
    from eval.harness import run_case

    cases = []
    index = 0
    for items in datasets.values():
        for case in items:
            test_case = run_case(graph, case, index).test_case
            index += 1
            if (test_case.actual_output or "").strip():
                cases.append(test_case)
            else:
                print(f"[eval] skip (empty reply): {case['input'][:60]}")
    return cases


def tool_cases(cases: list) -> list:
    """Cases that declare expected tools — the only ones ToolCorrectness should score.

    ``ToolCorrectnessMetric`` on a case with no ``expected_tools`` penalizes any
    real tool call, which is a category error for non-tool cases. Restrict it.
    """
    return [tc for tc in cases if tc.expected_tools]


def main() -> int:
    """Keyed run: build real graph + judge, evaluate, return process exit code."""
    if not has_real_openai_key():
        print("[eval] SKIP: no real OPENAI_API_KEY (judge) — set one to run DeepEval.")
        return 0

    from deepeval import evaluate

    from eval.harness import build_eval_graph
    from eval.loader import load_all
    from eval.metrics_geval import GEVAL_METRICS, tool_correctness_metric

    graph = build_eval_graph()
    test_cases = build_test_cases(graph, load_all())
    if not test_cases:
        print("[eval] no scorable cases (all replies empty).")
        return 0

    # G-Eval rubrics (language / intent / grounding / format) apply to every reply.
    evaluate(test_cases=test_cases, metrics=[f() for f in GEVAL_METRICS.values()])

    # ToolCorrectness only where the case declares expected tools, else it
    # penalizes legitimate tool calls on cases that never specified any.
    scored_for_tools = tool_cases(test_cases)
    if scored_for_tools:
        evaluate(test_cases=scored_for_tools, metrics=[tool_correctness_metric()])
    return 0


if __name__ == "__main__":
    sys.exit(main())
