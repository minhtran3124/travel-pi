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
    """Run every case through the graph → list of LLMTestCase (needs a real graph/key)."""
    from eval.harness import run_case

    cases = []
    index = 0
    for items in datasets.values():
        for case in items:
            cases.append(run_case(graph, case, index).test_case)
            index += 1
    return cases


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
    metrics = [f() for f in GEVAL_METRICS.values()] + [tool_correctness_metric()]
    evaluate(test_cases=test_cases, metrics=metrics)
    return 0


if __name__ == "__main__":
    sys.exit(main())
