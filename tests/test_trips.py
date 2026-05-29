"""Tests for the /trips itinerary-aggregation endpoints."""

import pytest
from app.services import hotel_service

from tests.conftest import (
    VALID_CHECK_IN,
    VALID_CHECK_OUT,
    get_first_flight_booking_fields,
    get_first_hotel_id,
)


@pytest.fixture(autouse=True)
def _rooms_always_available(monkeypatch):
    """Pin hotel availability high so attached hotel bookings always succeed."""
    monkeypatch.setattr(hotel_service, "available_rooms", lambda *a, **k: 99)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_hotel_booking(client) -> str:
    """Create a hotel booking and return its UUID."""
    hotel_id = get_first_hotel_id(client)
    return client.post(
        "/hotels/book",
        json={
            "hotel_id": hotel_id,
            "check_in": VALID_CHECK_IN,
            "check_out": VALID_CHECK_OUT,
            "adults": 2,
            "guest_name": "Trip Tester",
            "guest_email": "trip@example.com",
            "guest_phone": "+84 901 234 567",
        },
    ).json()["id"]


def _make_flight_booking(client) -> str:
    return client.post(
        "/flights/book",
        json={
            **get_first_flight_booking_fields(client),
            "passenger_name": "Trip Tester",
            "passenger_email": "trip@example.com",
            "passenger_phone": "+84 901 234 567",
        },
    ).json()["id"]


def _first_place_id(client, city="Da Nang") -> str:
    return client.get("/places/search", params={"city": city}).json()["results"][0][
        "id"
    ]


def _create_trip(client, **overrides) -> dict:
    payload = {
        "name": "Da Nang weekend",
        "destination_city": "Da Nang",
        "start_date": "2026-06-01",
        "end_date": "2026-06-04",
    }
    payload.update(overrides)
    return client.post("/trips", json=payload).json()


# ---------------------------------------------------------------------------
# POST /trips
# ---------------------------------------------------------------------------


def test_create_trip_returns_200(client):
    resp = client.post(
        "/trips",
        json={
            "name": "Solo trip",
            "destination_city": "Da Nang",
            "start_date": "2026-06-01",
            "end_date": "2026-06-04",
        },
    )
    assert resp.status_code == 200


def test_create_trip_resolves_city_and_country(client):
    body = _create_trip(client, destination_city="danang")  # fuzzy
    assert body["destination_city"] == "Da Nang"
    assert body["country"] == "Vietnam"


def test_create_trip_has_confirmation_code_and_nights(client):
    body = _create_trip(client)
    assert body["confirmation_code"].startswith("TRP-")
    assert body["nights"] == 3
    assert body["status"] == "planning"
    assert "summary" in body and body["summary"]


def test_create_trip_id_is_uuid(client):
    import uuid as _uuid

    _uuid.UUID(_create_trip(client)["id"])


def test_create_trip_with_bookings_and_items(client):
    hotel_booking = _make_hotel_booking(client)
    flight_booking = _make_flight_booking(client)
    place_id = _first_place_id(client)
    body = _create_trip(
        client,
        booking_ids=[hotel_booking, flight_booking],
        items=[{"place_id": place_id, "day": 1, "note": "Morning"}],
    )
    assert body["booking_ids"] == [hotel_booking, flight_booking]
    assert body["items"][0]["place_id"] == place_id
    assert body["items"][0]["day"] == 1


def test_create_trip_accepts_booking_confirmation_code(client):
    """A booking can be attached by its confirmation code, stored as the UUID."""
    booking = client.post(
        "/hotels/book",
        json={
            "hotel_id": get_first_hotel_id(client),
            "check_in": VALID_CHECK_IN,
            "check_out": VALID_CHECK_OUT,
            "adults": 1,
            "guest_name": "Code Ref",
            "guest_email": "code@example.com",
            "guest_phone": "+84 901 234 567",
        },
    ).json()
    body = _create_trip(client, booking_ids=[booking["confirmation_code"]])
    assert body["booking_ids"] == [booking["id"]]


def test_create_trip_unknown_booking_returns_404(client):
    resp = client.post(
        "/trips",
        json={
            "name": "Bad ref",
            "destination_city": "Da Nang",
            "start_date": "2026-06-01",
            "end_date": "2026-06-04",
            "booking_ids": ["00000000-0000-0000-0000-000000000000"],
        },
    )
    assert resp.status_code == 404


def test_create_trip_unknown_place_returns_404(client):
    resp = client.post(
        "/trips",
        json={
            "name": "Bad place",
            "destination_city": "Da Nang",
            "start_date": "2026-06-01",
            "end_date": "2026-06-04",
            "items": [{"place_id": "no-such-place"}],
        },
    )
    assert resp.status_code == 404


def test_create_trip_unknown_city_returns_404(client):
    resp = client.post(
        "/trips",
        json={
            "name": "Nowhere",
            "destination_city": "Qzxwvutsrq",  # far from any seeded city
            "start_date": "2026-06-01",
            "end_date": "2026-06-04",
        },
    )
    assert resp.status_code == 404


def test_create_trip_end_before_start_returns_422(client):
    resp = client.post(
        "/trips",
        json={
            "name": "Backwards",
            "destination_city": "Da Nang",
            "start_date": "2026-06-04",
            "end_date": "2026-06-01",
        },
    )
    assert resp.status_code == 422


def test_create_trip_bad_date_format_returns_422(client):
    resp = client.post(
        "/trips",
        json={
            "name": "Bad date",
            "destination_city": "Da Nang",
            "start_date": "june 1",
            "end_date": "2026-06-04",
        },
    )
    assert resp.status_code == 422


def test_create_trip_same_day_is_zero_nights(client):
    body = _create_trip(client, start_date="2026-06-01", end_date="2026-06-01")
    assert body["nights"] == 0


def test_create_trip_unknown_field_returns_422(client):
    resp = client.post(
        "/trips",
        json={
            "name": "x",
            "destination_city": "Da Nang",
            "start_date": "2026-06-01",
            "end_date": "2026-06-04",
            "duration_days": 3,  # not a field
        },
    )
    assert resp.status_code == 422
    assert resp.json()["error"] == "ValidationError"


def test_create_trip_missing_required_returns_422(client):
    assert client.post("/trips", json={"name": "x"}).status_code == 422


def test_create_trip_idempotency_key_replays(client):
    headers = {"Idempotency-Key": "trip-replay-001"}
    first = client.post(
        "/trips",
        headers=headers,
        json={
            "name": "Replay",
            "destination_city": "Hanoi",
            "start_date": "2026-07-01",
            "end_date": "2026-07-03",
        },
    ).json()
    second = client.post(
        "/trips",
        headers=headers,
        json={
            "name": "Replay",
            "destination_city": "Hanoi",
            "start_date": "2026-07-01",
            "end_date": "2026-07-03",
        },
    ).json()
    assert first["id"] == second["id"]


# ---------------------------------------------------------------------------
# GET /trips/{id}  (expanded detail)
# ---------------------------------------------------------------------------


def test_get_trip_by_uuid(client):
    trip = _create_trip(client)
    resp = client.get(f"/trips/{trip['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == trip["id"]


def test_get_trip_by_confirmation_code(client):
    trip = _create_trip(client)
    resp = client.get(f"/trips/{trip['confirmation_code']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == trip["id"]


def test_get_trip_expands_bookings_and_itinerary(client):
    hotel_booking = _make_hotel_booking(client)
    place_id = _first_place_id(client)
    trip = _create_trip(
        client,
        booking_ids=[hotel_booking],
        items=[{"place_id": place_id, "day": 1}],
    )
    detail = client.get(f"/trips/{trip['id']}").json()
    assert len(detail["bookings"]) == 1
    assert detail["bookings"][0]["id"] == hotel_booking
    assert len(detail["itinerary"]) == 1
    assert detail["itinerary"][0]["place"]["id"] == place_id


def test_get_trip_unknown_returns_404(client):
    resp = client.get("/trips/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    assert "hint" in resp.json()


# ---------------------------------------------------------------------------
# GET /trips  (list)
# ---------------------------------------------------------------------------


def test_list_trips_returns_paginated_envelope(client):
    _create_trip(client)
    body = client.get("/trips").json()
    for field in ("total", "limit", "offset", "results"):
        assert field in body


def test_list_trips_filter_by_status(client):
    trip = _create_trip(client, name="To cancel")
    client.delete(f"/trips/{trip['id']}")
    cancelled = client.get(
        "/trips", params={"status": "cancelled", "limit": 500}
    ).json()
    assert all(t["status"] == "cancelled" for t in cancelled["results"])
    assert any(t["id"] == trip["id"] for t in cancelled["results"])


def test_list_trips_search_by_name(client):
    _create_trip(client, name="Unmistakable Honeymoon Trip")
    body = client.get("/trips", params={"q": "honeymoon", "limit": 500}).json()
    assert any("Honeymoon" in t["name"] for t in body["results"])


def test_list_trips_invalid_status_returns_422(client):
    assert client.get("/trips", params={"status": "bogus"}).status_code == 422


# ---------------------------------------------------------------------------
# PATCH /trips/{id}
# ---------------------------------------------------------------------------


def test_patch_trip_renames(client):
    trip = _create_trip(client)
    body = client.patch(f"/trips/{trip['id']}", json={"name": "New name"}).json()
    assert body["name"] == "New name"
    assert body["destination_city"] == trip["destination_city"]  # untouched


def test_patch_trip_changes_status(client):
    trip = _create_trip(client)
    body = client.patch(f"/trips/{trip['id']}", json={"status": "booked"}).json()
    assert body["status"] == "booked"


def test_patch_trip_replaces_items(client):
    place_id = _first_place_id(client)
    trip = _create_trip(client)
    body = client.patch(
        f"/trips/{trip['id']}",
        json={"items": [{"place_id": place_id, "day": 2}]},
    ).json()
    assert len(body["items"]) == 1
    assert body["items"][0]["day"] == 2


def test_patch_trip_empty_body_is_noop(client):
    trip = _create_trip(client)
    body = client.patch(f"/trips/{trip['id']}", json={}).json()
    assert body["name"] == trip["name"]
    assert body["status"] == trip["status"]


def test_patch_trip_invalid_dates_returns_422(client):
    trip = _create_trip(client)
    resp = client.patch(
        f"/trips/{trip['id']}",
        json={"start_date": "2026-06-10", "end_date": "2026-06-05"},
    )
    assert resp.status_code == 422


def test_patch_trip_unknown_returns_404(client):
    resp = client.patch("/trips/no-such-trip", json={"name": "x"})
    assert resp.status_code == 404


def test_patch_trip_unknown_field_returns_422(client):
    trip = _create_trip(client)
    resp = client.patch(f"/trips/{trip['id']}", json={"nights": 9})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /trips/{id}  (soft cancel)
# ---------------------------------------------------------------------------


def test_delete_trip_soft_cancels(client):
    trip = _create_trip(client)
    body = client.delete(f"/trips/{trip['id']}").json()
    assert body["status"] == "cancelled"
    # Still retrievable — soft change.
    assert client.get(f"/trips/{trip['id']}").status_code == 200


def test_delete_trip_is_idempotent(client):
    trip = _create_trip(client)
    client.delete(f"/trips/{trip['id']}")
    second = client.delete(f"/trips/{trip['id']}")
    assert second.status_code == 200
    assert second.json()["status"] == "cancelled"


def test_delete_trip_unknown_returns_404(client):
    assert client.delete("/trips/no-such-trip").status_code == 404
