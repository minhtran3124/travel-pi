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
            "min_stars": 6,
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
