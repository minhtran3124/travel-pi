"""Turn-scoped idempotency for the booking write tools: a second call within the
same turn replays the original booking, a new turn books again, and no turn
context keeps the create-every-time behaviour."""

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


def test_book_flight_same_turn_allow_duplicate_still_replays_one_row(agent_db):
    """Same-turn idempotency replay wins over the duplicate check even when
    allow_duplicate=True is set: the row count stays 1 and the same id comes back."""
    from app.tools.flight_tools import book_flight

    args = {
        **_flight_args(_flight_number(agent_db)),
        "messages": [HumanMessage(id="h1", content="book it")],
    }
    config = {"configurable": {"thread_id": "t1"}}

    first = book_flight.invoke(dict(args), config=config)
    second = book_flight.invoke({**args, "allow_duplicate": True}, config=config)

    assert first["id"] == second["id"]
    assert _rows(agent_db) == 1


def test_book_flight_cancel_then_rebook_same_turn_creates_new_row(agent_db):
    """A cancel releases the idempotency key: book -> cancel -> book-again in the
    same turn creates a fresh booking rather than replaying the cancelled row."""
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


def test_book_flight_new_turn_books_again_two_rows(agent_db):
    from app.tools.flight_tools import book_flight

    base = _flight_args(_flight_number(agent_db))
    config = {"configurable": {"thread_id": "t1"}}

    book_flight.invoke(
        {**base, "messages": [HumanMessage(id="h1", content="book it")]}, config=config
    )
    # A new turn re-booking the identical flight trips the duplicate check, so the
    # deliberate second booking sets allow_duplicate=True and is not collapsed.
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


def test_book_flight_no_context_creates_distinct_bookings(agent_db):
    from app.tools.flight_tools import book_flight

    args = _flight_args(_flight_number(agent_db))

    first = book_flight.invoke(dict(args))
    # No turn context means no replay, but the duplicate check still fires, so the
    # intentional second booking opts in.
    second = book_flight.invoke({**args, "allow_duplicate": True})

    assert first["id"] != second["id"]
    assert _rows(agent_db) == 2


def test_book_flight_replays_through_booking_subagent(agent_db):
    """Driven through the real booking sub-agent, a second invoke in the same turn
    replays the first booking. The state carries a real OWNER-owned trip because
    book_flight is trip-scoped and the sub-agent's trip guard blocks it otherwise."""
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


@pytest.mark.parametrize("tool_name", ["book_flight", "book_hotel"])
def test_messages_and_config_hidden_from_model_schema(tool_name):
    from app.tools.flight_tools import book_flight
    from app.tools.hotel_tools import book_hotel

    tool = {"book_flight": book_flight, "book_hotel": book_hotel}[tool_name]
    assert "messages" not in tool.args
    assert "config" not in tool.args
