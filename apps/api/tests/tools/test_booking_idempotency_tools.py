"""Turn-scoped idempotency for the booking write tools (gh-193, task 2.1).

``book_flight`` / ``book_hotel`` are re-run on a revise turn (the reflection
loop re-invokes the specialist with a correction note). These tests pin that a
second call *within the same traveller turn* — same LangGraph ``thread_id`` and
same last ``HumanMessage`` — replays the original booking instead of creating a
duplicate, while a genuinely new turn (a new ``HumanMessage``) still books
again, and a call with no thread/turn context keeps today's create-every-time
behaviour (that last invariant is pinned by
``tests/tools/test_flight_booking_tool.py`` and cross-checked here as case (d)).
"""

from __future__ import annotations

import pytest
from app.db.engine import get_session_factory
from app.services.booking_service import BookingService
from langchain_core.messages import AIMessage, HumanMessage

OWNER = "u_idem_owner"


def _flight_number(url: str) -> str:
    from app.services.flight_service import FlightService

    with get_session_factory(url)() as s:
        return (
            FlightService(s).search_flights("HAN", "SGN", "2027-03-15")[0].flight_number
        )


def _hotel_id(url: str) -> str:
    from app.services.hotel_service import HotelService

    with get_session_factory(url)() as s:
        _, results = HotelService(s).check_availability(
            "Da Nang", "2027-04-10", "2027-04-14", rooms=1, adults=2, children=0
        )
        return next(h for h in results if h.available).id


def _flight_args(flight_number: str) -> dict:
    return {
        "flight_number": flight_number,
        "origin": "HAN",
        "destination": "SGN",
        "departure_date": "2027-03-15",
        "passenger_name": "Test User",
        "passenger_email": "test@example.com",
        "passenger_phone": "+1 555 000 0000",
        "confirm": True,
        "user_id": OWNER,
    }


def _hotel_args(hotel_id: str) -> dict:
    return {
        "hotel_id": hotel_id,
        "check_in": "2027-04-10",
        "check_out": "2027-04-14",
        "rooms": 1,
        "adults": 2,
        "children": 0,
        "guest_name": "Test User",
        "guest_email": "test@example.com",
        "guest_phone": "+1 555 000 0000",
        "confirm": True,
        "user_id": OWNER,
    }


def _rows(url: str) -> int:
    with get_session_factory(url)() as s:
        return len(BookingService(s).list_all(user_id=OWNER))


# ---------------------------------------------------------------------------
# (a) same thread + same last HumanMessage -> replay (one row)
# ---------------------------------------------------------------------------


def test_book_flight_same_turn_replays_one_row(agent_db):
    from app.tools.flight_tools import book_flight

    args = {
        **_flight_args(_flight_number(agent_db)),
        "messages": [HumanMessage(id="h1", content="book it")],
    }
    config = {"configurable": {"thread_id": "t1"}}

    first = book_flight.invoke(dict(args), config=config)
    second = book_flight.invoke(dict(args), config=config)

    assert first["id"] == second["id"]
    assert first["confirmation_code"] == second["confirmation_code"]
    assert _rows(agent_db) == 1


# ---------------------------------------------------------------------------
# (a1) same turn, second call with allow_duplicate=True -> still replays (one row)
# ---------------------------------------------------------------------------


def test_book_flight_same_turn_allow_duplicate_still_replays_one_row(agent_db):
    """Same-turn idempotency replay wins over the duplicate check: a second call
    in the same turn replays the first booking even when allow_duplicate=True is
    set, so the row count stays 1 and the same id comes back (gh-194, M4)."""
    from app.tools.flight_tools import book_flight

    args = {
        **_flight_args(_flight_number(agent_db)),
        "messages": [HumanMessage(id="h1", content="book it")],
    }
    config = {"configurable": {"thread_id": "t1"}}

    first = book_flight.invoke(dict(args), config=config)
    second = book_flight.invoke(
        {**args, "allow_duplicate": True}, config=config
    )

    assert first["id"] == second["id"]
    assert _rows(agent_db) == 1


# ---------------------------------------------------------------------------
# (a2) same turn, but cancelled between calls -> new booking (two rows)
# ---------------------------------------------------------------------------


def test_book_flight_cancel_then_rebook_same_turn_creates_new_row(agent_db):
    """A cancel releases the idempotency key (gh-193, E001): book -> cancel ->
    book-again within the *same* turn no longer replays the cancelled row, it
    creates a fresh booking. Two rows exist (one cancelled, one confirmed)."""
    from app.tools.booking_tools import cancel_flight
    from app.tools.flight_tools import book_flight

    args = {
        **_flight_args(_flight_number(agent_db)),
        "messages": [HumanMessage(id="h1", content="book it")],
    }
    config = {"configurable": {"thread_id": "t1"}}

    first = book_flight.invoke(dict(args), config=config)
    cancel_flight.invoke({"booking_id": first["id"], "confirm": True, "user_id": OWNER})
    second = book_flight.invoke(dict(args), config=config)

    assert second["id"] != first["id"]
    assert _rows(agent_db) == 2


# ---------------------------------------------------------------------------
# (b) new turn (new HumanMessage) -> new booking (two rows)
# ---------------------------------------------------------------------------


def test_book_flight_new_turn_books_again_two_rows(agent_db):
    from app.tools.flight_tools import book_flight

    base = _flight_args(_flight_number(agent_db))
    config = {"configurable": {"thread_id": "t1"}}

    book_flight.invoke(
        {**base, "messages": [HumanMessage(id="h1", content="book it")]}, config=config
    )
    # gh-194: a genuinely new turn re-booking the identical flight now trips the
    # duplicate check, so the second (deliberate) booking sets allow_duplicate=True
    # — this keeps testing that a new turn is not idempotency-collapsed.
    book_flight.invoke(
        {
            **base,
            "allow_duplicate": True,
            "messages": [
                HumanMessage(id="h1", content="book it"),
                AIMessage(content="Booked!"),
                HumanMessage(id="h2", content="actually book it again"),
            ],
        },
        config=config,
    )

    assert _rows(agent_db) == 2


# ---------------------------------------------------------------------------
# (c) same as (a) for book_hotel
# ---------------------------------------------------------------------------


def test_book_hotel_same_turn_replays_one_row(agent_db):
    from app.tools.hotel_tools import book_hotel

    args = {
        **_hotel_args(_hotel_id(agent_db)),
        "messages": [HumanMessage(id="h1", content="book it")],
    }
    config = {"configurable": {"thread_id": "t1"}}

    first = book_hotel.invoke(dict(args), config=config)
    second = book_hotel.invoke(dict(args), config=config)

    assert first["id"] == second["id"]
    assert first["confirmation_code"] == second["confirmation_code"]
    assert _rows(agent_db) == 1


# ---------------------------------------------------------------------------
# (d) no thread/turn context -> distinct bookings (pinned behaviour, SC-3)
# ---------------------------------------------------------------------------


def test_book_flight_no_context_creates_distinct_bookings(agent_db):
    from app.tools.flight_tools import book_flight

    args = _flight_args(_flight_number(agent_db))

    first = book_flight.invoke(dict(args))
    # gh-194: with no turn context there is no idempotency replay, but the
    # duplicate check still fires, so the intentional second booking opts in.
    second = book_flight.invoke({**args, "allow_duplicate": True})

    assert first["id"] != second["id"]
    assert _rows(agent_db) == 2


# ---------------------------------------------------------------------------
# (e) end-to-end through the booking sub-agent: two invokes, same turn -> one row
# ---------------------------------------------------------------------------


def test_book_flight_replays_through_booking_subagent(agent_db):
    """The reflection revise loop re-invokes the specialist with the same turn
    (same thread + same last HumanMessage). Driven through the real booking
    sub-agent, the second invoke must replay the first booking, not duplicate it.

    ``book_flight`` is trip-scoped (``trip_id`` via ``InjectedState``), so the
    sub-agent's trip guard blocks it when no trip is active - the state carries a
    real OWNER-owned trip so the tool actually runs (see report deviation)."""
    from app.agents.subagents.booking import build_booking
    from app.clients.llm import FakeLLM
    from app.schemas.trip import TripCreate
    from app.services.trip_service import TripService

    flight_number = _flight_number(agent_db)
    with get_session_factory(agent_db)() as s:
        trip = TripService(s, OWNER).create_trip(
            TripCreate(title="HAN to SGN", city="Hanoi")
        )
        s.commit()
        trip_id = trip.id

    tool_call = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "book_flight",
                "args": {
                    "flight_number": flight_number,
                    "origin": "HAN",
                    "destination": "SGN",
                    "departure_date": "2027-03-15",
                    "passenger_name": "Test User",
                    "passenger_email": "test@example.com",
                    "passenger_phone": "+1 555 000 0000",
                    "confirm": True,
                },
                "id": "call-1",
            }
        ],
    )
    fake_llm = FakeLLM(responses=[tool_call, "Booked!"])
    agent = build_booking(lambda hint=None: fake_llm)

    state = {
        "messages": [HumanMessage(id="h1", content="book HAN to SGN")],
        "user_id": OWNER,
        "trip_id": trip_id,
    }
    config = {"configurable": {"thread_id": "t-e2e"}}

    agent.invoke(dict(state), config=config)
    agent.invoke(dict(state), config=config)

    assert _rows(agent_db) == 1


# ---------------------------------------------------------------------------
# SC-6: injected plumbing stays out of the model-visible schema
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tool_name", ["book_flight", "book_hotel"])
def test_messages_and_config_hidden_from_model_schema(tool_name):
    from app.tools.flight_tools import book_flight
    from app.tools.hotel_tools import book_hotel

    tool = {"book_flight": book_flight, "book_hotel": book_hotel}[tool_name]
    assert "messages" not in tool.args
    assert "config" not in tool.args
