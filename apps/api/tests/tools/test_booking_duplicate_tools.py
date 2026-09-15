"""Duplicate-intent warning on the agent book tools (gh-194, task 2.1).

``book_flight`` / ``book_hotel`` opt into ``BookingService``'s duplicate check
(``check_duplicate=not allow_duplicate``). A genuinely new turn re-booking the
identical active flight/hotel for the same owner must surface a ``ToolException``
that names the existing booking's confirmation code and points at
``allow_duplicate`` — and create no new row. Passing ``allow_duplicate=True``
(the override the model sets only after the traveller confirms) books a second
row. The override is model-visible; injected plumbing stays hidden.

These call the tools directly (no thread/turn context) so idempotency replay is
out of the picture and the duplicate check is what's under test.
"""

from __future__ import annotations

import pytest
from app.db.engine import get_session_factory
from app.exceptions import DUPLICATE_WARNING_MARKER
from app.services.booking_service import BookingService
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import ToolException

OWNER = "u_dup_owner"


def _warning_message(tool_name: str, content: str) -> ToolMessage:
    """The error ``ToolMessage`` the graph appends after a duplicate warning."""
    return ToolMessage(
        content=content, name=tool_name, status="error", tool_call_id="call-dup"
    )


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
# Flight: new-turn duplicate -> ToolException naming the code + allow_duplicate
# ---------------------------------------------------------------------------


def test_book_flight_duplicate_raises_and_creates_no_row(agent_db):
    from app.tools.flight_tools import book_flight

    args = _flight_args(_flight_number(agent_db))
    first = book_flight.invoke(dict(args))

    with pytest.raises(ToolException) as excinfo:
        book_flight.invoke(dict(args))

    message = str(excinfo.value)
    assert first["confirmation_code"] in message
    assert "allow_duplicate" in message
    # The blocked second attempt must not have persisted anything.
    assert _rows(agent_db) == 1


def test_book_flight_allow_duplicate_books_second_row(agent_db):
    from app.tools.flight_tools import book_flight

    args = _flight_args(_flight_number(agent_db))
    first = book_flight.invoke(dict(args))
    second = book_flight.invoke({**args, "allow_duplicate": True})

    assert second["id"] != first["id"]
    assert _rows(agent_db) == 2


# ---------------------------------------------------------------------------
# Hotel: same shape
# ---------------------------------------------------------------------------


def test_book_hotel_duplicate_raises_and_creates_no_row(agent_db):
    from app.tools.hotel_tools import book_hotel

    args = _hotel_args(_hotel_id(agent_db))
    first = book_hotel.invoke(dict(args))

    with pytest.raises(ToolException) as excinfo:
        book_hotel.invoke(dict(args))

    message = str(excinfo.value)
    assert first["confirmation_code"] in message
    assert "allow_duplicate" in message
    assert _rows(agent_db) == 1


def test_book_hotel_allow_duplicate_books_second_row(agent_db):
    from app.tools.hotel_tools import book_hotel

    args = _hotel_args(_hotel_id(agent_db))
    first = book_hotel.invoke(dict(args))
    second = book_hotel.invoke({**args, "allow_duplicate": True})

    assert second["id"] != first["id"]
    assert _rows(agent_db) == 2


# ---------------------------------------------------------------------------
# Same-turn override guard (gh-194 fix-up CR-5): a blocked duplicate raises
# before any row is inserted, so idempotency replay cannot catch a same-turn
# re-run with allow_duplicate=True flipped on. The tool must ignore the override
# until the traveller has spoken again (a new HumanMessage after the warning).
# ---------------------------------------------------------------------------


def test_book_flight_same_turn_allow_duplicate_after_warning_still_raises(agent_db):
    from app.tools.flight_tools import book_flight

    args = _flight_args(_flight_number(agent_db))
    # Pre-existing active booking from an earlier turn (no turn context).
    book_flight.invoke(dict(args))

    messages = [HumanMessage(id="h1", content="book HAN to SGN")]
    with pytest.raises(ToolException) as excinfo:
        book_flight.invoke({**args, "messages": list(messages)})
    warning = str(excinfo.value)

    # Same turn: the model flips allow_duplicate=True right after the warning,
    # with no new traveller message in between -> override is refused.
    messages.append(_warning_message("book_flight", warning))
    with pytest.raises(ToolException) as retry:
        book_flight.invoke(
            {**args, "allow_duplicate": True, "messages": list(messages)}
        )

    assert "confirm" in str(retry.value).lower()
    assert _rows(agent_db) == 1


def test_book_flight_allow_duplicate_after_new_message_books(agent_db):
    from app.tools.flight_tools import book_flight

    args = _flight_args(_flight_number(agent_db))
    first = book_flight.invoke(dict(args))

    messages = [HumanMessage(id="h1", content="book HAN to SGN")]
    with pytest.raises(ToolException) as excinfo:
        book_flight.invoke({**args, "messages": list(messages)})
    messages.append(_warning_message("book_flight", str(excinfo.value)))
    # The traveller confirms in a NEW message -> override is honoured.
    messages.append(HumanMessage(id="h2", content="yes, book another"))

    second = book_flight.invoke(
        {**args, "allow_duplicate": True, "messages": list(messages)}
    )

    assert second["id"] != first["id"]
    assert _rows(agent_db) == 2


def test_book_flight_allow_duplicate_no_context_books(agent_db):
    """No messages/context -> nothing to inspect, so the override is honoured
    (today's behaviour)."""
    from app.tools.flight_tools import book_flight

    args = _flight_args(_flight_number(agent_db))
    first = book_flight.invoke(dict(args))
    second = book_flight.invoke({**args, "allow_duplicate": True})

    assert second["id"] != first["id"]
    assert _rows(agent_db) == 2


def test_book_hotel_same_turn_allow_duplicate_after_warning_still_raises(agent_db):
    from app.tools.hotel_tools import book_hotel

    args = _hotel_args(_hotel_id(agent_db))
    book_hotel.invoke(dict(args))

    messages = [HumanMessage(id="h1", content="book Da Nang")]
    with pytest.raises(ToolException) as excinfo:
        book_hotel.invoke({**args, "messages": list(messages)})
    warning = str(excinfo.value)

    messages.append(_warning_message("book_hotel", warning))
    with pytest.raises(ToolException) as retry:
        book_hotel.invoke({**args, "allow_duplicate": True, "messages": list(messages)})

    assert "confirm" in str(retry.value).lower()
    assert _rows(agent_db) == 1


def test_book_hotel_allow_duplicate_after_new_message_books(agent_db):
    from app.tools.hotel_tools import book_hotel

    args = _hotel_args(_hotel_id(agent_db))
    first = book_hotel.invoke(dict(args))

    messages = [HumanMessage(id="h1", content="book Da Nang")]
    with pytest.raises(ToolException) as excinfo:
        book_hotel.invoke({**args, "messages": list(messages)})
    messages.append(_warning_message("book_hotel", str(excinfo.value)))
    messages.append(HumanMessage(id="h2", content="yes, book another"))

    second = book_hotel.invoke(
        {**args, "allow_duplicate": True, "messages": list(messages)}
    )

    assert second["id"] != first["id"]
    assert _rows(agent_db) == 2


def test_book_hotel_allow_duplicate_no_context_books(agent_db):
    from app.tools.hotel_tools import book_hotel

    args = _hotel_args(_hotel_id(agent_db))
    first = book_hotel.invoke(dict(args))
    second = book_hotel.invoke({**args, "allow_duplicate": True})

    assert second["id"] != first["id"]
    assert _rows(agent_db) == 2


# ---------------------------------------------------------------------------
# Per-booking override (gh-200): the override is refused only for the booking
# actually flagged this turn. A same-turn warning about booking A must not
# block an override for a different booking B; a bare legacy marker still
# refuses every override for that tool (fail-safe).
# ---------------------------------------------------------------------------


def test_book_flight_same_turn_override_for_different_booking_books(agent_db):
    from app.tools.flight_tools import book_flight

    args = _flight_args(_flight_number(agent_db))
    # Two distinct existing bookings for OWNER (match key = row + passengers),
    # seeded without turn context.
    book_flight.invoke(dict(args))  # A: passengers=1
    book_flight.invoke({**args, "passengers": 2})  # B: passengers=2
    assert _rows(agent_db) == 2

    # One turn: A is warned (its id rides the marker), then allow_duplicate=True
    # for the DIFFERENT booking B still books.
    messages = [HumanMessage(id="h1", content="book HAN to SGN")]
    with pytest.raises(ToolException) as excinfo:
        book_flight.invoke({**args, "messages": list(messages)})
    messages.append(_warning_message("book_flight", str(excinfo.value)))

    booked = book_flight.invoke(
        {**args, "passengers": 2, "allow_duplicate": True, "messages": list(messages)}
    )
    assert isinstance(booked, dict)
    assert _rows(agent_db) == 3

    # The flagged booking A is still refused in the same turn.
    with pytest.raises(ToolException) as retry:
        book_flight.invoke(
            {**args, "allow_duplicate": True, "messages": list(messages)}
        )
    assert "confirm" in str(retry.value).lower()
    assert _rows(agent_db) == 3


def test_book_hotel_same_turn_override_for_different_booking_books(agent_db):
    from app.tools.hotel_tools import book_hotel

    args = _hotel_args(_hotel_id(agent_db))
    b_args = {**args, "check_in": "2027-05-01", "check_out": "2027-05-04"}
    book_hotel.invoke(dict(args))  # A
    book_hotel.invoke(dict(b_args))  # B: same hotel, different dates
    assert _rows(agent_db) == 2

    messages = [HumanMessage(id="h1", content="book Da Nang")]
    with pytest.raises(ToolException) as excinfo:
        book_hotel.invoke({**args, "messages": list(messages)})
    messages.append(_warning_message("book_hotel", str(excinfo.value)))

    booked = book_hotel.invoke(
        {**b_args, "allow_duplicate": True, "messages": list(messages)}
    )
    assert isinstance(booked, dict)
    assert _rows(agent_db) == 3

    with pytest.raises(ToolException) as retry:
        book_hotel.invoke({**args, "allow_duplicate": True, "messages": list(messages)})
    assert "confirm" in str(retry.value).lower()
    assert _rows(agent_db) == 3


def test_book_flight_legacy_marker_refuses_override(agent_db):
    from app.tools.flight_tools import book_flight

    args = _flight_args(_flight_number(agent_db))
    book_flight.invoke(dict(args))
    messages = [
        HumanMessage(id="h1", content="book HAN to SGN"),
        _warning_message(
            "book_flight", f"Tool call failed: dup {DUPLICATE_WARNING_MARKER}"
        ),
    ]
    with pytest.raises(ToolException) as retry:
        book_flight.invoke(
            {**args, "allow_duplicate": True, "messages": list(messages)}
        )
    assert "confirm" in str(retry.value).lower()
    assert _rows(agent_db) == 1


def test_book_hotel_legacy_marker_refuses_override(agent_db):
    from app.tools.hotel_tools import book_hotel

    args = _hotel_args(_hotel_id(agent_db))
    book_hotel.invoke(dict(args))
    messages = [
        HumanMessage(id="h1", content="book Da Nang"),
        _warning_message(
            "book_hotel", f"Tool call failed: dup {DUPLICATE_WARNING_MARKER}"
        ),
    ]
    with pytest.raises(ToolException) as retry:
        book_hotel.invoke({**args, "allow_duplicate": True, "messages": list(messages)})
    assert "confirm" in str(retry.value).lower()
    assert _rows(agent_db) == 1


# ---------------------------------------------------------------------------
# Schema: allow_duplicate is model-visible, injected plumbing stays hidden
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tool_name", ["book_flight", "book_hotel"])
def test_allow_duplicate_in_model_schema_injected_hidden(tool_name):
    from app.tools.flight_tools import book_flight
    from app.tools.hotel_tools import book_hotel

    tool = {"book_flight": book_flight, "book_hotel": book_hotel}[tool_name]
    model_fields = tool.tool_call_schema.model_fields
    assert "allow_duplicate" in model_fields
    # The description must steer the model to only override after confirming.
    description = model_fields["allow_duplicate"].description or ""
    assert "confirm" in description.lower()
    for hidden in ("user_id", "trip_id", "messages", "config"):
        assert hidden not in model_fields


# ---------------------------------------------------------------------------
# gh-200 C1 — a newer matching booking committed after the warning must not slip
# through a same-turn override. The warning flagged X (warned={X}); a newer
# matching Z lands before the re-run (e.g. the REST route, which never runs the
# duplicate check); the service now raises for Z, but X is still among the error's
# matches, so the override is refused and no row is added.
# ---------------------------------------------------------------------------


def test_book_flight_newer_match_after_warning_refuses_override(agent_db):
    from app.tools.flight_tools import book_flight

    args = _flight_args(_flight_number(agent_db))
    book_flight.invoke(dict(args))  # X: the booking the warning will flag
    assert _rows(agent_db) == 1

    messages = [HumanMessage(id="h1", content="book HAN to SGN")]
    with pytest.raises(ToolException) as excinfo:
        book_flight.invoke({**args, "messages": list(messages)})
    messages.append(_warning_message("book_flight", str(excinfo.value)))

    # A newer matching booking Z lands before the same-turn re-run.
    book_flight.invoke({**args, "allow_duplicate": True})  # Z, no turn context
    assert _rows(agent_db) == 2

    # Same turn, warned={X}: the service raises for the newer Z, but X is still in
    # matches, so the override must be refused and nothing new persisted.
    with pytest.raises(ToolException) as retry:
        book_flight.invoke(
            {**args, "allow_duplicate": True, "messages": list(messages)}
        )
    assert "confirm" in str(retry.value).lower()
    assert _rows(agent_db) == 2


def test_book_hotel_newer_match_after_warning_refuses_override(agent_db):
    from app.tools.hotel_tools import book_hotel

    args = _hotel_args(_hotel_id(agent_db))
    book_hotel.invoke(dict(args))  # X
    assert _rows(agent_db) == 1

    messages = [HumanMessage(id="h1", content="book Da Nang")]
    with pytest.raises(ToolException) as excinfo:
        book_hotel.invoke({**args, "messages": list(messages)})
    messages.append(_warning_message("book_hotel", str(excinfo.value)))

    book_hotel.invoke({**args, "allow_duplicate": True})  # Z, no turn context
    assert _rows(agent_db) == 2

    with pytest.raises(ToolException) as retry:
        book_hotel.invoke({**args, "allow_duplicate": True, "messages": list(messages)})
    assert "confirm" in str(retry.value).lower()
    assert _rows(agent_db) == 2
