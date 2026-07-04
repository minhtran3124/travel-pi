"""Offline eval runner (specs/travel-agent Task 8.1).

Runs the routing dataset and asserts the quality threshold. The
functions take injected dependencies so the CI smoke test drives them with a
FakeLLM (no network); ``main()`` builds the real LLM and is for manual/keyed runs.

Usage: python eval/run_eval.py    (requires a configured LLM provider key)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

from app.agents.context import AgentContext
from langchain_core.messages import HumanMessage
from langgraph.graph import END

from eval.metrics import routing_accuracy

_DATASETS = Path(__file__).resolve().parent / "datasets"

ROUTING_THRESHOLD = 0.9


def load_dataset(name: str) -> list[dict]:
    return json.loads((_DATASETS / name).read_text(encoding="utf-8"))


def run_routing_eval(llm, dataset: list[dict]) -> list[dict]:
    """Route each input through the supervisor and compare to the expected agent."""
    from app.agents.supervisor import make_supervisor

    supervisor = make_supervisor(llm)
    # Default per-run context (no tier gating) — the supervisor now takes a Runtime.
    runtime = SimpleNamespace(context=AgentContext())
    results = []
    for item in dataset:
        cmd = supervisor({"messages": [HumanMessage(content=item["input"])]}, runtime)
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
