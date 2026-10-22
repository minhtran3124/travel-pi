"""Multi-intent routing via ``route_tasks``: parallel fan-out then synthesize, single-intent straight-through, and the REVISE loop-back."""

import asyncio
from typing import Any

from app.agents.constants import TASK_NOTE_PREAMBLE
from app.agents.graph import build_graph
from app.agents.nodes import route_tasks
from app.agents.supervisor import SupervisorIntent
from app.clients.llm import FakeLLM
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Send


def _drive(graph, *args, **kwargs):
    """Run the graph asynchronously, as production does: ``synthesis_worker`` is async-only and ``graph.invoke`` cannot execute it."""
    return asyncio.run(graph.ainvoke(*args, **kwargs))


def _build(structured_responses, main_responses, fast_responses):
    main = FakeLLM(structured_responses=structured_responses, responses=main_responses)
    fast = FakeLLM(responses=fast_responses)
    return build_graph(
        llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=InMemoryStore()
    )


def _invoke(graph, msg: str, thread_id: str):
    return _drive(
        graph,
        {
            "messages": [HumanMessage(content=msg)],
            "user_id": "u1",
            "trip_id": None,
        },
        {"configurable": {"thread_id": thread_id}},
    )


def test_two_intents_run_in_parallel_then_synthesize():
    graph = _build(
        structured_responses=[
            SupervisorIntent(target_agent="planner", plan=["concierge"])
        ],
        main_responses=["flights found", "here's what to see", "combined answer"],
        fast_responses=["OK"],
    )
    out = _invoke(
        graph, "flights to Tokyo and things to do there", thread_id="t-multi-1"
    )

    assert out["current_flow"] == "synthesize"

    agents = {r["agent"] for r in out.get("task_results", [])}
    assert agents == {"planner", "concierge"}

    contents = [m.content for m in out["messages"] if isinstance(m, AIMessage)]
    assert "combined answer" in contents


def test_reflection_revise_after_synthesis_re_enters_synthesize():
    # The synthesize node must set current_flow to its own node name, or the REVISE
    # loop-back goto lands on an undeclared label and LangGraph silently drops it.
    graph = _build(
        structured_responses=[
            SupervisorIntent(target_agent="planner", plan=["concierge"])
        ],
        main_responses=[
            "flights found",
            "here's what to see",
            "synth v1",
            "synth v2",
        ],
        fast_responses=["REVISE", "OK"],
    )
    out = _invoke(
        graph, "flights to Tokyo and things to do there", thread_id="t-synth-revise"
    )

    assert out["current_flow"] == "synthesize"
    assert out["revisions"] == 1

    ai_contents = [m.content for m in out["messages"] if isinstance(m, AIMessage)]
    assert "synth v2" in ai_contents

    # The internal revise note must not be the final persisted message.
    assert not (
        isinstance(out["messages"][-1], SystemMessage)
        and "improve your previous answer" in out["messages"][-1].content
    )


def test_route_tasks_passes_parent_state_to_parallel_workers():
    # Send must carry the parent state because LangGraph does not merge it automatically.
    state = {
        "tasks": [
            {"agent": "planner", "query": "find flights", "index": 0},
            {"agent": "concierge", "query": "check weather", "index": 1},
        ],
        "messages": [HumanMessage(content="flights and weather in Tokyo")],
        "user_id": "u1",
        "trip_id": "trip-123",
        "language": "en",
        "trip_context": "Active trip: Tokyo",
    }
    sends = route_tasks(state)
    assert len(sends) == 2
    assert all(isinstance(s, Send) and s.node == "synthesis_worker" for s in sends)
    for send, task in zip(sends, state["tasks"], strict=True):
        assert send.arg["task"] == task
        assert send.arg["messages"] == state["messages"]
        assert send.arg["user_id"] == state["user_id"]
        assert send.arg["trip_id"] == state["trip_id"]
        assert send.arg["language"] == state["language"]
        assert send.arg["trip_context"] == state["trip_context"]


def test_single_intent_goes_straight_to_reflection_unchanged():
    graph = _build(
        structured_responses=[SupervisorIntent(target_agent="concierge")],
        main_responses=["here you go"],
        fast_responses=["OK"],
    )
    out = _invoke(graph, "what to see in Tokyo?", thread_id="t-single-1")

    assert out["current_flow"] == "concierge"
    assert any("here you go" in (m.content or "") for m in out["messages"])
    # Only one sub-agent answer in the transcript — no secondary intent ran.
    ai_answers = [m.content for m in out["messages"] if m.content == "here you go"]
    assert len(ai_answers) == 1


def test_reflection_revise_loop_does_not_retrigger_drained_secondary():
    # The REVISE loop must re-enter only the same sub-agent — no drained secondary is re-run.
    graph = _build(
        structured_responses=[SupervisorIntent(target_agent="planner")],
        main_responses=["first draft", "revised draft"],
        fast_responses=["REVISE", "OK"],
    )
    out = _invoke(graph, "plan my trip", thread_id="t-revise-1")

    assert out["current_flow"] == "planner"
    assert out["revisions"] == 1

    contents = [m.content for m in out["messages"]]
    assert "first draft" in contents
    assert "revised draft" in contents
    # Exactly one revise note was injected — the loop ran once, not forever.
    revise_notes = [
        m
        for m in out["messages"]
        if isinstance(m, SystemMessage) and "improve your previous answer" in m.content
    ]
    assert len(revise_notes) == 1


def test_booking_hitl_detour_untouched_by_dispatch():
    from langgraph.types import Command

    graph = _build(
        structured_responses=[SupervisorIntent(target_agent="booking")],
        main_responses=["Hotel booked!"],
        fast_responses=["OK"],
    )
    cfg_thread = "t-booking-detour-1"
    first = _invoke(graph, "book me a hotel in Paris", thread_id=cfg_thread)
    assert first.get("__interrupt__"), "booking must still pause at plan_node"

    resumed = _drive(
        graph,
        Command(resume={"approved": True}),
        {"configurable": {"thread_id": cfg_thread}},
    )
    assert not resumed.get("__interrupt__")
    assert any("Hotel booked" in (m.content or "") for m in resumed["messages"])


def test_task_results_cleared_between_turns():
    # task_results must not leak between turns — load_context_node resets them each turn.
    graph = _build(
        structured_responses=[
            SupervisorIntent(target_agent="planner", plan=["concierge"]),
            SupervisorIntent(target_agent="concierge"),
        ],
        main_responses=[
            "flights found",
            "here's what to see",
            "combined answer",
            "sunny today",
        ],
        fast_responses=["OK", "OK"],
    )
    thread_id = "t-clear-results"
    first = _invoke(
        graph, "flights to Tokyo and things to do there", thread_id=thread_id
    )
    assert {r["agent"] for r in first.get("task_results", [])} == {
        "planner",
        "concierge",
    }

    second = _invoke(graph, "what's the weather in Tokyo?", thread_id=thread_id)
    assert second["current_flow"] == "concierge"
    assert second.get("task_results") == []


class CapturingFakeLLM(FakeLLM):
    """FakeLLM that records every message list the model actually receives."""

    seen: list = []

    def _generate(self, messages, stop=None, run_manager=None, **kwargs: Any):
        self.seen.append(list(messages))
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def test_fan_out_workers_receive_distinct_task_notes():
    # Each parallel worker's model sees its own task folded into the leading
    # SystemMessage, and no task note is checkpointed in the thread.
    main = CapturingFakeLLM(
        structured_responses=[
            SupervisorIntent(
                target_agent="planner",
                plan=["concierge"],
                task_queries=["find flights", "check visa"],
            )
        ],
        responses=["flights found", "visa info", "combined answer"],
        seen=[],
    )
    graph = build_graph(
        llm=main,
        fast_llm=FakeLLM(responses=["OK"]),
        checkpointer=MemorySaver(),
        store=InMemoryStore(),
    )
    thread_id = "t-fan-out-notes"
    _invoke(graph, "flights to Tokyo and do I need a visa", thread_id=thread_id)

    notes = [
        str(call[0].content)
        for call in main.seen
        if isinstance(call[0], SystemMessage)
        and TASK_NOTE_PREAMBLE in str(call[0].content)
    ]
    assert any(n.endswith("find flights") for n in notes)
    assert any(n.endswith("check visa") for n in notes)

    thread = graph.get_state({"configurable": {"thread_id": thread_id}}).values[
        "messages"
    ]
    assert not any(TASK_NOTE_PREAMBLE in str(m.content) for m in thread)
