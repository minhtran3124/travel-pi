"""Task 4.1 — supervisor slot extraction + secondary intent (MIN-65 DESIGN D3)."""

from types import SimpleNamespace

import pytest
from app.agents.context import AgentContext
from langchain_core.messages import HumanMessage


def _runtime(ctx: AgentContext | None = None) -> SimpleNamespace:
    """Minimal runtime stand-in matching the Runtime[AgentContext] interface."""
    return SimpleNamespace(context=ctx if ctx is not None else AgentContext())


# ---------------------------------------------------------------------------
# Date slots — resolvable vs. unresolvable
# ---------------------------------------------------------------------------


def test_resolvable_dates_land_in_trip_facts_as_iso():
    from app.agents.supervisor import ExtractedSlots, SupervisorIntent, make_supervisor
    from app.clients.llm import FakeLLM

    intent = SupervisorIntent(
        target_agent="planner",
        slots=ExtractedSlots(start_date_text="2026-08-15", end_date_text="20/08/2026"),
    )
    llm = FakeLLM(structured_responses=[intent])
    supervisor = make_supervisor(llm)

    cmd = supervisor(
        {"messages": [HumanMessage(content="plan a trip 15/8 to 20/8")]}, _runtime()
    )

    assert cmd.update["trip_facts"] == {
        "start_date": "2026-08-15",
        "end_date": "2026-08-20",
    }


def test_unresolvable_date_text_is_dropped_not_set_none():
    from app.agents.supervisor import ExtractedSlots, SupervisorIntent, make_supervisor
    from app.clients.llm import FakeLLM

    intent = SupervisorIntent(
        target_agent="planner",
        slots=ExtractedSlots(start_date_text="garbled nonsense", end_date_text=None),
    )
    llm = FakeLLM(structured_responses=[intent])
    supervisor = make_supervisor(llm)

    cmd = supervisor({"messages": [HumanMessage(content="plan a trip")]}, _runtime())

    assert "start_date" not in cmd.update["trip_facts"]
    assert "end_date" not in cmd.update["trip_facts"]
    assert cmd.update["trip_facts"] == {}


# ---------------------------------------------------------------------------
# Count slots — adults/children/rooms
# ---------------------------------------------------------------------------


def test_positive_counts_land_in_trip_facts():
    from app.agents.supervisor import ExtractedSlots, SupervisorIntent, make_supervisor
    from app.clients.llm import FakeLLM

    intent = SupervisorIntent(
        target_agent="planner",
        slots=ExtractedSlots(adults=2, children=1, rooms=1),
    )
    llm = FakeLLM(structured_responses=[intent])
    supervisor = make_supervisor(llm)

    cmd = supervisor(
        {"messages": [HumanMessage(content="2 adults 1 child 1 room")]}, _runtime()
    )

    assert cmd.update["trip_facts"] == {"adults": 2, "children": 1, "rooms": 1}


def test_zero_negative_or_absent_counts_are_dropped():
    from app.agents.supervisor import ExtractedSlots, SupervisorIntent, make_supervisor
    from app.clients.llm import FakeLLM

    intent = SupervisorIntent(
        target_agent="planner",
        slots=ExtractedSlots(adults=0, children=-1, rooms=None),
    )
    llm = FakeLLM(structured_responses=[intent])
    supervisor = make_supervisor(llm)

    cmd = supervisor({"messages": [HumanMessage(content="hmm")]}, _runtime())

    assert cmd.update["trip_facts"] == {}


def test_children_zero_is_kept_unlike_adults_and_rooms():
    """Regression (ce-code-review finding): "2 adults, no kids" must not be
    re-asked about later — children=0 is a required, meaningful hotel-search
    value ("0 if none"), unlike adults/rooms where 0 is genuinely invalid."""
    from app.agents.supervisor import ExtractedSlots, SupervisorIntent, make_supervisor
    from app.clients.llm import FakeLLM

    intent = SupervisorIntent(
        target_agent="planner",
        slots=ExtractedSlots(adults=2, children=0, rooms=1),
    )
    llm = FakeLLM(structured_responses=[intent])
    supervisor = make_supervisor(llm)

    cmd = supervisor(
        {"messages": [HumanMessage(content="2 adults, no kids, 1 room")]}, _runtime()
    )

    assert cmd.update["trip_facts"] == {"adults": 2, "children": 0, "rooms": 1}


# ---------------------------------------------------------------------------
# Secondary intent gating
# ---------------------------------------------------------------------------


def test_booking_target_forces_secondary_to_empty_even_if_llm_set_one():
    from app.agents.supervisor import SupervisorIntent, make_supervisor
    from app.clients.llm import FakeLLM

    intent = SupervisorIntent(target_agent="booking", secondary_agent="concierge")
    llm = FakeLLM(structured_responses=[intent])
    supervisor = make_supervisor(llm)

    cmd = supervisor(
        {"messages": [HumanMessage(content="book the hotel and find me food")]},
        _runtime(),
    )

    assert cmd.update["pending_flows"] == []


def test_valid_distinct_secondary_queues_pending_flow():
    from app.agents.supervisor import SupervisorIntent, make_supervisor
    from app.clients.llm import FakeLLM

    intent = SupervisorIntent(target_agent="planner", secondary_agent="concierge")
    llm = FakeLLM(structured_responses=[intent])
    supervisor = make_supervisor(llm)

    cmd = supervisor(
        {"messages": [HumanMessage(content="find a flight and tell me about food")]},
        _runtime(),
    )

    assert cmd.update["pending_flows"] == ["concierge"]


def test_secondary_equal_to_target_is_dropped():
    from app.agents.supervisor import SupervisorIntent, make_supervisor
    from app.clients.llm import FakeLLM

    intent = SupervisorIntent(target_agent="planner", secondary_agent="planner")
    llm = FakeLLM(structured_responses=[intent])
    supervisor = make_supervisor(llm)

    cmd = supervisor({"messages": [HumanMessage(content="plan my trip")]}, _runtime())

    assert cmd.update["pending_flows"] == []


# ---------------------------------------------------------------------------
# Regression: no slots mentioned -> routing behavior unchanged
# ---------------------------------------------------------------------------


def test_no_slots_mentioned_routing_unchanged():
    from app.agents.supervisor import SupervisorIntent, make_supervisor
    from app.clients.llm import FakeLLM

    llm = FakeLLM(structured_responses=[SupervisorIntent(target_agent="planner")])
    supervisor = make_supervisor(llm)

    cmd = supervisor({"messages": [HumanMessage(content="plan my trip")]}, _runtime())

    assert cmd.goto == ()
    assert cmd.update["current_flow"] == "planner"
    assert cmd.update["trip_facts"] == {}
    assert cmd.update["pending_flows"] == []
    assert cmd.update["tasks"] == [
        {"agent": "planner", "query": "plan my trip", "index": 0}
    ]


# ---------------------------------------------------------------------------
# Budget slot — _BUDGET_RE "parse or drop" (MIN-65 DESIGN D3, no full currency
# parser: a number + optional currency hint is kept verbatim, anything with no
# number is dropped rather than guessed)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Plain number, no currency hint.
        ("5000000", "5000000"),
        # Each supported currency-unit hint (kept verbatim, spaced off the amount).
        ("10 triệu", "10 triệu"),
        ("10tr", "10 tr"),
        ("500 nghìn", "500 nghìn"),
        ("500 ngàn", "500 ngàn"),
        ("20k", "20 k"),
        ("300 usd", "300 usd"),
        ("200000 đ", "200000 đ"),
        # Group separators and decimals inside the amount are preserved.
        ("2.000.000 vnd", "2.000.000 vnd"),
        ("1.5 triệu", "1.5 triệu"),
        # A trailing currency symbol is a unit; a leading one is not matched.
        ("300$", "300 $"),
        ("$300", "300"),
        # Number embedded in a sentence is still found.
        ("around 10 triệu please", "10 triệu"),
        # No number → dropped, never guessed.
        ("no budget here", None),
        ("", None),
        ("   ", None),
        (None, None),
    ],
)
def test_normalize_budget_slot(raw, expected):
    from app.agents.supervisor import _normalize_budget_slot

    assert _normalize_budget_slot(raw) == expected
