"""Agent booking/cancel tools stamp & enforce the graph owner (review-A, SC-6).

Wave 2 made ``BookingService`` owner-scoped (keyword-only ``user_id``). These
tests prove the agent tools now thread the graph's ``user_id`` (injected from
``TravelAgentState`` via ``InjectedState``) into the service, so:

* a booking created through ``book_flight`` / ``book_hotel`` is scoped to that
  owner — readable by the owner, not-found for anyone else (#118);
* the ``user_id`` is injected, never model-supplied (hidden from the
  model-facing schema).

The second half of SC-6 — the four money tools being *absent* from the MCP tool
list — is asserted by ``test_booking_tools_absent_from_mcp`` below. Enforcement
lives in ``app/mcp/server.py``, which skips ``destructive`` tools from the
unauthenticated MCP surface (specs/review-a-security-hardening E004); adding
``InjectedState("user_id")`` alone does not drop a tool off MCP.
"""

import pytest
from app.db.engine import get_session_factory
from app.exceptions import NotFoundError
from app.services.booking_service import BookingService

OWNER = "u_state_owner"
INTRUDER = "u_intruder"


def _assert_scoped_to_owner(url: str, booking_id: str) -> None:
    """The booking reads back for OWNER and is not-found for anyone else."""
    with get_session_factory(url)() as s:
        svc = BookingService(s)
        owned = svc.get(booking_id, user_id=OWNER)
        assert owned.id == booking_id
        with pytest.raises(NotFoundError):
            svc.get(booking_id, user_id=INTRUDER)


def test_book_flight_stamps_graph_owner(agent_db):
    from app.services.flight_service import FlightService
    from app.tools.flight_tools import book_flight

    with get_session_factory(agent_db)() as s:
        flight_number = (
            FlightService(s).search_flights("HAN", "SGN", "2027-03-15")[0].flight_number
        )

    result = book_flight.invoke(
        {
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
    )
    assert result["status"] == "confirmed"
    _assert_scoped_to_owner(agent_db, result["id"])


def test_book_hotel_stamps_graph_owner(agent_db):
    from app.services.hotel_service import HotelService
    from app.tools.hotel_tools import book_hotel

    with get_session_factory(agent_db)() as s:
        _, results = HotelService(s).check_availability(
            "Da Nang", "2027-04-10", "2027-04-14", rooms=1, adults=2, children=0
        )
        hotel_id = next(h for h in results if h.available).id

    result = book_hotel.invoke(
        {
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
    )
    assert result["type"] == "hotel"
    _assert_scoped_to_owner(agent_db, result["id"])


@pytest.mark.parametrize(
    "tool_name",
    ["book_flight", "book_hotel", "cancel_flight", "cancel_hotel"],
)
def test_owner_hidden_from_model_facing_schema(tool_name):
    """The injected ``user_id`` never appears in the model-facing tool schema."""
    from app.tools.registry import ALL_TOOLS

    tool = next(t for t in ALL_TOOLS if t.name == tool_name)
    assert "user_id" not in tool.tool_call_schema.model_fields
    assert "user_id" in tool.get_input_schema().model_fields


def test_booking_tools_absent_from_mcp():
    """SC-6 (second half): the four money tools must be absent from the MCP list."""
    import asyncio

    from app.mcp.server import build_mcp_server

    names = {t.name for t in asyncio.run(build_mcp_server().list_tools())}
    assert names.isdisjoint(
        {"book_flight", "book_hotel", "cancel_flight", "cancel_hotel"}
    )
