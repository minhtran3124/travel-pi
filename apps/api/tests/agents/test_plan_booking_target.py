"""The plan gate asks what to book first when the request names nothing bookable (#278, option B)."""

from __future__ import annotations

from app.agents import nodes as nodes_mod
from app.agents.graph import build_graph
from app.agents.nodes import _BookingTarget, make_plan_node, plan_node
from app.agents.supervisor import SupervisorIntent
from app.clients.llm import FakeLLM
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command


def _verdict(identified: bool) -> FakeLLM:
    return FakeLLM(structured_responses=[_BookingTarget(identified=identified)])


def _state(*messages, language="en"):
    return {"messages": list(messages), "language": language}


def test_vague_request_asks_first_and_never_interrupts(monkeypatch):
    def boom(_payload):
        raise AssertionError("must not interrupt for a request that names nothing")

    monkeypatch.setattr(nodes_mod, "interrupt", boom)
    monkeypatch.setattr(nodes_mod, "system_reply", lambda key, lang, **_: key)
    cmd = make_plan_node(_verdict(False))(_state(HumanMessage("Book something for me")))
    assert isinstance(cmd, Command)
    assert cmd.goto == "__end__"
    assert cmd.update["messages"][0].content == "booking_needs_details"


def test_identified_request_still_hits_the_approval_gate(monkeypatch):
    seen = []
    monkeypatch.setattr(
        nodes_mod,
        "interrupt",
        lambda payload: seen.append(payload) or {"approved": True},
    )
    cmd = make_plan_node(_verdict(True))(_state(HumanMessage("Book the Sunrise Hotel")))
    assert seen and seen[0]["type"] == "plan_approval"
    assert cmd.goto == "booking"


def test_classifier_failure_keeps_the_gate(monkeypatch):
    """Fail open: an empty/failed check must never skip approval for a booking."""
    seen = []
    monkeypatch.setattr(
        nodes_mod,
        "interrupt",
        lambda payload: seen.append(payload) or {"approved": True},
    )
    cmd = make_plan_node(FakeLLM())(
        _state(HumanMessage("book me a hotel"))
    )  # no structured_responses
    assert seen and cmd.goto == "booking"


def test_reference_to_an_earlier_option_is_read_with_context(monkeypatch):
    llm = FakeLLM(structured_responses=[_BookingTarget(identified=True)])
    calls = []
    real = nodes_mod.with_structured

    def spy(model, schema):
        runnable = real(model, schema)
        calls.append(runnable)
        return runnable

    monkeypatch.setattr(nodes_mod, "with_structured", spy)
    monkeypatch.setattr(nodes_mod, "interrupt", lambda _p: {"approved": True})
    make_plan_node(llm)(
        _state(
            AIMessage("I found the Sunrise Hotel, 2 nights from 10 Mar."),
            HumanMessage("Go ahead and book that one"),
        )
    )
    assert calls  # the classifier ran with the transcript, not just the last line


def test_plan_node_without_a_model_always_gates(monkeypatch):
    seen = []
    monkeypatch.setattr(
        nodes_mod,
        "interrupt",
        lambda payload: seen.append(payload) or {"approved": True},
    )
    plan_node(_state(HumanMessage("Book something for me")))
    assert seen


def test_graph_vague_booking_replies_without_pausing():
    # The supervisor and the booking-target check share the same (supervisor-tier) model.
    main = FakeLLM(
        structured_responses=[
            SupervisorIntent(target_agent="booking"),
            _BookingTarget(identified=False),
        ],
        responses=["unused"] * 4,
    )
    fast = FakeLLM(responses=["OK"] * 4)
    graph = build_graph(
        llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=InMemoryStore()
    )
    out = graph.invoke(
        {
            "messages": [HumanMessage("Book something for me")],
            "user_id": "u1",
            "trip_id": None,
        },
        {"configurable": {"thread_id": "t-vague-1"}},
    )
    assert not out.get("__interrupt__")
    assert "Which hotel or flight" in out["messages"][-1].content


def test_vague_request_is_answered_in_the_message_language_not_the_state_language(
    monkeypatch,
):
    """The router's state language defaults to English on a short opener; the question follows the message."""
    seen = []
    monkeypatch.setattr(
        nodes_mod, "system_reply", lambda key, lang, **_: seen.append(lang) or key
    )
    llm = FakeLLM(
        structured_responses=[_BookingTarget(identified=False, language="vi")]
    )
    make_plan_node(llm)(
        _state(HumanMessage("Đặt phòng khách sạn đó giúp tôi"), language="en")
    )
    assert seen == ["vi"]
