"""Tests for `TripBudget.booked_total` (Task 3.2, SC-6).

``booked_total`` is deliberately NOT a fix for ``total_spent`` — it is a
second, independent number: every non-cancelled booking carrying the trip's
``trip_id``, counted once. ``total_spent`` keeps walking itinerary items and
skipping/double-counting exactly as it always has. These tests pin the
divergence between the two, not paper over it.
"""

from tests.conftest import get_first_flight_booking_fields


def _create_trip(client, **overrides):
    body = {"title": "Booked total trip", "travelers": 1}
    body.update(overrides)
    resp = client.post("/trips", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _book_flight(client, trip_id=None, **overrides):
    """Book a real flight (optionally linked to ``trip_id``); return (id, total_price)."""
    body = {
        **get_first_flight_booking_fields(client),
        "passenger_name": "Booked Total Test",
        "passenger_email": "booked-total@example.com",
        "passenger_phone": "+84 901 234 567",
    }
    if trip_id is not None:
        body["trip_id"] = trip_id
    body.update(overrides)
    resp = client.post("/flights/book", json=body)
    assert resp.status_code == 200, resp.text
    b = resp.json()
    return b["id"], b["total_price"]


def _add_item(client, trip_id, **overrides):
    body = {"day": 1, "kind": "place", "title": "Stop", "sort_order": 0}
    body.update(overrides)
    resp = client.post(f"/trips/{trip_id}/items", json=body)
    assert resp.status_code == 201, resp.text
    return resp


def test_booked_total_counts_a_booking_no_item_references(client):
    """A booking carrying trip_id but referenced by no item: booked_total > 0,
    total_spent stays at zero (no item to walk)."""
    trip = _create_trip(client)
    _booking_id, price = _book_flight(client, trip_id=trip["id"])

    resp = client.get(f"/trips/{trip['id']}/budget")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["booked_total"] == price
    assert body["total_spent"] == 0


def test_booked_total_counts_once_total_spent_counts_twice(client):
    """A booking referenced by two itinerary items: booked_total counts it
    once (booking-level), total_spent counts it twice (per-item, unchanged)."""
    trip = _create_trip(client)
    booking_id, price = _book_flight(client, trip_id=trip["id"])
    _add_item(client, trip["id"], booking_id=booking_id, sort_order=0)
    _add_item(client, trip["id"], booking_id=booking_id, sort_order=1)

    resp = client.get(f"/trips/{trip['id']}/budget")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["booked_total"] == price
    assert body["total_spent"] == price * 2


def test_cancelled_booking_counts_in_neither(client):
    """A cancelled booking carrying trip_id contributes to neither number."""
    trip = _create_trip(client)
    booking_id, _price = _book_flight(client, trip_id=trip["id"])
    _add_item(client, trip["id"], booking_id=booking_id)

    cancel_resp = client.post(f"/bookings/{booking_id}/cancel")
    assert cancel_resp.status_code == 200, cancel_resp.text

    resp = client.get(f"/trips/{trip['id']}/budget")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["booked_total"] == 0
    assert body["total_spent"] == 0
