"""Tests for flight endpoints: search, detail, and booking."""


from tests.conftest import (
    VALID_DATE,
    VALID_DESTINATION,
    VALID_ORIGIN,
    get_first_flight_booking_fields,
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


def test_get_flight_resolves_from_persisted_index(client):
    """A flight ID resolves even when the in-process cache is empty — i.e.
    after a restart or on a different worker — because the search params are
    persisted to SQLite."""
    from app.services import flight_service

    flight_id = get_first_flight_id(client)
    # Simulate a fresh process: the in-memory cache is gone, only the DB remains.
    flight_service._flight_index.clear()

    resp = client.get(f"/flights/{flight_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == flight_id


# ---------------------------------------------------------------------------
# POST /flights/book
# ---------------------------------------------------------------------------


def test_book_flight_returns_200(client):

    resp = client.post(
        "/flights/book",
        json={
            **get_first_flight_booking_fields(client),
            "passenger_name": "Alice Smith",
            "passenger_email": "alice@example.com",
            "passenger_phone": "+84 901 234 567",
        },
    )
    assert resp.status_code == 200


def test_book_flight_response_structure(client):

    body = client.post(
        "/flights/book",
        json={
            **get_first_flight_booking_fields(client),
            "passenger_name": "Bob Jones",
            "passenger_email": "bob@example.com",
            "passenger_phone": "+84 901 234 567",
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

    body = client.post(
        "/flights/book",
        json={
            **get_first_flight_booking_fields(client),
            "passenger_name": "Carol White",
            "passenger_email": "carol@example.com",
            "passenger_phone": "+84 901 234 567",
        },
    ).json()
    assert body["type"] == "flight"


def test_book_flight_id_is_uuid(client):
    import uuid as _uuid


    body = client.post(
        "/flights/book",
        json={
            **get_first_flight_booking_fields(client),
            "passenger_name": "Dave Brown",
            "passenger_email": "dave@example.com",
            "passenger_phone": "+84 901 234 567",
        },
    ).json()
    _uuid.UUID(body["id"])  # raises if not a valid UUID


def test_book_flight_status_is_confirmed(client):

    body = client.post(
        "/flights/book",
        json={
            **get_first_flight_booking_fields(client),
            "passenger_name": "Eve Green",
            "passenger_email": "eve@example.com",
            "passenger_phone": "+84 901 234 567",
        },
    ).json()
    assert body["status"] == "confirmed"


def test_book_flight_customer_name_stored(client):

    body = client.post(
        "/flights/book",
        json={
            **get_first_flight_booking_fields(client),
            "passenger_name": "Frank Lee",
            "passenger_email": "frank@example.com",
            "passenger_phone": "+84 901 234 567",
        },
    ).json()
    assert body["customer_name"] == "Frank Lee"


def test_book_flight_unknown_flight_returns_404(client):
    """A well-formed payload that names a flight nobody operates → 404."""
    resp = client.post(
        "/flights/book",
        json={
            "flight_number": "ZZ999",
            "origin": VALID_ORIGIN,
            "destination": VALID_DESTINATION,
            "departure_date": VALID_DATE,
            "passenger_name": "Ghost User",
            "passenger_email": "ghost@example.com",
            "passenger_phone": "+84 901 234 567",
        },
    )
    assert resp.status_code == 404


def test_book_flight_missing_fields_returns_422(client):
    """flight_number alone (no route/date, no passenger info) → 422."""
    resp = client.post(
        "/flights/book",
        json={"flight_number": "VN123"},
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

    body = client.post(
        "/flights/book",
        json={
            **get_first_flight_booking_fields(client),
            "passenger_name": "Notes User",
            "passenger_email": "notes@example.com",
            "passenger_phone": "+84 901 234 567",
            "notes": "Part of Da Nang 3-day trip",
        },
    ).json()
    assert body["notes"] == "Part of Da Nang 3-day trip"


def test_book_flight_notes_optional(client):

    body = client.post(
        "/flights/book",
        json={
            **get_first_flight_booking_fields(client),
            "passenger_name": "No Notes",
            "passenger_email": "nonotes@example.com",
            "passenger_phone": "+84 901 234 567",
        },
    ).json()
    assert body["notes"] is None


# ---------------------------------------------------------------------------
# POST /flights/book — Idempotency-Key
# ---------------------------------------------------------------------------


def test_book_flight_idempotency_key_replays_same_booking(client):

    payload = {
        **get_first_flight_booking_fields(client),
        "passenger_name": "Idem Potent",
        "passenger_email": "idem@example.com",
        "passenger_phone": "+84 901 234 567",
    }
    headers = {"Idempotency-Key": "flight-key-abc"}
    first = client.post("/flights/book", json=payload, headers=headers).json()
    second = client.post("/flights/book", json=payload, headers=headers).json()
    assert first["id"] == second["id"]


def test_book_flight_idempotency_key_does_not_create_duplicate(client):

    payload = {
        **get_first_flight_booking_fields(client),
        "passenger_name": "No Dupe",
        "passenger_email": "nodupe@example.com",
        "passenger_phone": "+84 901 234 567",
    }
    headers = {"Idempotency-Key": "flight-key-nodupe"}
    client.post("/flights/book", json=payload, headers=headers)
    client.post("/flights/book", json=payload, headers=headers)
    matches = client.get(
        "/bookings", params={"limit": 500, "q": "nodupe@example.com"}
    ).json()["results"]
    assert len(matches) == 1


def test_book_flight_without_idempotency_key_creates_each_time(client):

    payload = {
        **get_first_flight_booking_fields(client),
        "passenger_name": "Twice Booked",
        "passenger_email": "twice@example.com",
        "passenger_phone": "+84 901 234 567",
    }
    first = client.post("/flights/book", json=payload).json()
    second = client.post("/flights/book", json=payload).json()
    assert first["id"] != second["id"]


def test_book_flight_distinct_idempotency_keys_create_distinct_bookings(client):

    payload = {
        **get_first_flight_booking_fields(client),
        "passenger_name": "Distinct Keys",
        "passenger_email": "distinct@example.com",
        "passenger_phone": "+84 901 234 567",
    }
    first = client.post(
        "/flights/book", json=payload, headers={"Idempotency-Key": "flight-key-1"}
    ).json()
    second = client.post(
        "/flights/book", json=payload, headers={"Idempotency-Key": "flight-key-2"}
    ).json()
    assert first["id"] != second["id"]


# ---------------------------------------------------------------------------
# POST /flights/book — realistic request shape
# ---------------------------------------------------------------------------


def test_book_flight_price_taken_from_flight_server_side(client):
    """total_price comes from the selected flight, not the request body."""
    flight_id = get_first_flight_id(client)
    flight = client.get(f"/flights/{flight_id}").json()
    body = client.post(
        "/flights/book",
        json={
            **get_first_flight_booking_fields(client),
            "passenger_name": "Server Price",
            "passenger_email": "serverprice@example.com",
            "passenger_phone": "+84 901 234 567",
        },
    ).json()
    assert body["total_price"] == flight["price"]


def test_book_flight_client_supplied_price_is_ignored(client):
    """A stray total_price in the body must not override the real fare."""
    flight_id = get_first_flight_id(client)
    flight = client.get(f"/flights/{flight_id}").json()
    body = client.post(
        "/flights/book",
        json={
            **get_first_flight_booking_fields(client),
            "passenger_name": "Tampered Price",
            "passenger_email": "tampered@example.com",
            "passenger_phone": "+84 901 234 567",
            "total_price": 1.0,
        },
    ).json()
    assert body["total_price"] == flight["price"]


def test_book_flight_requires_passenger_phone(client):

    resp = client.post(
        "/flights/book",
        json={
            **get_first_flight_booking_fields(client),
            "passenger_name": "No Phone",
            "passenger_email": "nophone@example.com",
        },
    )
    assert resp.status_code == 422


def test_book_flight_details_includes_passenger_phone(client):

    body = client.post(
        "/flights/book",
        json={
            **get_first_flight_booking_fields(client),
            "passenger_name": "Phone Carrier",
            "passenger_email": "phonecarrier@example.com",
            "passenger_phone": "+84 987 654 321",
        },
    ).json()
    assert body["details"]["passenger_phone"] == "+84 987 654 321"
