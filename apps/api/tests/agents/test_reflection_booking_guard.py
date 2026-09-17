"""When this turn already committed a booking (a non-error booking-write ToolMessage after the last ``HumanMessage``), reflection must END before the judge so the booking is never re-run. ``llm._cursor`` (0 until the judge is called) proves whether it ran."""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.constants import BOOKING_WRITE_TOOLS
from app.agents.context import AgentContext
from app.agents.nodes import make_reflection_node
from app.clients.llm import FakeLLM
from app.tools.flight_tools import book_flight
from app.tools.hotel_tools import book_hotel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import END

# ---------------------------------------------------------------------------
# Helpers (mirrors tests/agents/test_depth_toggles.py)
# ---------------------------------------------------------------------------


def _runtime(ctx: AgentContext | None = None):
    """Minimal runtime stand-in: exposes only .context, which is all nodes read."""
    return SimpleNamespace(context=ctx)


def _base_state(**overrides):
    """Minimal TravelAgentState for testing."""
    state = {
        "messages": [HumanMessage(content="hi")],
        "revisions": 0,
        "current_flow": "booking",
        "user_id": None,
        "trip_id": None,
        "summary": None,
        "trip_context": None,
    }
    state.update(overrides)
    return state


def _tool_msg(name: str, status: str = "success") -> ToolMessage:
    return ToolMessage(content="done", name=name, tool_call_id="call-1", status=status)


# ---------------------------------------------------------------------------
# The guard
# ---------------------------------------------------------------------------


def test_committed_booking_this_turn_ends_turn_without_judge():
    """Successful book_flight ToolMessage this turn -> END, judge not called."""
    llm = FakeLLM(responses=["REVISE this answer"])  # would loop if judge ran
    reflect = make_reflection_node(llm)

    state = _base_state(
        messages=[
            HumanMessage(content="book the 9am flight"),
            AIMessage(content=""),
            _tool_msg("book_flight"),
            AIMessage(content="Booked! Confirmation ABC123."),
        ],
    )
    result = reflect(state, _runtime(AgentContext()))

    assert result.goto == END
    assert llm._cursor == 0  # judge was never called


def test_errored_booking_this_turn_still_reaches_judge():
    """An errored book_* ToolMessage is not a committed booking -> judge runs."""
    llm = FakeLLM(responses=["REVISE this answer"])
    reflect = make_reflection_node(llm)

    state = _base_state(
        messages=[
            HumanMessage(content="book the 9am flight"),
            AIMessage(content=""),
            _tool_msg("book_flight", status="error"),
            AIMessage(content="Sorry, that flight is sold out."),
        ],
    )
    result = reflect(state, _runtime(AgentContext()))

    assert result.goto == "booking"  # REVISE routed back to current_flow
    assert llm._cursor == 1  # judge ran


def test_booking_before_last_human_message_reaches_judge():
    """A committed booking in an EARLIER turn does not guard this turn."""
    llm = FakeLLM(responses=["REVISE this answer"])
    reflect = make_reflection_node(llm)

    state = _base_state(
        messages=[
            HumanMessage(content="book the 9am flight"),
            _tool_msg("book_flight"),
            AIMessage(content="Booked!"),
            HumanMessage(content="what's the weather there?"),
            AIMessage(content="Sunny all week."),
        ],
    )
    result = reflect(state, _runtime(AgentContext()))

    assert result.goto == "booking"
    assert llm._cursor == 1  # judge ran


def test_non_booking_tool_this_turn_reaches_judge():
    """A non-booking write tool this turn does not trip the guard."""
    llm = FakeLLM(responses=["REVISE this answer"])
    reflect = make_reflection_node(llm)

    state = _base_state(
        messages=[
            HumanMessage(content="find me a flight"),
            AIMessage(content=""),
            _tool_msg("search_flights"),
            AIMessage(content="Here are three options."),
        ],
    )
    result = reflect(state, _runtime(AgentContext()))

    assert result.goto == "booking"
    assert llm._cursor == 1  # judge ran


def test_booking_write_tools_pinned_to_tool_names():
    """The constant is pinned to the real tool objects' .name attributes."""
    assert {book_flight.name, book_hotel.name} == BOOKING_WRITE_TOOLS
