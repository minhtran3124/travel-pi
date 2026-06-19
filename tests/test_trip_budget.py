"""API + enum tests for per-category trip budgets (specs/trip-budget)."""

import pytest
from app.enums import BudgetCategory

from tests.conftest import get_first_flight_booking_fields


def test_budget_category_values():
    assert {c.value for c in BudgetCategory} == {
        "flights",
        "hotels",
        "activities",
        "buffer",
    }


def test_trip_budget_schema_shape():
    from app.schemas.trip import (
        BudgetCategories,
        CategoryBudget,
        TripBudget,
        TripBudgetSet,
    )

    cat = CategoryBudget(cap=700.0, spent=600.0, remaining=100.0)
    cats = BudgetCategories(flights=cat, hotels=cat, activities=cat, buffer=cat)
    budget = TripBudget(
        trip_id="t1",
        categories=cats,
        total_cap=2800.0,
        total_spent=2400.0,
        total_remaining=400.0,
        over_budget=False,
    )
    assert budget.categories.flights.remaining == 100.0
    # POST body: all caps optional, negative rejected
    assert TripBudgetSet(flights=700).flights == 700
    assert TripBudgetSet().flights is None


# --------------------------------------------------------------------------- #
# Task 4: get/set budget (API-level)
# --------------------------------------------------------------------------- #


def _create_trip(client, **overrides):
    body = {"title": "Budget trip", "travelers": 1}
    body.update(overrides)
    resp = client.post("/trips", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_get_budget_no_caps_is_all_null(client):
    trip = _create_trip(client)
    resp = client.get(f"/trips/{trip['id']}/budget")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["trip_id"] == trip["id"]
    assert body["total_cap"] is None
    assert body["total_spent"] == 0.0
    assert body["over_budget"] is False
    for cat in ("flights", "hotels", "activities", "buffer"):
        assert body["categories"][cat]["cap"] is None
        assert body["categories"][cat]["spent"] == 0.0
        assert body["categories"][cat]["remaining"] is None


def test_post_budget_sets_and_get_reflects(client):
    trip = _create_trip(client)
    resp = client.post(
        f"/trips/{trip['id']}/budget",
        json={"flights": 700, "hotels": 600, "activities": 300, "buffer": 200},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["categories"]["flights"]["cap"] == 700.0
    assert body["categories"]["flights"]["remaining"] == 700.0  # nothing spent yet
    assert body["total_cap"] == 1800.0
    # GET mirrors it
    got = client.get(f"/trips/{trip['id']}/budget").json()
    assert got["categories"]["hotels"]["cap"] == 600.0


def test_post_budget_replace_semantics(client):
    trip = _create_trip(client)
    client.post(f"/trips/{trip['id']}/budget", json={"flights": 700})
    # Second POST omits flights → it becomes uncapped again.
    client.post(f"/trips/{trip['id']}/budget", json={"hotels": 500})
    body = client.get(f"/trips/{trip['id']}/budget").json()
    assert body["categories"]["flights"]["cap"] is None
    assert body["categories"]["hotels"]["cap"] == 500.0


def test_post_budget_negative_is_422(client):
    trip = _create_trip(client)
    resp = client.post(f"/trips/{trip['id']}/budget", json={"flights": -1})
    assert resp.status_code == 422


def test_budget_unknown_trip_404(client):
    assert client.get("/trips/nope/budget").status_code == 404
    assert client.post("/trips/nope/budget", json={"flights": 100}).status_code == 404


# --------------------------------------------------------------------------- #
# Task 5: 409 enforcement on item add
# --------------------------------------------------------------------------- #


@pytest.fixture
def _flight_booking(client):
    """Create a real flight booking; return (booking_id, total_price).

    The trip service resolves linked bookings via the *module-level*
    ``get_booking_service()`` singleton (a direct factory call, not FastAPI
    DI), so the conftest's dependency override alone isn't enough — point the
    singleton at the same isolated store the client uses, mirroring how
    conftest wires ``saved_place_service``.
    """
    from app.services import booking_service as booking_service_module
    from app.services.booking_service import get_booking_service

    # Save and restore the singleton so the repoint doesn't leak past this test.
    orig = booking_service_module._booking_service
    booking_service_module._booking_service = client.app.dependency_overrides[
        get_booking_service
    ]()
    try:
        resp = client.post(
            "/flights/book",
            json={
                **get_first_flight_booking_fields(client),
                "passenger_name": "Test User",
                "passenger_email": "test@example.com",
                "passenger_phone": "+84 901 234 567",
            },
        )
        # NB: /flights/book returns 200 (not 201) — it sets no status_code, so
        # FastAPI's POST default applies (see test_flights.py::test_book_flight_returns_200).
        assert resp.status_code == 200, resp.text
        b = resp.json()
        yield b["id"], b["total_price"]
    finally:
        booking_service_module._booking_service = orig


def _add_item(client, trip_id, **overrides):
    body = {"day": 1, "kind": "place", "title": "Stop", "sort_order": 0}
    body.update(overrides)
    return client.post(f"/trips/{trip_id}/items", json=body)


def test_spent_rolls_up_linked_flight_booking(client, _flight_booking):
    booking_id, price = _flight_booking
    trip = _create_trip(client)
    client.post(f"/trips/{trip['id']}/budget", json={"flights": price + 1000})
    resp = _add_item(client, trip["id"], booking_id=booking_id)
    assert resp.status_code == 201, resp.text
    body = client.get(f"/trips/{trip['id']}/budget").json()
    assert body["categories"]["flights"]["spent"] == price
    assert body["categories"]["flights"]["remaining"] == price + 1000 - price


def test_item_add_over_flights_cap_is_409(client, _flight_booking):
    booking_id, price = _flight_booking
    trip = _create_trip(client)
    # Cap below the booking price → adding the linked item must 409.
    client.post(f"/trips/{trip['id']}/budget", json={"flights": price - 1})
    resp = _add_item(client, trip["id"], booking_id=booking_id)
    assert resp.status_code == 409, resp.text
    assert resp.json()["status_code"] == 409
    msg = (resp.json().get("message", "") + resp.json().get("hint", "")).lower()
    assert "flights" in msg and "budget" in msg


def test_item_add_no_cap_for_category_not_blocked(client, _flight_booking):
    booking_id, _price = _flight_booking
    trip = _create_trip(client)
    client.post(f"/trips/{trip['id']}/budget", json={"hotels": 1})  # flights uncapped
    assert _add_item(client, trip["id"], booking_id=booking_id).status_code == 201


def test_item_add_at_cap_boundary_allowed(client, _flight_booking):
    booking_id, price = _flight_booking
    trip = _create_trip(client)
    client.post(f"/trips/{trip['id']}/budget", json={"flights": price})  # exactly equal
    # spent would become exactly the cap; "over" is strictly greater → allowed.
    assert _add_item(client, trip["id"], booking_id=booking_id).status_code == 201


def test_item_add_without_booking_never_blocked(client):
    trip = _create_trip(client)
    client.post(f"/trips/{trip['id']}/budget", json={"flights": 1})
    assert _add_item(client, trip["id"]).status_code == 201  # no booking_id
