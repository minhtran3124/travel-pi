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


def test_search_flights_returns_panel_artifact(agent_db):
    msg = _invoke_flight({"origin": "HAN", "destination": "SGN", "departure_date": "2027-03-15"})
    assert isinstance(msg, ToolMessage)
    assert isinstance(msg.content, str) and msg.content.strip()  # model-facing summary
    assert msg.artifact["kind"] == "flights"
    data = msg.artifact["data"]
    assert data["results_count"] == len(data["flights"]) >= 1
    assert "flight_number" in data["flights"][0]


def test_search_flights_price_sort_orders_artifact(agent_db):
    # Sort order is observable on the artifact now, not the content.
    msg = _invoke_flight(
        {"origin": "HAN", "destination": "SGN", "departure_date": "2027-03-15", "sort": "price_asc"}
    )
    prices = [f["price"] for f in msg.artifact["data"]["flights"]]
    assert prices == sorted(prices)


def test_search_hotels_returns_list(agent_db):
    from app.tools.hotel_tools import search_hotels

    result = search_hotels.invoke(
        {
            "city": "Da Nang",
            "check_in": "2027-04-10",
            "check_out": "2027-04-14",
        }
    )
    assert isinstance(result, list)
    if result:
        assert isinstance(result[0], dict)
        # check_availability annotates results with these fields
        assert "available" in result[0]
        assert "nights" in result[0]
        assert "total_price" in result[0]


def test_search_hotels_unknown_city_returns_reason(agent_db):
    from app.tools.hotel_tools import search_hotels

    result = search_hotels.invoke(
        {
            "city": "NoSuchCityXYZ",
            "check_in": "2027-04-10",
            "check_out": "2027-04-14",
        }
    )
    # Empty results now carry an explicit signal so the LLM can answer clearly.
    assert isinstance(result, dict)
    assert result["results"] == []
    assert result["reason"] == "unknown_city"
    assert result["message"]


def test_search_hotels_no_match_returns_reason(agent_db):
    from app.tools.hotel_tools import search_hotels

    # City resolves, but an impossible filter (no 6-star hotels) empties the results.
    result = search_hotels.invoke(
        {
            "city": "Da Nang",
            "check_in": "2027-04-10",
            "check_out": "2027-04-14",
            "min_stars": 6,
        }
    )
    assert isinstance(result, dict)
    assert result["results"] == []
    assert result["reason"] == "no_match"
    assert result["message"]


def test_search_hotels_bad_dates_raise(agent_db):
    from app.tools.hotel_tools import search_hotels

    with pytest.raises(ToolException):
        search_hotels.invoke(
            {
                "city": "Da Nang",
                "check_in": "2027-04-14",
                "check_out": "2027-04-10",  # check_out before check_in
            }
        )


def test_search_flights_no_match_returns_message_no_panel(agent_db):
    msg = _invoke_flight(
        {"origin": "HAN", "destination": "SGN", "departure_date": "2027-03-15", "max_price": 1}
    )
    assert isinstance(msg, ToolMessage)
    assert msg.artifact is None          # no panel on empty
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
