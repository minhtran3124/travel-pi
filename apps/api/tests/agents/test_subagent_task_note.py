"""Specialists receive the supervisor's task note as their last model input (SC-5/SC-6)."""

import asyncio
import types
from typing import Any

from app.agents.constants import TASK_NOTE_PREAMBLE
from app.agents.subagents.planner import build_planner
from app.agents.subagents.synthesis_worker import build_synthesis_worker
from app.clients.llm import FakeLLM
from langchain_core.messages import HumanMessage, SystemMessage

QUERY = "find flights to Tokyo"


class CapturingFakeLLM(FakeLLM):
    """FakeLLM that records every message list the model actually receives."""

    seen: list = []

    def _generate(self, messages, stop=None, run_manager=None, **kwargs: Any):
        self.seen.append(list(messages))
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def _llm() -> CapturingFakeLLM:
    return CapturingFakeLLM(responses=["Here are some flights."], seen=[])


def _is_note(msg) -> bool:
    return isinstance(msg, SystemMessage) and str(msg.content).startswith(
        TASK_NOTE_PREAMBLE
    )


def _run_planner(llm, **extra):
    graph = build_planner(lambda hint=None: llm)
    state = {"messages": [HumanMessage(content="I want to go to Tokyo")], **extra}
    return asyncio.run(graph.ainvoke(state))


def _task():
    return {"agent": "planner", "query": QUERY, "index": 0}


def test_single_intent_receives_note():
    llm = _llm()
    _run_planner(llm, tasks=[_task()])
    assert llm.seen
    last = llm.seen[-1][-1]
    assert _is_note(last)
    assert str(last.content).endswith(QUERY)


def test_fan_out_receives_note():
    llm = _llm()
    worker = build_synthesis_worker(lambda name, hint=None: llm)
    state = {
        "task": _task(),
        "messages": [HumanMessage(content="I want to go to Tokyo")],
        "user_id": "u1",
        "trip_id": None,
    }
    runtime = types.SimpleNamespace(context=None, config={})
    asyncio.run(worker(state, runtime))
    assert llm.seen
    last = llm.seen[-1][-1]
    assert _is_note(last)
    assert str(last.content).endswith(QUERY)


def test_note_not_persisted():
    llm = _llm()
    result = _run_planner(llm, tasks=[_task()])
    assert llm.seen and _is_note(llm.seen[-1][-1])
    assert not any(_is_note(m) for m in result["messages"])


def test_no_task_no_note():
    llm = _llm()
    _run_planner(llm)
    assert llm.seen
    last = llm.seen[-1][-1]
    assert isinstance(last, HumanMessage)
