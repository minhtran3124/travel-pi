"""Specialists receive the supervisor's task folded into their single leading system message (SC-5/SC-6)."""

import asyncio
import types
from typing import Any

from app.agents.constants import REFLECTION_REVISE_NOTE, TASK_NOTE_PREAMBLE
from app.agents.subagents.planner import build_planner
from app.agents.subagents.synthesis_worker import build_synthesis_worker
from app.clients.llm import FakeLLM
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

QUERY = "find flights to Tokyo"


class CapturingFakeLLM(FakeLLM):
    """FakeLLM that records every message list the model actually receives."""

    seen: list = []

    def _generate(self, messages, stop=None, run_manager=None, **kwargs: Any):
        self.seen.append(list(messages))
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def _llm(responses=None) -> CapturingFakeLLM:
    return CapturingFakeLLM(responses=responses or ["Here are some flights."], seen=[])


def _systems(call) -> list[SystemMessage]:
    return [m for m in call if isinstance(m, SystemMessage)]


def _assert_single_leading_system_with_task(call) -> None:
    systems = _systems(call)
    assert len(systems) == 1, "expected exactly one SystemMessage"
    assert call[0] is systems[0], "the SystemMessage must lead the input"
    content = str(systems[0].content)
    assert TASK_NOTE_PREAMBLE in content
    assert content.endswith(QUERY)


def _run_planner(llm, messages=None, **extra):
    graph = build_planner(lambda hint=None: llm)
    state = {
        "messages": messages or [HumanMessage(content="I want to go to Tokyo")],
        **extra,
    }
    return asyncio.run(graph.ainvoke(state))


def _task():
    return {"agent": "planner", "query": QUERY, "index": 0}


def test_single_intent_receives_note():
    llm = _llm()
    _run_planner(llm, tasks=[_task()])
    assert llm.seen
    _assert_single_leading_system_with_task(llm.seen[-1])


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
    _assert_single_leading_system_with_task(llm.seen[-1])


def test_note_not_persisted():
    llm = _llm()
    result = _run_planner(llm, tasks=[_task()])
    assert llm.seen
    assert not any(TASK_NOTE_PREAMBLE in str(m.content) for m in result["messages"])


def test_no_task_no_note():
    llm = _llm()
    _run_planner(llm)
    assert llm.seen
    assert not any(TASK_NOTE_PREAMBLE in str(m.content) for m in llm.seen[-1])


def test_tool_round_keeps_tool_result_last():
    tool_call = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "needs_clarification",
                "args": {"question": "Which dates?"},
                "id": "c1",
            }
        ],
    )
    llm = _llm([tool_call, "Here are some flights."])
    _run_planner(llm, tasks=[_task()])
    assert len(llm.seen) >= 2, "expected a second model call after the tool round"
    second = llm.seen[1]
    assert isinstance(second[-1], ToolMessage)
    _assert_single_leading_system_with_task(second)


def test_revise_note_stays_last():
    llm = _llm()
    history = [
        HumanMessage(content="I want to go to Tokyo"),
        AIMessage(content="Draft answer."),
        SystemMessage(content=REFLECTION_REVISE_NOTE),
    ]
    _run_planner(llm, messages=history, tasks=[_task()])
    assert llm.seen
    call = llm.seen[-1]
    assert isinstance(call[-1], SystemMessage)
    assert call[-1].content == REFLECTION_REVISE_NOTE
    # The history carries reflection's own system note by design (as on main);
    # only the FIRST system message may carry the task.
    systems = _systems(call)
    assert call[0] is systems[0]
    assert TASK_NOTE_PREAMBLE in str(systems[0].content)
    assert not any(TASK_NOTE_PREAMBLE in str(s.content) for s in systems[1:])
