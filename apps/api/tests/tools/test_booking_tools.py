"""Tests for flight and hotel search/booking tools (specs/travel-agent Task 3.3)."""

import pytest
from langchain_core.tools import ToolException


def test_search_flights_returns_list(agent_db):
    from app.tools.flight_tools import search_flights

    result = search_flights.invoke(
        {
            "origin": "HAN",
            "destination": "SGN",
            "departure_date": "2027-03-15",
        }
    )
    assert isinstance(result, list)
    if result:
        assert isinstance(result[0], dict)
        assert "flight_number" in result[0]
        assert "price" in result[0]


def test_search_flights_with_price_sort(agent_db):
    from app.tools.flight_tools import search_flights

    result = search_flights.invoke(
        {
            "origin": "HAN",
            "destination": "SGN",
            "departure_date": "2027-03-15",
            "sort": "price_asc",
        }
    )
    assert isinstance(result, list)
    # Deterministic — same query always returns results; verify ascending price order.
    if len(result) > 1:
        prices = [item["price"] for item in result]
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


def test_search_flights_no_match_returns_reason(agent_db):
    from app.tools.flight_tools import search_flights

    # An impossible price cap empties the deterministic 5-flight set.
    result = search_flights.invoke(
        {
            "origin": "HAN",
            "destination": "SGN",
            "departure_date": "2027-03-15",
            "max_price": 1,
        }
    )
    assert isinstance(result, dict)
    assert result["results"] == []
    assert result["reason"] == "no_match"
    assert "max_price" in result["message"]


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
