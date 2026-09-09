"""Tests for flight and hotel search/booking tools (specs/travel-agent Task 3.3)."""

import pytest
from langchain_core.messages import ToolMessage
from langchain_core.tools import ToolException


def _invoke_flight(args: dict) -> ToolMessage:
    """Invoke the sync content_and_artifact search_flights via ToolCall -> ToolMessage."""
    from app.tools.flight_tools import search_flights

    return search_flights.invoke(
        {"type": "tool_call", "id": "t1", "name": "search_flights", "args": args}
    )


def _invoke_hotel(args: dict) -> ToolMessage:
    """Invoke the sync content_and_artifact search_hotels via ToolCall -> ToolMessage."""
    from app.tools.hotel_tools import search_hotels

    return search_hotels.invoke(
        {"type": "tool_call", "id": "t1", "name": "search_hotels", "args": args}
    )


def test_search_flights_returns_panel_artifact(agent_db):
    msg = _invoke_flight(
        {"origin": "HAN", "destination": "SGN", "departure_date": "2027-03-15"}
    )
    assert isinstance(msg, ToolMessage)
    assert isinstance(msg.content, str) and msg.content.strip()  # model-facing summary
    assert msg.artifact["kind"] == "flights"
    data = msg.artifact["data"]
    assert data["results_count"] == len(data["flights"]) >= 1
    assert "flight_number" in data["flights"][0]


def test_search_flights_price_sort_orders_artifact(agent_db):
    # Sort order is observable on the artifact now, not the content.
    msg = _invoke_flight(
        {
            "origin": "HAN",
            "destination": "SGN",
            "departure_date": "2027-03-15",
            "sort": "price_asc",
        }
    )
    prices = [f["price"] for f in msg.artifact["data"]["flights"]]
    assert prices == sorted(prices)


def test_search_hotels_returns_panel_artifact(agent_db):
    msg = _invoke_hotel(
        {
            "city": "Da Nang",
            "check_in": "2027-04-10",
            "check_out": "2027-04-14",
            "rooms": 1,
            "adults": 2,
            "children": 0,
        }
    )
    assert isinstance(msg, ToolMessage)
    assert isinstance(msg.content, str) and msg.content.strip()  # model-facing summary
    assert msg.artifact["kind"] == "hotels"
    data = msg.artifact["data"]
    assert data["results_count"] == len(data["hotels"]) >= 1
    row = data["hotels"][0]
    # check_availability annotations projected through
    assert "available" in row and "total_price" in row and "nights" not in row


def test_search_hotels_unknown_city_returns_message_no_panel(agent_db):
    msg = _invoke_hotel(
        {
            "city": "NoSuchCityXYZ",
            "check_in": "2027-04-10",
            "check_out": "2027-04-14",
            "rooms": 1,
            "adults": 2,
            "children": 0,
        }
    )
    assert isinstance(msg, ToolMessage)
    assert msg.artifact is None  # no panel on empty
    assert "not recognized" in msg.content.lower()


def test_search_hotels_no_match_returns_message_no_panel(agent_db):
    msg = _invoke_hotel(
        {
            "city": "Da Nang",
            "check_in": "2027-04-10",
            "check_out": "2027-04-14",
            "rooms": 1,
            "adults": 2,
            "children": 0,
            "max_price": 1,  # unmatchable filter (min_stars=6 is now rejected by args_schema le=5)
        }
    )
    assert isinstance(msg, ToolMessage)
    assert msg.artifact is None  # no panel on empty
    assert "no hotels" in msg.content.lower()


def test_search_hotels_bad_dates_raise(agent_db):
    from app.tools.hotel_tools import search_hotels

    with pytest.raises(ToolException):
        search_hotels.invoke(
            {
                "city": "Da Nang",
                "check_in": "2027-04-14",
                "check_out": "2027-04-10",  # check_out before check_in
                "rooms": 1,
                "adults": 2,
                "children": 0,
            }
        )


def test_search_hotels_past_date_raises(agent_db):
    """A check_in in the past is rejected so the model self-corrects."""
    from app.tools.hotel_tools import search_hotels

    with pytest.raises(ToolException, match="in the past"):
        search_hotels.invoke(
            {
                "city": "Da Nang",
                "check_in": "2023-10-07",
                "check_out": "2023-10-11",
                "rooms": 1,
                "adults": 2,
                "children": 0,
            }
        )


def test_search_flights_no_match_returns_message_no_panel(agent_db):
    msg = _invoke_flight(
        {
            "origin": "HAN",
            "destination": "SGN",
            "departure_date": "2027-03-15",
            "max_price": 1,
        }
    )
    assert isinstance(msg, ToolMessage)
    assert msg.artifact is None  # no panel on empty
    assert "no flights" in msg.content.lower()


def test_search_flights_bad_date_raises(agent_db):
    from app.tools.flight_tools import search_flights

    with pytest.raises(ToolException):
        search_flights.invoke(
            {
                "origin": "HAN",
                "destination": "SGN",
                "departure_date": "not-a-date",
            }
        )


def test_search_flights_past_date_raises(agent_db):
    """A departure_date in the past is rejected so the model self-corrects."""
    from app.tools.flight_tools import search_flights

    with pytest.raises(ToolException, match="in the past"):
        search_flights.invoke(
            {
                "origin": "HAN",
                "destination": "SGN",
                "departure_date": "2023-10-07",
            }
        )


def test_book_hotel_guard_raises_without_confirm(agent_db):
    from app.tools.hotel_tools import book_hotel

    with pytest.raises(ToolException, match="confirm=true"):
        book_hotel.invoke(
            {
                "hotel_id": "some-hotel-id",
                "check_in": "2027-04-10",
                "check_out": "2027-04-12",
                "guest_name": "Test User",
                "guest_email": "test@example.com",
                "guest_phone": "+1 555 000 0000",
            }
        )


def test_book_hotel_guard_raises_when_confirm_false(agent_db):
    from app.tools.hotel_tools import book_hotel

    with pytest.raises(ToolException, match="confirm=true"):
        book_hotel.invoke(
            {
                "hotel_id": "some-hotel-id",
                "check_in": "2027-04-10",
                "check_out": "2027-04-12",
                "guest_name": "Test User",
                "guest_email": "test@example.com",
                "guest_phone": "+1 555 000 0000",
                "confirm": False,
            }
        )


def test_book_hotel_does_not_log_guest_pii(agent_db, caplog):
    """book_hotel must log only booking identifiers, never guest
    name/email/phone (guards against a regression back to locals()) (MIN-42)."""
    import logging

    from app.db.engine import get_session_factory
    from app.services.hotel_service import HotelService
    from app.tools.hotel_tools import book_hotel

    with get_session_factory(agent_db)() as s:
        _, results = HotelService(s).check_availability(
            "Da Nang", "2027-04-10", "2027-04-14", rooms=1, adults=2, children=0
        )
        hotel = next((h for h in results if h.available), None)
        assert hotel is not None, "no available Da Nang hotel to arrange the test"
        hotel_id = hotel.id

    with caplog.at_level(logging.INFO, logger="app.tools"):
        book_hotel.invoke(
            {
                "hotel_id": hotel_id,
                "check_in": "2027-04-10",
                "check_out": "2027-04-14",
                "guest_name": "Very Secret Guest",
                "guest_email": "secret.guest@example.com",
                "guest_phone": "+1 555 987 6543",
                "confirm": True,
            }
        )

    assert "Very Secret Guest" not in caplog.text
    assert "secret.guest@example.com" not in caplog.text
    assert "+1 555 987 6543" not in caplog.text
    assert hotel_id in caplog.text  # the plain booking identifier IS logged

_STAY = {
    "city": "Da Nang",
    "check_in": "2027-03-15",
    "check_out": "2027-03-17",
    "rooms": 1,
    "adults": 2,
    "children": 0,
}


def _sell_out(monkeypatch, hotel_ids):
    """Make the named hotels report zero free rooms, leaving the rest untouched.

    Patches the per-hotel room count `HotelService` consults, so the real catalog,
    pricing and ranking all still run — only the availability answer is staged.
    The seeded fixture books nothing, so without this every hotel is available and
    the sold-out path is unreachable.
    """
    from app.services import hotel_service as svc

    real = svc.available_rooms
    monkeypatch.setattr(
        svc,
        "available_rooms",
        lambda hotel, check_in, check_out: (
            0 if hotel.id in hotel_ids else real(hotel, check_in, check_out)
        ),
    )


def test_search_hotels_summary_never_names_a_sold_out_hotel(agent_db, monkeypatch):
    """The cheapest hotel the model is told about must be one that can be booked.

    ``check_availability`` returns every hotel matching the city and filters, each
    carrying an ``available`` flag, so the cheapest row is not necessarily the
    cheapest *bookable* room. #147: the concierge now quotes dated availability and
    has no booking step to catch the mistake later.
    """
    panel = _invoke_hotel(_STAY).artifact["data"]["hotels"]
    cheapest = min(panel, key=lambda h: h["total_price"])
    runner_up = min(
        (h for h in panel if h["id"] != cheapest["id"]),
        key=lambda h: h["total_price"],
    )

    _sell_out(monkeypatch, {cheapest["id"]})
    msg = _invoke_hotel(_STAY)

    assert cheapest["name"] not in msg.content, (
        "a hotel with no free room must never be named as the cheapest option"
    )
    assert runner_up["name"] in msg.content
    assert f"${runner_up['total_price']:.0f}" in msg.content
    assert "1 of them have no room free" in msg.content
    # The panel still carries every row, so the traveller sees the full picture.
    assert len(msg.artifact["data"]["hotels"]) == len(panel)


def test_search_hotels_summary_when_nothing_is_available(agent_db, monkeypatch):
    """Every hotel sold out: say so plainly instead of listing them as options."""
    panel = _invoke_hotel(_STAY).artifact["data"]["hotels"]

    _sell_out(monkeypatch, {h["id"] for h in panel})
    msg = _invoke_hotel(_STAY)

    assert "none has a room free" in msg.content
    assert "Cheapest" not in msg.content
    assert all(not h["available"] for h in msg.artifact["data"]["hotels"])
