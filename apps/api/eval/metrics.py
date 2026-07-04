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
