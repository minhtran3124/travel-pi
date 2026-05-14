"""Tests for flight endpoints: search, detail, and booking."""

import pytest

from tests.conftest import (
    VALID_DATE,
    VALID_DESTINATION,
    VALID_ORIGIN,
    get_first_flight_id,
)


# ---------------------------------------------------------------------------
# GET /flights/search
# ---------------------------------------------------------------------------


def test_search_flights_returns_200(client):
    resp = client.get(
        "/flights/search",
        params={
            "origin": VALID_ORIGIN,
            "destination": VALID_DESTINATION,
            "departure_date": VALID_DATE,
        },
    )
    assert resp.status_code == 200


def test_search_flights_response_structure(client):
    body = client.get(
        "/flights/search",
        params={
            "origin": VALID_ORIGIN,
            "destination": VALID_DESTINATION,
            "departure_date": VALID_DATE,
        },
    ).json()
    assert "count" in body
    assert "search" in body
    assert "results" in body


def test_search_flights_count_matches_results(client):
    body = client.get(
        "/flights/search",
        params={
            "origin": VALID_ORIGIN,
            "destination": VALID_DESTINATION,
            "departure_date": VALID_DATE,
        },
    ).json()
    assert body["count"] == len(body["results"])


def test_search_flights_returns_five_results(client):
    body = client.get(
        "/flights/search",
        params={
            "origin": VALID_ORIGIN,
            "destination": VALID_DESTINATION,
            "departure_date": VALID_DATE,
        },
    ).json()
    assert body["count"] == 5


def test_search_flights_is_deterministic(client):
    params = {
        "origin": VALID_ORIGIN,
        "destination": VALID_DESTINATION,
        "departure_date": VALID_DATE,
    }
    first = client.get("/flights/search", params=params).json()
    second = client.get("/flights/search", params=params).json()
    assert first["results"] == second["results"]


def test_search_flights_result_fields(client):
    results = client.get(
        "/flights/search",
        params={
            "origin": VALID_ORIGIN,
            "destination": VALID_DESTINATION,
            "departure_date": VALID_DATE,
        },
    ).json()["results"]
    flight = results[0]
    for field in (
        "id",
        "airline",
        "flight_number",
        "origin",
        "destination",
        "departure_time",
        "arrival_time",
        "duration_minutes",
        "price",
        "currency",
        "seats_available",
        "stops",
    ):
        assert field in flight


def test_search_flights_origin_uppercased(client):
    body = client.get(
        "/flights/search",
        params={
            "origin": "dad",
            "destination": "sgn",
            "departure_date": VALID_DATE,
        },
    ).json()
    assert body["search"]["origin"] == "DAD"
    assert body["search"]["destination"] == "SGN"


def test_search_flights_echoes_back_params(client):
    body = client.get(
        "/flights/search",
        params={
            "origin": VALID_ORIGIN,
            "destination": VALID_DESTINATION,
            "departure_date": VALID_DATE,
            "adults": 2,
        },
    ).json()
    assert body["search"]["origin"] == VALID_ORIGIN
    assert body["search"]["destination"] == VALID_DESTINATION
    assert body["search"]["departure_date"] == VALID_DATE
    assert body["search"]["adults"] == 2


def test_search_flights_invalid_date_returns_422(client):
    resp = client.get(
        "/flights/search",
        params={
            "origin": VALID_ORIGIN,
            "destination": VALID_DESTINATION,
            "departure_date": "not-a-date",
        },
    )
    assert resp.status_code == 422


def test_search_flights_missing_required_param_returns_422(client):
    resp = client.get(
        "/flights/search",
        params={
            "origin": VALID_ORIGIN,
            "destination": VALID_DESTINATION,
            # departure_date missing
        },
    )
    assert resp.status_code == 422


def test_search_flights_filter_by_max_price(client):
    all_results = client.get(
        "/flights/search",
        params={
            "origin": VALID_ORIGIN,
            "destination": VALID_DESTINATION,
            "departure_date": VALID_DATE,
        },
    ).json()["results"]

    max_price = sorted(f["price"] for f in all_results)[2]  # median price

    filtered = client.get(
        "/flights/search",
        params={
            "origin": VALID_ORIGIN,
            "destination": VALID_DESTINATION,
            "departure_date": VALID_DATE,
            "max_price": max_price,
        },
    ).json()["results"]

    assert all(f["price"] <= max_price for f in filtered)


def test_search_flights_filter_by_max_stops(client):
    filtered = client.get(
        "/flights/search",
        params={
            "origin": VALID_ORIGIN,
            "destination": VALID_DESTINATION,
            "departure_date": VALID_DATE,
            "max_stops": 0,
        },
    ).json()["results"]
    assert all(f["stops"] == 0 for f in filtered)


def test_search_flights_sort_price_asc(client):
    results = client.get(
        "/flights/search",
        params={
            "origin": VALID_ORIGIN,
            "destination": VALID_DESTINATION,
            "departure_date": VALID_DATE,
            "sort": "price_asc",
        },
    ).json()["results"]
    prices = [f["price"] for f in results]
    assert prices == sorted(prices)


def test_search_flights_sort_price_desc(client):
    results = client.get(
        "/flights/search",
        params={
            "origin": VALID_ORIGIN,
            "destination": VALID_DESTINATION,
            "departure_date": VALID_DATE,
            "sort": "price_desc",
        },
    ).json()["results"]
    prices = [f["price"] for f in results]
    assert prices == sorted(prices, reverse=True)


def test_search_flights_sort_departure_asc(client):
    results = client.get(
        "/flights/search",
        params={
            "origin": VALID_ORIGIN,
            "destination": VALID_DESTINATION,
            "departure_date": VALID_DATE,
            "sort": "departure_asc",
        },
    ).json()["results"]
    departures = [f["departure_time"] for f in results]
    assert departures == sorted(departures)


def test_search_flights_sort_duration_asc(client):
    results = client.get(
        "/flights/search",
        params={
            "origin": VALID_ORIGIN,
            "destination": VALID_DESTINATION,
            "departure_date": VALID_DATE,
            "sort": "duration_asc",
        },
    ).json()["results"]
    durations = [f["duration_minutes"] for f in results]
    assert durations == sorted(durations)


# ---------------------------------------------------------------------------
# GET /flights/{flight_id}
# ---------------------------------------------------------------------------


def test_get_flight_returns_200(client):
    flight_id = get_first_flight_id(client)
    resp = client.get(f"/flights/{flight_id}")
    assert resp.status_code == 200


def test_get_flight_returns_correct_id(client):
    flight_id = get_first_flight_id(client)
    body = client.get(f"/flights/{flight_id}").json()
    assert body["id"] == flight_id


def test_get_flight_has_expected_fields(client):
    flight_id = get_first_flight_id(client)
    body = client.get(f"/flights/{flight_id}").json()
    for field in ("id", "airline", "origin", "destination", "price", "stops"):
        assert field in body


def test_get_flight_unknown_uuid_returns_404(client):
    resp = client.get("/flights/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


def test_get_flight_malformed_id_returns_404(client):
    resp = client.get("/flights/not-a-valid-flight-id")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /flights/book
# ---------------------------------------------------------------------------


def test_book_flight_returns_200(client):
    flight_id = get_first_flight_id(client)
    resp = client.post(
        "/flights/book",
        json={
            "flight_id": flight_id,
            "passenger_name": "Alice Smith",
            "passenger_email": "alice@example.com",
            "total_price": 250.0,
        },
    )
    assert resp.status_code == 200


def test_book_flight_response_structure(client):
    flight_id = get_first_flight_id(client)
    body = client.post(
        "/flights/book",
        json={
            "flight_id": flight_id,
            "passenger_name": "Bob Jones",
            "passenger_email": "bob@example.com",
            "total_price": 300.0,
        },
    ).json()
    for field in (
        "id",
        "type",
        "reference_id",
        "customer_name",
        "customer_email",
        "total_price",
        "status",
        "created_at",
        "details",
    ):
        assert field in body


def test_book_flight_type_is_flight(client):
    flight_id = get_first_flight_id(client)
    body = client.post(
        "/flights/book",
        json={
            "flight_id": flight_id,
            "passenger_name": "Carol White",
            "passenger_email": "carol@example.com",
            "total_price": 199.99,
        },
    ).json()
    assert body["type"] == "flight"


def test_book_flight_id_is_uuid(client):
    import uuid as _uuid

    flight_id = get_first_flight_id(client)
    body = client.post(
        "/flights/book",
        json={
            "flight_id": flight_id,
            "passenger_name": "Dave Brown",
            "passenger_email": "dave@example.com",
            "total_price": 150.0,
        },
    ).json()
    _uuid.UUID(body["id"])  # raises if not a valid UUID


def test_book_flight_status_is_confirmed(client):
    flight_id = get_first_flight_id(client)
    body = client.post(
        "/flights/book",
        json={
            "flight_id": flight_id,
            "passenger_name": "Eve Green",
            "passenger_email": "eve@example.com",
            "total_price": 200.0,
        },
    ).json()
    assert body["status"] == "confirmed"


def test_book_flight_customer_name_stored(client):
    flight_id = get_first_flight_id(client)
    body = client.post(
        "/flights/book",
        json={
            "flight_id": flight_id,
            "passenger_name": "Frank Lee",
            "passenger_email": "frank@example.com",
            "total_price": 175.0,
        },
    ).json()
    assert body["customer_name"] == "Frank Lee"


def test_book_flight_invalid_id_returns_404(client):
    resp = client.post(
        "/flights/book",
        json={
            "flight_id": "FL_NONEXISTENT",
            "passenger_name": "Ghost User",
            "passenger_email": "ghost@example.com",
            "total_price": 100.0,
        },
    )
    assert resp.status_code == 404


def test_book_flight_missing_fields_returns_422(client):
    resp = client.post(
        "/flights/book",
        json={"flight_id": "FL_DADSGN_20260601_00"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Round-trip search
# ---------------------------------------------------------------------------

RETURN_DATE = "2026-06-08"


def test_search_flights_roundtrip_returns_return_results(client):
    body = client.get(
        "/flights/search",
        params={
            "origin": VALID_ORIGIN,
            "destination": VALID_DESTINATION,
            "departure_date": VALID_DATE,
            "return_date": RETURN_DATE,
        },
    ).json()
    assert body["return_results"] is not None
    assert body["return_count"] == len(body["return_results"])


def test_search_flights_roundtrip_echoes_return_date(client):
    body = client.get(
        "/flights/search",
        params={
            "origin": VALID_ORIGIN,
            "destination": VALID_DESTINATION,
            "departure_date": VALID_DATE,
            "return_date": RETURN_DATE,
        },
    ).json()
    assert body["search"]["return_date"] == RETURN_DATE


def test_search_flights_roundtrip_legs_are_reversed(client):
    body = client.get(
        "/flights/search",
        params={
            "origin": VALID_ORIGIN,
            "destination": VALID_DESTINATION,
            "departure_date": VALID_DATE,
            "return_date": RETURN_DATE,
        },
    ).json()
    for flight in body["return_results"]:
        assert flight["origin"] == VALID_DESTINATION
        assert flight["destination"] == VALID_ORIGIN


def test_search_flights_no_return_date_has_null_return_fields(client):
    body = client.get(
        "/flights/search",
        params={
            "origin": VALID_ORIGIN,
            "destination": VALID_DESTINATION,
            "departure_date": VALID_DATE,
        },
    ).json()
    assert body["return_results"] is None
    assert body["return_count"] is None


def test_search_flights_roundtrip_invalid_return_date_returns_422(client):
    resp = client.get(
        "/flights/search",
        params={
            "origin": VALID_ORIGIN,
            "destination": VALID_DESTINATION,
            "departure_date": VALID_DATE,
            "return_date": "not-a-date",
        },
    )
    assert resp.status_code == 422


def test_book_flight_with_notes(client):
    flight_id = get_first_flight_id(client)
    body = client.post(
        "/flights/book",
        json={
            "flight_id": flight_id,
            "passenger_name": "Notes User",
            "passenger_email": "notes@example.com",
            "total_price": 250.0,
            "notes": "Part of Da Nang 3-day trip",
        },
    ).json()
    assert body["notes"] == "Part of Da Nang 3-day trip"


def test_book_flight_notes_optional(client):
    flight_id = get_first_flight_id(client)
    body = client.post(
        "/flights/book",
        json={
            "flight_id": flight_id,
            "passenger_name": "No Notes",
            "passenger_email": "nonotes@example.com",
            "total_price": 199.0,
        },
    ).json()
    assert body["notes"] is None
