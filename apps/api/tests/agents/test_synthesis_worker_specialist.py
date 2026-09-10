"""The synthesis worker must carry its specialist name into the inner config.

The inner sub-graph's checkpoint namespace is ``synthesis_worker:<uuid>|
assistant:<uuid>`` — it has no specialist segment — so the config metadata is
the only channel that reaches ``on_chat_model_start`` / ``on_tool_start``. The
merge must not drop the caller's own metadata keys.
"""

import asyncio
from types import SimpleNamespace

from app.agents.subagents.synthesis_worker import (
    _AGENT_BUILDERS,
    build_synthesis_worker,
)
from langchain_core.messages import AIMessage, HumanMessage


class _CapturingGraph:
    """A compiled-graph stand-in that records the config it is invoked with."""

    def __init__(self) -> None:
        self.captured_config = None

    # The worker awaits the sub-agent (#178: the specialists bind async-only
    # tools), so the capture point is the async entry point.
    async def ainvoke(self, state: dict, config=None) -> dict:
        self.captured_config = config
        return {**state, "messages": [AIMessage(content="Here are the facts.")]}


def _state(agent: str) -> dict:
    return {
        "messages": [HumanMessage(content="plan a trip and find a hotel")],
        "task": {"agent": agent, "index": 0},
        "trip_id": None,
        "awaiting_user": False,
    }


def test_worker_passes_specialist_and_keeps_caller_metadata(monkeypatch):
    """The inner invoke gets specialist metadata merged onto the caller's."""
    graph = _CapturingGraph()
    monkeypatch.setitem(_AGENT_BUILDERS, "concierge", lambda _resolve: graph)

    worker = build_synthesis_worker(lambda _name, _hint=None: None)
    runtime = SimpleNamespace(
        config={
            "configurable": {"thread_id": "t-1"},
            "metadata": {"langgraph_node": "synthesis_worker", "run_id": "r-1"},
        }
    )

    asyncio.run(worker(_state("concierge"), runtime))

    config = graph.captured_config
    assert config is not None
    assert config["metadata"]["specialist"] == "concierge"
    # The regression that matters: the caller's own metadata must survive.
    assert config["metadata"]["langgraph_node"] == "synthesis_worker"
    assert config["metadata"]["run_id"] == "r-1"
    assert config["configurable"] == {"thread_id": "t-1"}


def test_worker_adds_specialist_when_caller_has_no_metadata(monkeypatch):
    """A config without metadata still gets a specialist key."""
    graph = _CapturingGraph()
    monkeypatch.setitem(_AGENT_BUILDERS, "planner", lambda _resolve: graph)

    worker = build_synthesis_worker(lambda _name, _hint=None: None)

    asyncio.run(worker(_state("planner"), SimpleNamespace(config=None)))

    assert graph.captured_config["metadata"] == {"specialist": "planner"}


def test_unknown_specialist_returns_command_without_invoking(monkeypatch):
    """The unknown-specialist early return never builds or invokes a sub-agent."""

    def _explode(_resolve):  # pragma: no cover - must never run
        raise AssertionError("builder must not be called for an unknown specialist")

    monkeypatch.setitem(_AGENT_BUILDERS, "nope", _explode)

    worker = build_synthesis_worker(lambda _name, _hint=None: None)
    cmd = asyncio.run(
        worker(_state("mystery"), SimpleNamespace(config={"metadata": {"a": 1}}))
    )

    result = cmd.update["task_results"][0]
    assert result["agent"] == "mystery"
    assert "Unknown specialist" in result["findings"]
