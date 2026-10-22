"""Synthesis worker must propagate tool-driven graph-state mutations to the parent while keeping the sub-agent's inner messages private."""

import asyncio
from types import SimpleNamespace

from app.agents.subagents.synthesis_worker import (
    _AGENT_BUILDERS,
    build_synthesis_worker,
)
from langchain_core.messages import AIMessage, HumanMessage


def _fake_subagent(mutated_state: dict):
    """Return a compiled-graph-like builder whose invoke() overlays ``mutated_state`` on the input state."""

    class FakeGraph:
        # The worker awaits the sub-agent, so the stand-in exposes async ainvoke.
        async def ainvoke(self, state: dict, config=None) -> dict:
            merged = dict(state)
            merged.update(mutated_state)
            return merged

    def builder(_resolve_model):
        return FakeGraph()

    return builder


def test_worker_propagates_trip_id_when_tool_creates_trip(monkeypatch):
    monkeypatch.setitem(
        _AGENT_BUILDERS,
        "planner",
        _fake_subagent(
            {
                "trip_id": "new-trip-id",
                "messages": [AIMessage(content="Created a new trip for you.")],
            }
        ),
    )

    worker = build_synthesis_worker(lambda _name, _hint=None: None)
    state = {
        "messages": [HumanMessage(content="plan a trip and check weather")],
        "task": {"agent": "planner", "index": 0},
        "trip_id": None,
        "awaiting_user": False,
    }
    runtime = SimpleNamespace(config=None)

    cmd = asyncio.run(worker(state, runtime))

    assert cmd.update["trip_id"] == "new-trip-id"
    assert cmd.update["task_results"][0]["findings"] == "Created a new trip for you."
    assert "messages" not in cmd.update


def test_worker_propagates_awaiting_user_when_tool_blocks(monkeypatch):
    monkeypatch.setitem(
        _AGENT_BUILDERS,
        "planner",
        _fake_subagent(
            {
                "awaiting_user": True,
                "messages": [AIMessage(content="What is your departure city?")],
            }
        ),
    )

    worker = build_synthesis_worker(lambda _name, _hint=None: None)
    state = {
        "messages": [HumanMessage(content="find flights and things to do")],
        "task": {"agent": "planner", "index": 0},
        "trip_id": None,
        "awaiting_user": False,
    }
    runtime = SimpleNamespace(config=None)

    cmd = asyncio.run(worker(state, runtime))

    assert cmd.update["awaiting_user"] is True
    assert cmd.update["task_results"][0]["findings"] == "What is your departure city?"
    assert "messages" not in cmd.update


def test_worker_does_not_overwrite_unchanged_state(monkeypatch):
    monkeypatch.setitem(
        _AGENT_BUILDERS,
        "concierge",
        _fake_subagent({"messages": [AIMessage(content="Sunny and warm.")]}),
    )

    worker = build_synthesis_worker(lambda _name, _hint=None: None)
    state = {
        "messages": [HumanMessage(content="plan a trip and check weather")],
        "task": {"agent": "concierge", "index": 1},
        "trip_id": "existing-trip-id",
        "awaiting_user": False,
    }
    runtime = SimpleNamespace(config=None)

    cmd = asyncio.run(worker(state, runtime))

    assert "trip_id" not in cmd.update
    assert "awaiting_user" not in cmd.update
    assert cmd.update["task_results"][0]["findings"] == "Sunny and warm."
