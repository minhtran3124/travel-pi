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
    from app.agents.suggestions import suggestions_for_flow

    from eval.harness import run_case

    cases = []
    index = 0
    for items in datasets.values():
        for case in items:
            result = run_case(graph, case, index)
            test_case = result.test_case
            index += 1
            if (test_case.actual_output or "").strip():
                # Carry the case's declared rubrics so each G-Eval metric scores
                # only the cases that opted into it (see cases_for_metric).
                # Also attach the follow-up suggestion keys routed for this
                # case's final flow — suggestion_relevance's deterministic
                # layer checks them for non-emptiness + catalog membership,
                # and its GEval half reads them back via retrieval_context.
                keys = suggestions_for_flow(result.current_flow)
                test_case.metadata = {
                    **(test_case.metadata or {}),
                    "metrics": case.get("metrics", []),
                    "suggestions": keys,
                }
                test_case.retrieval_context = keys
                cases.append(test_case)
            else:
                preview = case.get("input") or " / ".join(case.get("turns", []))
                print(f"[eval] skip (empty reply): {preview[:60]}")
    return cases


def tool_cases(cases: list) -> list:
    """Cases that declare expected tools — the only ones ToolCorrectness should score.

    ``ToolCorrectnessMetric`` on a case with no ``expected_tools`` penalizes any
    real tool call, which is a category error for non-tool cases. Restrict it.
    """
    return [tc for tc in cases if tc.expected_tools]


def cases_for_metric(key: str, cases: list) -> list:
    """Cases that opted into the G-Eval rubric ``key`` via their ``metrics`` field.

    Applying every rubric to every case (the original behavior) is a category
    error — e.g. judging a weather question on search-vs-booking intent, or the
    booking case on search intent — which manufactured false negatives and a
    misleading denominator. Each rubric now scores only its declared cases.
    """
    return [tc for tc in cases if key in (tc.metadata or {}).get("metrics", [])]


def known_suggestion_keys() -> set:
    """All valid suggestion keys (``flow.subkey``) from the current catalog.

    Single source of truth: ``app.agents.suggestions._FLOW_SUGGESTIONS``. As
    MIN-65 task 6.1 grows the catalog, this membership check follows
    automatically — no change needed here.
    """
    from app.agents.suggestions import _FLOW_SUGGESTIONS

    return {key for keys in _FLOW_SUGGESTIONS.values() for key in keys}


def suggestion_relevance_deterministic(cases: list) -> dict:
    """Deterministic pass/fail for ``suggestion_relevance``: non-empty + known keys.

    Measures the ticket's acceptance criterion (>=80% of responses carry a
    relevant suggestion) without an LLM judge call. A case "passes" when its
    attached suggestions are non-empty AND every key belongs to the known
    catalog — an unknown/typo'd key is as much a failure as no suggestion.
    """
    catalog = known_suggestion_keys()
    scored = cases_for_metric("suggestion_relevance", cases)
    passed = 0
    for tc in scored:
        keys = (tc.metadata or {}).get("suggestions", [])
        if keys and all(k in catalog for k in keys):
            passed += 1
    total = len(scored)
    return {
        "total": total,
        "passed": passed,
        "rate": (passed / total) if total else 0.0,
    }


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

    # Each G-Eval rubric scores ONLY the cases that declare it in their `metrics`
    # field. The old code applied all four rubrics to all cases, judging (e.g.) a
    # weather question on search-vs-booking intent — a category error that
    # produced false negatives and an inflated-bad denominator.
    for key, factory in GEVAL_METRICS.items():
        subset = cases_for_metric(key, test_cases)
        if subset:
            evaluate(test_cases=subset, metrics=[factory()])
        else:
            print(f"[eval] no cases declare metric '{key}' — skipped.")

    # Deterministic suggestion_relevance layer: measures the ticket's AC
    # (>=80% of responses carry a relevant, catalog-valid suggestion) without
    # a judge call — runs independently of the GEval pass above.
    det = suggestion_relevance_deterministic(test_cases)
    if det["total"]:
        print(
            f"[eval] suggestion_relevance (deterministic): "
            f"{det['passed']}/{det['total']} ({det['rate']:.0%})"
        )

    # ToolCorrectness only where the case declares expected tools, else it
    # penalizes legitimate tool calls on cases that never specified any.
    scored_for_tools = tool_cases(test_cases)
    if scored_for_tools:
        evaluate(test_cases=scored_for_tools, metrics=[tool_correctness_metric()])
    return 0


if __name__ == "__main__":
    sys.exit(main())
