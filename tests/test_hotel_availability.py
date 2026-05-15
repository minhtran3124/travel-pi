"""Tests for GET /hotels/availability and the booking availability gate.

Availability is deterministic (hotel + date range → seeded RNG), so these
tests assert structure and invariants rather than exact room counts. The
booking-gate tests monkeypatch ``hotel_service.available_rooms`` to drive the
available / fully-booked branches deterministically.
"""

import pytest
from app.services import hotel_service

from tests.conftest import VALID_CHECK_IN, VALID_CHECK_OUT, get_first_hotel_id

_CITY = "Da Nang"


def _availability(client, **params):
    base = {"city": _CITY, "check_in": VALID_CHECK_IN, "check_out": VALID_CHECK_OUT}
    return client.get("/hotels/availability", params={**base, **params})


# --- Endpoint shape -----------------------------------------------------------


def test_availability_returns_200(client):
    assert _availability(client).status_code == 200


def test_availability_response_shape(client):
    body = _availability(client, rooms=2, adults=3, children=1).json()
    for field in ("total", "limit", "offset", "search", "results"):
        assert field in body
    search = body["search"]
    assert search["city"] == "Da Nang"
    assert search["nights"] == 2
    assert search["rooms"] == 2
    assert search["adults"] == 3
    assert search["children"] == 1


def test_availability_result_fields(client):
    body = _availability(client).json()
    assert body["total"] > 0
    for hotel in body["results"]:
        for field in (
            "available",
            "available_rooms",
            "max_occupancy_per_room",
            "nights",
            "total_price",
        ):
            assert field in hotel
        assert isinstance(hotel["available"], bool)
        assert hotel["available_rooms"] >= 0
        assert hotel["nights"] == 2


def test_availability_total_price_is_per_stay_and_rooms(client):
    """total_price = price_per_night × nights × rooms."""
    body = _availability(client, rooms=3).json()
    for hotel in body["results"]:
        assert hotel["total_price"] == pytest.approx(
            hotel["price_per_night"] * 2 * 3
        )


def test_availability_bad_date_returns_422(client):
    assert _availability(client, check_in="not-a-date").status_code == 422


def test_availability_unknown_city_returns_zero(client):
    body = client.get(
        "/hotels/availability",
        params={
            "city": "zzzznowhere",
            "check_in": VALID_CHECK_IN,
            "check_out": VALID_CHECK_OUT,
        },
    ).json()
    assert body["total"] == 0


def test_availability_city_is_fuzzy(client):
    body = client.get(
        "/hotels/availability",
        params={
            "city": "danang",
            "check_in": VALID_CHECK_IN,
            "check_out": VALID_CHECK_OUT,
        },
    ).json()
    assert body["total"] > 0
    assert body["search"]["city"] == "Da Nang"


def test_availability_rooms_validation(client):
    assert _availability(client, rooms=0).status_code == 422
    assert _availability(client, adults=0).status_code == 422


def test_availability_only_filter(client, monkeypatch):
    """available_only=true drops the fully-booked hotels."""
    # Make exactly nothing available, then everything.
    monkeypatch.setattr(hotel_service, "available_rooms", lambda *a, **k: 0)
    body = _availability(client, available_only=True).json()
    assert body["total"] == 0

    monkeypatch.setattr(hotel_service, "available_rooms", lambda *a, **k: 99)
    body = _availability(client, available_only=True).json()
    assert body["total"] > 0
    assert all(h["available"] for h in body["results"])


# --- Deterministic availability model (units) ---------------------------------


def test_total_rooms_is_deterministic_and_in_range():
    hotel = hotel_service.list_hotels()[0]
    first = hotel_service.total_rooms(hotel)
    assert first == hotel_service.total_rooms(hotel)  # stable
    assert 20 <= first <= 200


def test_max_occupancy_scales_with_stars():
    for hotel in hotel_service.list_hotels():
        occ = hotel_service.max_occupancy(hotel)
        assert occ == 2 + hotel.star_rating // 3
        assert 2 <= occ <= 3


def test_available_rooms_is_deterministic_and_bounded():
    hotel = hotel_service.list_hotels()[0]
    first = hotel_service.available_rooms(hotel, VALID_CHECK_IN, VALID_CHECK_OUT)
    assert first == hotel_service.available_rooms(
        hotel, VALID_CHECK_IN, VALID_CHECK_OUT
    )
    assert 0 <= first <= hotel_service.total_rooms(hotel)


def test_some_hotel_date_combos_are_fully_booked():
    """available_rooms can legitimately be 0 — at least one combo proves it."""
    fully_booked = any(
        hotel_service.available_rooms(h, VALID_CHECK_IN, VALID_CHECK_OUT) == 0
        or hotel_service.available_rooms(h, "2026-07-01", "2026-07-05") == 0
        for h in hotel_service.list_hotels()
    )
    assert fully_booked


# --- Booking availability gate ------------------------------------------------


def _book(client, **overrides):
    payload = {
        "hotel_id": get_first_hotel_id(client),
        "check_in": VALID_CHECK_IN,
        "check_out": VALID_CHECK_OUT,
        "rooms": 1,
        "adults": 2,
        "children": 0,
        "guest_name": "Avail Tester",
        "guest_email": "avail@example.com",
        "guest_phone": "+84 901 234 567",
    }
    payload.update(overrides)
    return client.post("/hotels/book", json=payload)


def test_book_fully_booked_hotel_returns_409(client, monkeypatch):
    monkeypatch.setattr(hotel_service, "available_rooms", lambda *a, **k: 0)
    assert _book(client).status_code == 409


def test_book_available_hotel_succeeds(client, monkeypatch):
    monkeypatch.setattr(hotel_service, "available_rooms", lambda *a, **k: 50)
    resp = _book(client, guest_email="availok@example.com")
    assert resp.status_code == 200
    body = resp.json()
    assert body["details"]["rooms"] == 1
    assert body["details"]["adults"] == 2


def test_book_party_too_large_for_rooms_returns_409(client, monkeypatch):
    """One room cannot hold 10 people even when rooms are free."""
    monkeypatch.setattr(hotel_service, "available_rooms", lambda *a, **k: 99)
    assert _book(client, rooms=1, adults=10).status_code == 409


def test_book_total_price_scales_with_rooms(client, monkeypatch):
    monkeypatch.setattr(hotel_service, "available_rooms", lambda *a, **k: 99)
    hotel_id = get_first_hotel_id(client)
    price_per_night = client.get(f"/hotels/{hotel_id}").json()["price_per_night"]
    body = _book(
        client, hotel_id=hotel_id, rooms=2, guest_email="rooms2@example.com"
    ).json()
    # price_per_night × 2 nights × 2 rooms
    assert body["total_price"] == pytest.approx(price_per_night * 2 * 2)
