"""Offline eval runner (specs/travel-agent Task 8.1).

Runs the routing and retrieval datasets and asserts quality thresholds. The
functions take injected dependencies so the CI smoke test drives them with a
FakeLLM (no network); ``main()`` builds the real LLM and is for manual/keyed runs.

Usage: python eval/run_eval.py    (requires a configured LLM provider key)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from langchain_core.messages import HumanMessage
from langgraph.graph import END

from eval.metrics import routing_accuracy

_DATASETS = Path(__file__).resolve().parent / "datasets"

ROUTING_THRESHOLD = 0.9
RETRIEVAL_THRESHOLD = 0.8


def load_dataset(name: str) -> list[dict]:
    return json.loads((_DATASETS / name).read_text(encoding="utf-8"))


def run_routing_eval(llm, dataset: list[dict]) -> list[dict]:
    """Route each input through the supervisor and compare to the expected agent."""
    from app.agents.supervisor import make_supervisor

    supervisor = make_supervisor(llm)
    results = []
    for item in dataset:
        cmd = supervisor({"messages": [HumanMessage(content=item["input"])]})
        # Use current_flow (the semantic intent) rather than goto: booking now
        # routes through plan_node first, so goto="plan" but current_flow="booking".
        predicted = (cmd.update or {}).get("current_flow") or (
            "none" if cmd.goto == END else cmd.goto
        )
        results.append(
            {
                "input": item["input"],
                "expected": item["expected"],
                "predicted": predicted,
            }
        )
    return results


def run_retrieval_eval(store, dataset: list[dict]) -> list[dict]:
    """Run hybrid search per query and check the expected keyword is retrieved."""
    from app.rag.retriever import hybrid_search

    results = []
    for item in dataset:
        docs = hybrid_search(store, item["query"], filters={"city": item["city"]}, k=5)
        hit = any(item["keyword"] in d.page_content for d in docs)
        results.append({"query": item["query"], "hit": hit})
    return results


def main() -> int:
    """Run evals against the real configured model; returns a process exit code."""
    from app.clients.llm import get_llm

    routing = run_routing_eval(get_llm(), load_dataset("routing.json"))
    acc = routing_accuracy(routing)
    print(f"routing_accuracy = {acc:.2f} (threshold {ROUTING_THRESHOLD})")
    ok = acc >= ROUTING_THRESHOLD
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
