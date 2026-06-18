"""API-level tests for the value-layer additions: TripDetail and day-plan.

Covers:
- GET /trips/{id}        → returns TripDetail (total_spent + gaps present)
- GET /trips/{id}/day-plan?date=  → 200 with day/items when trip has start_date
- GET /trips/{id}/day-plan?date=  → 409 when trip has no start_date
- GET /trips/unknown/day-plan?date=  → 404

All tests are deterministic and offline: items use no place_ids so routing is
never attempted.
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_trip(client, **overrides):
    body = {"title": "Test trip", "travelers": 1}
    body.update(overrides)
    resp = client.post("/trips", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _add_item(client, trip_id, **overrides):
    body = {"day": 1, "kind": "place", "title": "Stop A", "sort_order": 0}
    body.update(overrides)
    resp = client.post(f"/trips/{trip_id}/items", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# GET /trips/{id} → TripDetail
# ---------------------------------------------------------------------------


def test_get_trip_detail_has_value_layer_fields(client):
    """Detail endpoint returns total_spent (float) and gaps (list)."""
    trip = _create_trip(client)
    resp = client.get(f"/trips/{trip['id']}")
    assert resp.status_code == 200
    body = resp.json()
    assert "total_spent" in body
    assert isinstance(body["total_spent"], float)
    assert "gaps" in body
    assert isinstance(body["gaps"], list)


def test_get_trip_detail_total_spent_zero_no_bookings(client):
    """A trip with no linked bookings has total_spent == 0.0."""
    trip = _create_trip(client, start_date="2026-08-01", end_date="2026-08-03")
    _add_item(client, trip["id"], day=1, kind="place", title="Museum")
    resp = client.get(f"/trips/{trip['id']}")
    assert resp.status_code == 200
    assert resp.json()["total_spent"] == 0.0


def test_get_trip_detail_gaps_reported_for_days_without_items(client):
    """Gaps list includes a message for a day that has no items."""
    # 2-day trip with an item only on day 1 → day 2 should appear in gaps
    trip = _create_trip(client, start_date="2026-09-01", end_date="2026-09-02")
    _add_item(client, trip["id"], day=1, kind="place", title="Beach")
    resp = client.get(f"/trips/{trip['id']}")
    assert resp.status_code == 200
    gaps = resp.json()["gaps"]
    assert any("2" in g for g in gaps), f"Expected day-2 gap, got: {gaps}"


def test_get_trip_detail_unknown_returns_404(client):
    assert client.get("/trips/nonexistent-trip-id").status_code == 404


# ---------------------------------------------------------------------------
# GET /trips/{id}/day-plan
# ---------------------------------------------------------------------------


def test_day_plan_returns_200_with_correct_day(client):
    """day-plan for a trip with start_date returns the right day number and items."""
    trip = _create_trip(client, start_date="2026-07-10", end_date="2026-07-12")
    # Add two items on day 2 (2026-07-11), no place_id → routing skipped
    _add_item(client, trip["id"], day=2, kind="place", title="Temple", sort_order=0)
    _add_item(client, trip["id"], day=2, kind="meal", title="Lunch", sort_order=1)

    resp = client.get(f"/trips/{trip['id']}/day-plan", params={"date": "2026-07-11"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["day"] == 2
    assert body["date"] == "2026-07-11"
    assert body["trip_id"] == trip["id"]
    assert len(body["items"]) == 2
    # items ordered by sort_order
    assert body["items"][0]["item"]["title"] == "Temple"
    assert body["items"][1]["item"]["title"] == "Lunch"


def test_day_plan_includes_item_status(client):
    """status rides through the day-plan via the embedded TripItem."""
    trip = _create_trip(client, start_date="2026-07-10", end_date="2026-07-12")
    _add_item(
        client, trip["id"], day=1, kind="place", title="Fixed tour", status="constraint"
    )

    resp = client.get(f"/trips/{trip['id']}/day-plan", params={"date": "2026-07-10"})
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(pi["item"]["status"] == "constraint" for pi in items)


def test_day_plan_empty_items_for_date_with_no_stops(client):
    """day-plan for a valid date that has no items returns empty items list."""
    trip = _create_trip(client, start_date="2026-07-01", end_date="2026-07-03")
    # Only day 1 has an item; query day 3
    _add_item(client, trip["id"], day=1, kind="note", title="Arrive")

    resp = client.get(f"/trips/{trip['id']}/day-plan", params={"date": "2026-07-03"})
    assert resp.status_code == 200
    assert resp.json()["items"] == []
    assert resp.json()["day"] == 3


def test_day_plan_no_start_date_returns_409(client):
    """409 when the trip has no start_date set."""
    trip = _create_trip(client)  # no start_date
    resp = client.get(f"/trips/{trip['id']}/day-plan", params={"date": "2026-07-10"})
    assert resp.status_code == 409


def test_day_plan_unknown_trip_returns_404(client):
    """404 for an unrecognised trip UUID."""
    resp = client.get("/trips/does-not-exist/day-plan", params={"date": "2026-07-10"})
    assert resp.status_code == 404


def test_day_plan_travel_fields_null_without_place_ids(client):
    """travel_to_next_* fields are None when items have no place_id (offline)."""
    trip = _create_trip(client, start_date="2026-08-05", end_date="2026-08-05")
    _add_item(client, trip["id"], day=1, kind="place", title="Stop 1", sort_order=0)
    _add_item(client, trip["id"], day=1, kind="place", title="Stop 2", sort_order=1)

    resp = client.get(f"/trips/{trip['id']}/day-plan", params={"date": "2026-08-05"})
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 2
    # No place_ids → routing never attempted → travel fields stay None
    assert items[0]["travel_to_next_minutes"] is None
    assert items[0]["travel_to_next_mode"] is None
    # Last item always None
    assert items[1]["travel_to_next_minutes"] is None
