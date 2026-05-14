"""Tests for booking endpoints: list (paginated) and detail."""

from tests.conftest import (
    VALID_CHECK_IN,
    VALID_CHECK_OUT,
    get_first_flight_id,
    get_first_hotel_id,
)


def _create_flight_booking(client, name="Test User", email="test@example.com"):
    flight_id = get_first_flight_id(client)
    return client.post(
        "/flights/book",
        json={
            "flight_id": flight_id,
            "passenger_name": name,
            "passenger_email": email,
            "total_price": 199.0,
        },
    ).json()


def _create_hotel_booking(client, name="Test User", email="test@example.com"):
    hotel_id = get_first_hotel_id(client)
    return client.post(
        "/hotels/book",
        json={
            "hotel_id": hotel_id,
            "check_in": VALID_CHECK_IN,
            "check_out": VALID_CHECK_OUT,
            "guests": 1,
            "guest_name": name,
            "guest_email": email,
        },
    ).json()


def _all_bookings(client, **params):
    """Fetch all bookings by using a large limit."""
    return client.get("/bookings", params={"limit": 500, **params}).json()["results"]


# ---------------------------------------------------------------------------
# GET /bookings  (paginated)
# ---------------------------------------------------------------------------


def test_list_bookings_returns_200(client):
    assert client.get("/bookings").status_code == 200


def test_list_bookings_returns_paginated_envelope(client):
    body = client.get("/bookings").json()
    for field in ("total", "limit", "offset", "results"):
        assert field in body
    assert isinstance(body["results"], list)


def test_list_bookings_default_limit(client):
    body = client.get("/bookings").json()
    assert body["limit"] == 20
    assert body["offset"] == 0


def test_list_bookings_custom_limit(client):
    body = client.get("/bookings", params={"limit": 3}).json()
    assert body["limit"] == 3
    assert len(body["results"]) <= 3


def test_list_bookings_limit_validation(client):
    assert client.get("/bookings", params={"limit": 0}).status_code == 422
    assert client.get("/bookings", params={"limit": 501}).status_code == 422


def test_list_bookings_offset_validation(client):
    assert client.get("/bookings", params={"offset": -1}).status_code == 422


def test_list_bookings_contains_created_bookings(client):
    booking = _create_flight_booking(client, "ListUser", "listuser@example.com")
    ids = [b["id"] for b in _all_bookings(client)]
    assert booking["id"] in ids


def test_list_bookings_filter_by_type_flight(client):
    _create_flight_booking(client, "FlightFilter", "flightfilter@example.com")
    results = _all_bookings(client, type="flight")
    assert all(b["type"] == "flight" for b in results)


def test_list_bookings_filter_by_type_hotel(client):
    _create_hotel_booking(client, "HotelFilter", "hotelfilter@example.com")
    results = _all_bookings(client, type="hotel")
    assert all(b["type"] == "hotel" for b in results)


def test_list_bookings_unknown_type_returns_all(client):
    all_b = _all_bookings(client)
    filtered = _all_bookings(client, type="unknown")
    assert len(filtered) == len(all_b)


def test_list_bookings_search_by_name(client):
    unique_name = "UniqueNameXYZ987"
    booking = _create_flight_booking(client, unique_name, "unique987@example.com")
    results = _all_bookings(client, q=unique_name)
    assert len(results) >= 1
    assert any(b["id"] == booking["id"] for b in results)


def test_list_bookings_search_by_email(client):
    unique_email = "veryrandom123abc@example.com"
    booking = _create_hotel_booking(client, "Random User", unique_email)
    results = _all_bookings(client, q=unique_email)
    assert any(b["id"] == booking["id"] for b in results)


def test_list_bookings_search_case_insensitive(client):
    unique_name = "CaseSensTest"
    booking = _create_flight_booking(client, unique_name, "casetest@example.com")
    results = _all_bookings(client, q=unique_name.lower())
    assert any(b["id"] == booking["id"] for b in results)


def test_list_bookings_sort_price_asc(client):
    results = _all_bookings(client, sort="price_asc")
    if len(results) > 1:
        prices = [b["total_price"] for b in results]
        assert prices == sorted(prices)


def test_list_bookings_sort_price_desc(client):
    results = _all_bookings(client, sort="price_desc")
    if len(results) > 1:
        prices = [b["total_price"] for b in results]
        assert prices == sorted(prices, reverse=True)


def test_list_bookings_sort_created_asc(client):
    results = _all_bookings(client, sort="created_asc")
    if len(results) > 1:
        dates = [b["created_at"] for b in results]
        assert dates == sorted(dates)


def test_list_bookings_sort_created_desc(client):
    results = _all_bookings(client, sort="created_desc")
    if len(results) > 1:
        dates = [b["created_at"] for b in results]
        assert dates == sorted(dates, reverse=True)


def test_list_bookings_booking_has_required_fields(client):
    _create_flight_booking(client)
    bookings = _all_bookings(client)
    assert len(bookings) > 0
    booking = bookings[0]
    for field in (
        "id", "type", "reference_id", "customer_name", "customer_email",
        "total_price", "currency", "status", "created_at", "details",
    ):
        assert field in booking


def test_list_bookings_pagination_offset(client):
    _create_flight_booking(client, "PagA", "paga@example.com")
    _create_flight_booking(client, "PagB", "pagb@example.com")
    total = client.get("/bookings").json()["total"]
    if total > 1:
        r1 = client.get("/bookings", params={"limit": 1, "offset": 0}).json()
        r2 = client.get("/bookings", params={"limit": 1, "offset": 1}).json()
        assert r1["total"] == total
        assert r2["total"] == total
        assert r1["results"][0]["id"] != r2["results"][0]["id"]


def test_list_bookings_total_stable_across_pages(client):
    t1 = client.get("/bookings", params={"limit": 2, "offset": 0}).json()["total"]
    t2 = client.get("/bookings", params={"limit": 2, "offset": 2}).json()["total"]
    assert t1 == t2


# ---------------------------------------------------------------------------
# GET /bookings/{booking_id}
# ---------------------------------------------------------------------------


def test_get_booking_returns_200(client):
    booking = _create_flight_booking(client, "GetUser", "getuser@example.com")
    assert client.get(f"/bookings/{booking['id']}").status_code == 200


def test_get_booking_returns_correct_data(client):
    booking = _create_flight_booking(client, "DetailUser", "detail@example.com")
    body = client.get(f"/bookings/{booking['id']}").json()
    assert body["id"] == booking["id"]
    assert body["customer_name"] == "DetailUser"
    assert body["customer_email"] == "detail@example.com"


def test_get_booking_nonexistent_returns_404(client):
    assert client.get("/bookings/00000000-0000-0000-0000-000000000000").status_code == 404


def test_get_hotel_booking_by_id(client):
    booking = _create_hotel_booking(client, "HotelGetUser", "hotelget@example.com")
    body = client.get(f"/bookings/{booking['id']}").json()
    assert body["id"] == booking["id"]
    assert body["type"] == "hotel"
