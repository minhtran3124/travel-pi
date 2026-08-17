"""Evaluation metrics (specs/travel-agent Task 8.1).

Pure scoring helpers (no network) for routing accuracy.
"""

from __future__ import annotations


def routing_accuracy(results: list[dict]) -> float:
    """Fraction of routing results where predicted == expected agent."""
    if not results:
        return 0.0
    correct = sum(1 for r in results if r["predicted"] == r["expected"])
    return correct / len(results)


def plan_accuracy(results: list[dict]) -> float:
    """Fraction of multi-intent results whose ordered ledger matches (P1).

    A case is correct only if BOTH the primary target and the ordered follow-on
    ``plan`` match — order matters, so ``["concierge", "planner"]`` is not the
    same as ``["planner", "concierge"]``. Each result carries ``expected`` /
    ``predicted`` (target) and ``expected_plan`` / ``predicted_plan`` (ledger).
    """
    if not results:
        return 0.0
    correct = sum(
        1
        for r in results
        if r["predicted"] == r["expected"] and r["predicted_plan"] == r["expected_plan"]
    )
    return correct / len(results)


def task_accuracy(results: list[dict]) -> float:
    """Fraction of multi-intent results whose ordered ``tasks`` match (Path A).

    Same semantics as :func:`plan_accuracy`, but scores the new canonical
    ``tasks`` decomposition instead of the legacy ``pending_flows`` ledger.
    """
    if not results:
        return 0.0
    correct = sum(
        1
        for r in results
        if r["predicted_tasks"] == r["expected_tasks"]
    )
    return correct / len(results)
