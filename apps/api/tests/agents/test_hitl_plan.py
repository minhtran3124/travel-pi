"""HITL plan-approval interrupt tests (REVIEW.md M1).

Verifies that:
- A booking request pauses at plan_node with __interrupt__ in state.
- Resuming with approved=True proceeds to the booking sub-agent.
- Resuming with approved=False ends gracefully without booking.
- Non-booking flows complete without any interrupt.
"""

from app.agents.graph import build_graph
from app.agents.supervisor import SupervisorIntent
from app.clients.llm import FakeLLM
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command


def _build(intent_target: str, answer: str = "done", verdict: str = "OK"):
    main = FakeLLM(
        structured_responses=[SupervisorIntent(target_agent=intent_target)] * 6,
        responses=[answer] * 6,
    )
    fast = FakeLLM(responses=[verdict] * 6)
    return build_graph(
        llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=InMemoryStore()
    )


def _invoke(graph, msg: str, thread_id: str, **extra):
    return graph.invoke(
        {
            "messages": [HumanMessage(content=msg)],
            "user_id": "u1",
            "trip_id": None,
            **extra,
        },
        {"configurable": {"thread_id": thread_id}},
    )


# ---------------------------------------------------------------------------
# Booking flow: interrupt fires, then resumes
# ---------------------------------------------------------------------------


def test_booking_triggers_plan_interrupt():
    graph = _build(intent_target="booking", answer="Hotel booked!")
    result = _invoke(graph, "book me a hotel in Paris", thread_id="t-book-1")

    assert result.get("__interrupt__"), "graph must pause at plan_node for booking"
    payload = result["__interrupt__"][0].value
    assert payload["type"] == "plan_approval"
    assert "book me a hotel" in payload["draft"]


def test_booking_resume_approved_continues_to_booking():
    graph = _build(intent_target="booking", answer="Hotel booked!")
    cfg = {"configurable": {"thread_id": "t-book-2"}}

    # First turn — triggers interrupt.
    graph.invoke(
        {
            "messages": [HumanMessage(content="book me a hotel")],
            "user_id": "u1",
            "trip_id": None,
        },
        cfg,
    )

    # Resume with approval.
    result = graph.invoke(Command(resume={"approved": True}), cfg)
    assert not result.get("__interrupt__"), "no interrupt after approval"
    assert any("Hotel booked" in (m.content or "") for m in result["messages"])


def test_booking_resume_rejected_ends_gracefully():
    graph = _build(intent_target="booking", answer="Hotel booked!")
    cfg = {"configurable": {"thread_id": "t-book-3"}}

    graph.invoke(
        {
            "messages": [HumanMessage(content="book me a hotel")],
            "user_id": "u1",
            "trip_id": None,
        },
        cfg,
    )

    result = graph.invoke(Command(resume={"approved": False}), cfg)
    assert not result.get("__interrupt__"), "no interrupt after rejection"
    assert any("cancelled" in (m.content or "").lower() for m in result["messages"])
    # Must NOT contain any booking confirmation.
    assert not any("Hotel booked" in (m.content or "") for m in result["messages"])


# ---------------------------------------------------------------------------
# Non-booking flows: no interrupt
# ---------------------------------------------------------------------------


def test_non_booking_flow_has_no_interrupt():
    for agent in ("concierge", "planner", "budget", "journal"):
        graph = _build(intent_target=agent, answer=f"{agent} answer")
        result = _invoke(graph, "help me", thread_id=f"t-{agent}")
        assert not result.get("__interrupt__"), (
            f"{agent} must complete without interrupt"
        )
        assert result["current_flow"] == agent


# ---------------------------------------------------------------------------
# plan_approved must reset per turn (issue #63)
# ---------------------------------------------------------------------------


def test_plan_approved_resets_on_next_turn():
    """A booking approval must not leak outcome="approved" onto later turns.

    The approving turn keeps plan_approved=True (so its episode records
    "approved"), but the next fresh turn on the SAME thread must reset it to
    False — otherwise every subsequent episode is mislabeled (issue #63).
    """
    # Turn 1 supervises to booking; turn 2 to concierge (structured cursor cycles).
    main = FakeLLM(
        structured_responses=[
            SupervisorIntent(target_agent="booking"),
            SupervisorIntent(target_agent="concierge"),
        ],
        responses=["Hotel booked!", "Sunny in Hanoi"],
    )
    fast = FakeLLM(responses=["OK"])
    graph = build_graph(
        llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=InMemoryStore()
    )
    cfg = {"configurable": {"thread_id": "t-reset"}}

    # Turn 1: book → interrupt → approve. plan_node sets the flag True.
    graph.invoke(
        {
            "messages": [HumanMessage(content="book me a hotel")],
            "user_id": "u1",
            "trip_id": None,
        },
        cfg,
    )
    approved = graph.invoke(Command(resume={"approved": True}), cfg)
    assert approved.get("plan_approved") is True, (
        "approving turn must carry plan_approved=True"
    )

    # Turn 2: a fresh, unrelated turn on the same thread must clear the flag.
    nxt = graph.invoke(
        {
            "messages": [HumanMessage(content="weather in Hanoi?")],
            "user_id": "u1",
            "trip_id": None,
        },
        cfg,
    )
    assert nxt.get("plan_approved") is False, (
        "plan_approved must reset on the next fresh turn (issue #63)"
    )
