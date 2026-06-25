"""Evaluation metrics (specs/travel-agent Task 8.1).

Pure scoring helpers (no network) for routing accuracy and retrieval hit-rate,
plus an optional RAGAS faithfulness wrapper used only by real-model runs.
"""

from __future__ import annotations


def routing_accuracy(results: list[dict]) -> float:
    """Fraction of routing results where predicted == expected agent."""
    if not results:
        return 0.0
    correct = sum(1 for r in results if r["predicted"] == r["expected"])
    return correct / len(results)


def retrieval_hit_rate(results: list[dict]) -> float:
    """Fraction of retrieval results that returned the expected document."""
    if not results:
        return 0.0
    return sum(1 for r in results if r["hit"]) / len(results)


def ragas_faithfulness(samples: list[dict]) -> float:
    """RAGAS faithfulness over (question, answer, contexts) samples.

    Only usable with a real judge LLM + ragas installed; raises otherwise. Not
    exercised by the CI smoke test (which has no API key).
    """
    from ragas import evaluate  # noqa: PLC0415
    from ragas.metrics import faithfulness  # noqa: PLC0415

    result = evaluate(samples, metrics=[faithfulness])
    return float(result["faithfulness"])
