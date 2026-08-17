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

from eval.metrics import plan_accuracy, routing_accuracy, task_accuracy

_DATASETS = Path(__file__).resolve().parent / "datasets"

ROUTING_THRESHOLD = 0.9
PLAN_THRESHOLD = 0.8


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
        # GH-117 Path A: supervisor no longer uses Command(goto=...); an empty
        # goto (or END) means the turn ends without routing to a sub-agent.
        goto = cmd.goto
        has_routing = isinstance(goto, str) and goto != END
        predicted = (cmd.update or {}).get("current_flow") or (
            "none" if not has_routing else goto
        )
        results.append(
            {
                "input": item["input"],
                "expected": item["expected"],
                "predicted": predicted,
            }
        )
    return results


def _predicted_agent(cmd) -> str:
    """Extract the semantic target agent from a supervisor Command.

    GH-117 Path A: the supervisor no longer uses ``Command(goto=...)``.
    ``current_flow`` is the canonical target; an empty update or empty goto
    means the turn ends without a specialist.
    """
    goto = cmd.goto
    has_routing = isinstance(goto, str) and goto != END
    return (cmd.update or {}).get("current_flow") or (
        "none" if not has_routing else goto
    )


def run_plan_eval(llm, dataset: list[dict]) -> list[dict]:
    """Route each multi-intent input and capture the ordered plan (P1 / Path A).

    Records both the legacy ``pending_flows`` and the new ``tasks`` emitted by
    the supervisor, so metrics can grade either decomposition path.
    """
    from app.agents.supervisor import make_supervisor

    supervisor = make_supervisor(llm)
    runtime = SimpleNamespace(context=AgentContext())
    results = []
    for item in dataset:
        cmd = supervisor({"messages": [HumanMessage(content=item["input"])]}, runtime)
        update = cmd.update or {}
        tasks = update.get("tasks") or []
        predicted_tasks = [t["agent"] for t in tasks]
        results.append(
            {
                "input": item["input"],
                "expected": item["expected"],
                "predicted": _predicted_agent(cmd),
                "expected_plan": item.get("expected_plan", []),
                "predicted_plan": update.get("pending_flows") or [],
                "expected_tasks": [item["expected"], *item.get("expected_plan", [])],
                "predicted_tasks": predicted_tasks,
            }
        )
    return results


def main() -> int:
    """Run evals against the real configured model; returns a process exit code."""
    from app.clients.llm import get_llm

    llm = get_llm()
    routing = run_routing_eval(llm, load_dataset("routing.json"))
    acc = routing_accuracy(routing)
    plan = run_plan_eval(llm, load_dataset("multi_intent.json"))
    pacc = plan_accuracy(plan)
    tacc = task_accuracy(plan)
    print(f"routing_accuracy = {acc:.2f} (threshold {ROUTING_THRESHOLD})")
    print(f"plan_accuracy = {pacc:.2f} (threshold {PLAN_THRESHOLD})")
    print(f"task_accuracy = {tacc:.2f} (Path A tasks)")
    ok = acc >= ROUTING_THRESHOLD and pacc >= PLAN_THRESHOLD
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
