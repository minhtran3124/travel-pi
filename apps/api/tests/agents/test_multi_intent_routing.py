"""Multi-intent dispatch node — ``dispatch_next`` (MIN-65 DESIGN D4, PLAN 5.1).

Covers:
- Two queued intents run sequentially in one turn, then the turn ends.
- Single-intent (the common case, ``pending_flows == []``) behaves exactly as
  before this task — straight to the end of the turn.
- The plan/HITL booking detour keeps its own topology untouched.
"""

from app.agents.graph import build_graph
from app.agents.supervisor import SupervisorIntent
from app.clients.llm import FakeLLM
from langchain_core.messages import HumanMessage, SystemMessage
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


def test_two_intents_run_sequentially_then_end():
    graph = _build(
        structured_responses=[
            SupervisorIntent(target_agent="planner", secondary_agent="concierge")
        ],
        main_responses=["flights found", "here's what to see"],
        fast_responses=["OK"],
    )
    out = _invoke(
        graph, "flights to Tokyo and things to do there", thread_id="t-multi-1"
    )

    # Both sub-agents ran, drained the queue, and ended the turn — current_flow
    # reflects the last (secondary) sub-agent to run.
    assert out["current_flow"] == "concierge"
    assert out["pending_flows"] == []

    contents = [m.content for m in out["messages"]]
    assert "flights found" in contents
    assert "here's what to see" in contents
    # Sequential: planner ran (and is visible in state) before concierge ran —
    # i.e. the second sub-agent saw the first one's message.
    assert contents.index("flights found") < contents.index("here's what to see")


def test_single_intent_goes_straight_to_end_unchanged():
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
    # straight through to END exactly as the old direct edge did.
    assert resumed["pending_flows"] == []
