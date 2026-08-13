"""Multi-intent dispatch node — ``dispatch_next`` (MIN-65 DESIGN D4, PLAN 5.1).

Covers:
- Two queued intents run sequentially in one turn, then reflection.
- Single-intent (the common case, ``pending_flows == []``) behaves exactly as
  before this task — straight to reflection.
- Reflection's REVISE loop-back re-enters ``dispatch_next`` with an already
  empty queue, so it falls straight through to reflection again (no infinite
  loop, no re-triggering the drained secondary intent).
- The plan/HITL booking detour keeps its own topology untouched.
"""

from app.agents.graph import build_graph
from app.agents.supervisor import SupervisorIntent
from app.clients.llm import FakeLLM
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore


def _build(structured_responses, main_responses, fast_responses):
    main = FakeLLM(structured_responses=structured_responses, responses=main_responses)
    fast = FakeLLM(responses=fast_responses)
    return build_graph(
        llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=InMemoryStore()
    )


def _invoke(graph, msg: str, thread_id: str):
    return graph.invoke(
        {
            "messages": [HumanMessage(content=msg)],
            "user_id": "u1",
            "trip_id": None,
        },
        {"configurable": {"thread_id": thread_id}},
    )


def test_two_intents_run_in_parallel_then_synthesize():
    # GH-117 Path A: two intents are dispatched to parallel synthesis workers,
    # then a synthesizer combines their findings into one final answer.
    graph = _build(
        structured_responses=[
            SupervisorIntent(target_agent="planner", secondary_agent="concierge")
        ],
        main_responses=["flights found", "here's what to see", "combined answer"],
        fast_responses=["OK"],
    )
    out = _invoke(
        graph, "flights to Tokyo and things to do there", thread_id="t-multi-1"
    )

    assert out["current_flow"] == "synthesis"

    # Both specialists contributed structured findings.
    agents = {r["agent"] for r in out.get("task_results", [])}
    assert agents == {"planner", "concierge"}

    # The final assistant message is the synthesized answer.
    contents = [m.content for m in out["messages"] if isinstance(m, AIMessage)]
    assert "combined answer" in contents


def test_single_intent_goes_straight_to_reflection_unchanged():
    graph = _build(
        structured_responses=[SupervisorIntent(target_agent="concierge")],
        main_responses=["here you go"],
        fast_responses=["OK"],
    )
    out = _invoke(graph, "what to see in Tokyo?", thread_id="t-single-1")

    assert out["current_flow"] == "concierge"
    assert out["pending_flows"] == []
    assert any("here you go" in (m.content or "") for m in out["messages"])
    # Only one sub-agent answer in the transcript — no secondary intent ran.
    ai_answers = [m.content for m in out["messages"] if m.content == "here you go"]
    assert len(ai_answers) == 1


def test_reflection_revise_loop_does_not_retrigger_drained_secondary():
    # Single intent (no secondary) so pending_flows is drained (stays []) from
    # the first dispatch_next pass; reflection then REVISEs once before
    # accepting, and dispatch_next must not re-queue anything on the replay.
    graph = _build(
        structured_responses=[SupervisorIntent(target_agent="planner")],
        main_responses=["first draft", "revised draft"],
        fast_responses=["REVISE", "OK"],
    )
    out = _invoke(graph, "plan my trip", thread_id="t-revise-1")

    assert out["current_flow"] == "planner"
    assert out["pending_flows"] == []
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

    resumed = graph.invoke(
        Command(resume={"approved": True}),
        {"configurable": {"thread_id": cfg_thread}},
    )
    assert not resumed.get("__interrupt__")
    assert any("Hotel booked" in (m.content or "") for m in resumed["messages"])
    # No secondary intent was ever queued for booking — dispatch_next falls
    # straight through to reflection exactly as the old direct edge did.
    assert resumed["pending_flows"] == []
