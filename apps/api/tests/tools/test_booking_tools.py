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


def test_search_hotels_unknown_city_returns_empty(agent_db):
    from app.tools.hotel_tools import search_hotels

    result = search_hotels.invoke(
        {
            "city": "NoSuchCityXYZ",
            "check_in": "2027-04-10",
            "check_out": "2027-04-14",
        }
    )
    assert result == []


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
