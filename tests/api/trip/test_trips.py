"""Tests for the /trips itinerary feature (schemas, crud, service, endpoints)."""

import pytest
from app.schemas.trip import TripCreate, TripItemCreate
from pydantic import ValidationError

# --------------------------------------------------------------------------- #
# Schema validation
# --------------------------------------------------------------------------- #


def test_trip_create_minimal_ok():
    trip = TripCreate(title="Da Nang weekend")
    assert trip.travelers == 1
    assert trip.items == []


def test_trip_create_rejects_zero_travelers():
    with pytest.raises(ValidationError):
        TripCreate(title="x", travelers=0)


def test_trip_create_rejects_blank_title():
    with pytest.raises(ValidationError):
        TripCreate(title="")


def test_trip_create_rejects_end_before_start():
    with pytest.raises(ValidationError):
        TripCreate(title="x", start_date="2026-06-05", end_date="2026-06-01")


def test_trip_create_allows_equal_dates():
    trip = TripCreate(title="x", start_date="2026-06-01", end_date="2026-06-01")
    assert str(trip.start_date) == "2026-06-01"


def test_trip_item_create_rejects_bad_kind():
    with pytest.raises(ValidationError):
        TripItemCreate(day=1, kind="sightseeing", title="x")


def test_trip_item_create_rejects_day_below_one():
    with pytest.raises(ValidationError):
        TripItemCreate(day=0, kind="place", title="x")


def test_trip_item_status_enum_values():
    from app.enums import TripItemStatus

    assert {s.value for s in TripItemStatus} == {
        "pending",
        "booked",
        "constraint",
        "optional",
    }
    # str-Enum: compares equal to the raw string (JSON/query/store parity)
    assert TripItemStatus.PENDING == "pending"


def test_trip_item_create_default_status_is_pending():
    item = TripItemCreate(day=1, kind="place", title="Marble Mountains")
    from app.enums import TripItemStatus

    assert item.status == TripItemStatus.PENDING


def test_trip_item_create_accepts_each_status():
    for value in ("pending", "booked", "constraint", "optional"):
        item = TripItemCreate(day=1, kind="place", title="x", status=value)
        assert item.status == value


def test_trip_item_create_rejects_bad_status():
    with pytest.raises(ValidationError):
        TripItemCreate(day=1, kind="place", title="x", status="maybe")


# --------------------------------------------------------------------------- #
# CRUD layer (direct TripRepository against a temp DB)
# --------------------------------------------------------------------------- #


@pytest.fixture()
def repo(tmp_path):
    from app.crud.trip import TripRepository
    from app.db.engine import get_session_factory

    r = TripRepository(get_session_factory(f"sqlite:///{tmp_path / 'trips_test.db'}"))
    r.init_db()
    return r


def _make_trip(trip_id="t1", items=()):
    from datetime import datetime, timezone

    from app.schemas.trip import Trip, TripItem

    return Trip(
        id=trip_id,
        title="Trip",
        city="Da Nang",
        travelers=2,
        created_at=datetime.now(timezone.utc),
        items=[
            TripItem(id=f"i{n}", trip_id=trip_id, day=d, sort_order=s, kind=k, title=t)
            for n, (d, s, k, t) in enumerate(items)
        ],
    )


def test_repo_create_and_get_trip(repo):
    repo.create_trip(
        _make_trip(items=[(2, 0, "meal", "Dinner"), (1, 0, "place", "Bridge")])
    )
    got = repo.get_trip("t1")
    assert got is not None
    assert got.title == "Trip"
    # items come back sorted by (day, sort_order)
    assert [i.title for i in got.items] == ["Bridge", "Dinner"]


def test_repo_get_missing_returns_none(repo):
    assert repo.get_trip("nope") is None


def test_repo_soft_delete_trip(repo):
    repo.create_trip(_make_trip(items=[(1, 0, "place", "Bridge")]))
    assert repo.delete_trip("t1", when="2026-06-17T00:00:00+00:00") is True
    # trip is filtered out of reads...
    assert repo.get_trip("t1") is None
    # ...but its items are retained (data not destroyed).
    assert repo.get_item("i0") is not None


def test_repo_add_update_delete_item(repo):
    repo.create_trip(_make_trip())
    from app.schemas.trip import TripItem

    repo.add_item(TripItem(id="x1", trip_id="t1", day=1, kind="activity", title="Surf"))
    assert repo.get_item("x1").title == "Surf"
    repo.update_item(
        TripItem(id="x1", trip_id="t1", day=2, kind="activity", title="Dive")
    )
    updated = repo.get_item("x1")
    assert updated.day == 2 and updated.title == "Dive"
    assert repo.delete_item("x1") is True
    assert repo.get_item("x1") is None


def test_repo_persists_item_status_roundtrip(repo):
    from datetime import datetime, timezone

    from app.enums import TripItemStatus
    from app.schemas.trip import Trip, TripItem

    trip = Trip(
        id="t-status",
        title="Status trip",
        travelers=1,
        created_at=datetime.now(timezone.utc),
    )
    item = TripItem(
        id="i-1",
        trip_id="t-status",
        day=1,
        sort_order=0,
        kind="place",
        title="Anchor",
        status=TripItemStatus.CONSTRAINT,
    )
    repo.create_trip(trip)
    repo.add_item(item)

    got = repo.get_item("i-1")
    assert got.status == TripItemStatus.CONSTRAINT

    got.status = TripItemStatus.OPTIONAL
    assert repo.update_item(got) is True
    assert repo.get_item("i-1").status == TripItemStatus.OPTIONAL


def test_repo_item_defaults_status_pending_when_unset(repo):
    from datetime import datetime, timezone

    from app.enums import TripItemStatus
    from app.schemas.trip import Trip, TripItem

    trip = Trip(
        id="t-def",
        title="Default trip",
        travelers=1,
        created_at=datetime.now(timezone.utc),
    )
    repo.create_trip(trip)
    repo.add_item(
        TripItem(id="i-2", trip_id="t-def", day=1, sort_order=0, kind="note", title="x")
    )
    assert repo.get_item("i-2").status == TripItemStatus.PENDING


# --------------------------------------------------------------------------- #
# Service layer (direct TripService against a temp DB)
# --------------------------------------------------------------------------- #


@pytest.fixture()
def svc(tmp_path):
    from app.services.trip_service import TripService

    s = TripService(f"sqlite:///{tmp_path / 'svc.db'}")
    s.init_db()
    return s


def test_service_create_returns_trip_with_ids(svc):
    from app.schemas.trip import TripCreate, TripItemCreate

    trip = svc.create_trip(
        TripCreate(
            title="DN", items=[TripItemCreate(day=1, kind="place", title="Bridge")]
        )
    )
    assert trip.id
    assert trip.items[0].id and trip.items[0].trip_id == trip.id


def test_service_get_missing_raises_not_found(svc):
    from app.exceptions import NotFoundError

    with pytest.raises(NotFoundError):
        svc.get_trip("missing")


def test_service_update_trip(svc):
    from app.schemas.trip import TripCreate, TripUpdate

    trip = svc.create_trip(TripCreate(title="Old"))
    updated = svc.update_trip(trip.id, TripUpdate(title="New", travelers=3))
    assert updated.title == "New" and updated.travelers == 3


def test_service_delete_trip(svc):
    from app.exceptions import NotFoundError
    from app.schemas.trip import TripCreate

    trip = svc.create_trip(TripCreate(title="Bye"))
    svc.delete_trip(trip.id)
    with pytest.raises(NotFoundError):
        svc.get_trip(trip.id)


def test_service_item_wrong_trip_raises(svc):
    from app.exceptions import NotFoundError
    from app.schemas.trip import TripCreate, TripItemCreate, TripItemUpdate

    a = svc.create_trip(TripCreate(title="A"))
    b = svc.create_trip(TripCreate(title="B"))
    item = svc.add_item(a.id, TripItemCreate(day=1, kind="meal", title="Lunch"))
    # item belongs to A, not B -> 404 when addressed via B
    with pytest.raises(NotFoundError):
        svc.update_item(b.id, item.id, TripItemUpdate(day=1, kind="meal", title="x"))


def test_gap_detection_treats_optional_as_unplanned(svc):
    """A day whose only item is optional is still flagged 'no planned items'."""
    from app.enums import TripItemStatus
    from app.schemas.trip import TripCreate, TripItemCreate

    trip = svc.create_trip(
        TripCreate(
            title="Gap trip",
            start_date="2026-07-01",
            end_date="2026-07-01",  # single day
            items=[
                TripItemCreate(
                    day=1,
                    kind="place",
                    title="Maybe-museum",
                    status=TripItemStatus.OPTIONAL,
                )
            ],
        )
    )
    detail = svc.get_trip_detail(trip.id)
    assert any("Day 1 has no planned items" in g for g in detail.gaps)


def test_gap_detection_counts_non_optional_item(svc):
    """A day with a pending item is NOT flagged 'no planned items'."""
    from app.schemas.trip import TripCreate, TripItemCreate

    trip = svc.create_trip(
        TripCreate(
            title="Planned trip",
            start_date="2026-07-01",
            end_date="2026-07-01",
            items=[TripItemCreate(day=1, kind="place", title="Confirmed stop")],
        )
    )
    detail = svc.get_trip_detail(trip.id)
    assert not any("Day 1 has no planned items" in g for g in detail.gaps)


# --------------------------------------------------------------------------- #
# Endpoints (full stack via TestClient)
# --------------------------------------------------------------------------- #


def _create_trip(client, **over):
    body = {"title": "Da Nang weekend", "city": "Da Nang", "travelers": 2}
    body.update(over)
    return client.post("/trips", json=body)


def test_post_trip_returns_201_with_id(client):
    resp = _create_trip(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] and body["title"] == "Da Nang weekend"
    assert body["items"] == []


def test_post_trip_with_items(client):
    resp = _create_trip(
        client,
        items=[
            {"day": 2, "kind": "meal", "title": "Dinner"},
            {"day": 1, "kind": "place", "title": "Dragon Bridge"},
        ],
    )
    assert resp.status_code == 201
    titles = [i["title"] for i in resp.json()["items"]]
    assert titles == ["Dragon Bridge", "Dinner"]  # sorted by (day, sort_order)


def test_post_trip_invalid_body_422(client):
    assert _create_trip(client, travelers=0).status_code == 422
    assert _create_trip(client, title="").status_code == 422
    assert (
        _create_trip(client, start_date="2026-06-05", end_date="2026-06-01").status_code
        == 422
    )


def test_get_trip_roundtrip(client):
    trip_id = _create_trip(client).json()["id"]
    got = client.get(f"/trips/{trip_id}")
    assert got.status_code == 200 and got.json()["id"] == trip_id


def test_get_missing_trip_404(client):
    assert client.get("/trips/does-not-exist").status_code == 404


def test_list_trips_paginated_envelope(client):
    _create_trip(client)
    body = client.get("/trips").json()
    for field in ("total", "limit", "offset", "results"):
        assert field in body


def test_put_trip_replaces_fields(client):
    trip_id = _create_trip(client).json()["id"]
    resp = client.put(f"/trips/{trip_id}", json={"title": "Renamed", "travelers": 4})
    assert resp.status_code == 200
    assert resp.json()["title"] == "Renamed" and resp.json()["travelers"] == 4


def test_delete_trip_204_then_404(client):
    trip_id = _create_trip(client).json()["id"]
    assert client.delete(f"/trips/{trip_id}").status_code == 204
    assert client.get(f"/trips/{trip_id}").status_code == 404


def test_item_crud_via_endpoints(client):
    trip_id = _create_trip(client).json()["id"]
    add = client.post(
        f"/trips/{trip_id}/items", json={"day": 1, "kind": "activity", "title": "Surf"}
    )
    assert add.status_code == 201
    item_id = add.json()["id"]
    upd = client.put(
        f"/trips/{trip_id}/items/{item_id}",
        json={"day": 2, "kind": "activity", "title": "Dive"},
    )
    assert upd.status_code == 200 and upd.json()["title"] == "Dive"
    assert client.get(f"/trips/{trip_id}").json()["items"][0]["title"] == "Dive"
    assert client.delete(f"/trips/{trip_id}/items/{item_id}").status_code == 204
    assert client.get(f"/trips/{trip_id}").json()["items"] == []


def test_add_item_to_missing_trip_404(client):
    resp = client.post(
        "/trips/missing/items", json={"day": 1, "kind": "note", "title": "x"}
    )
    assert resp.status_code == 404


def test_item_bad_kind_422(client):
    trip_id = _create_trip(client).json()["id"]
    resp = client.post(
        f"/trips/{trip_id}/items", json={"day": 1, "kind": "bogus", "title": "x"}
    )
    assert resp.status_code == 422


# --------------------------------------------------------------------------- #
# Budget estimate — schema validation
# --------------------------------------------------------------------------- #


def test_estimate_request_minimal_defaults():
    from app.schemas.trip import TripEstimateRequest

    req = TripEstimateRequest(nights=2, travelers=1)
    assert req.meal_style == "mid"
    assert req.activity_level == "some"
    assert req.flight_total_usd is None
    assert req.hotel_price_per_night_usd is None


def test_estimate_request_rejects_zero_nights():
    import pytest
    from app.schemas.trip import TripEstimateRequest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TripEstimateRequest(nights=0, travelers=1)


def test_estimate_request_rejects_zero_travelers():
    import pytest
    from app.schemas.trip import TripEstimateRequest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TripEstimateRequest(nights=1, travelers=0)


def test_estimate_request_rejects_bad_meal_style():
    import pytest
    from app.schemas.trip import TripEstimateRequest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TripEstimateRequest(nights=1, travelers=1, meal_style="lavish")


def test_estimate_request_rejects_bad_activity_level():
    import pytest
    from app.schemas.trip import TripEstimateRequest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TripEstimateRequest(nights=1, travelers=1, activity_level="extreme")


def test_estimate_request_rejects_negative_costs():
    import pytest
    from app.schemas.trip import TripEstimateRequest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TripEstimateRequest(nights=1, travelers=1, flight_total_usd=-5)
    with pytest.raises(ValidationError):
        TripEstimateRequest(nights=1, travelers=1, hotel_price_per_night_usd=-1)


# --------------------------------------------------------------------------- #
# Budget estimate — pure calculator
# --------------------------------------------------------------------------- #


def test_estimate_worked_example_matches_spec():
    from app.schemas.trip import TripEstimateRequest
    from app.services.trip_service import estimate_trip

    res = estimate_trip(
        TripEstimateRequest(
            city="Da Nang",
            nights=3,
            travelers=2,
            flight_total_usd=240,
            hotel_price_per_night_usd=90,
            meal_style="mid",
            activity_level="some",
        )
    )
    assert res.breakdown.flights == 240
    assert res.breakdown.accommodation == 270
    assert res.breakdown.meals == 180
    assert res.breakdown.activities == 120
    assert res.breakdown.local_transport == 45
    assert res.subtotal == 855
    assert res.buffer_pct == 10
    assert res.total_estimate == 941
    assert res.per_person == 470.5
    assert res.currency == "USD"
    assert res.city == "Da Nang"


def test_estimate_missing_flight_zeroes_line_and_notes_assumption():
    from app.schemas.trip import TripEstimateRequest
    from app.services.trip_service import estimate_trip

    res = estimate_trip(
        TripEstimateRequest(nights=2, travelers=1, hotel_price_per_night_usd=50)
    )
    assert res.breakdown.flights == 0
    assert any("flight" in a.lower() for a in res.assumptions)


def test_estimate_missing_hotel_zeroes_line_and_notes_assumption():
    from app.schemas.trip import TripEstimateRequest
    from app.services.trip_service import estimate_trip

    res = estimate_trip(
        TripEstimateRequest(nights=2, travelers=1, flight_total_usd=100)
    )
    assert res.breakdown.accommodation == 0
    assert any("accommodation" in a.lower() for a in res.assumptions)


def test_estimate_rounds_total_half_up_to_whole_dollars():
    # nights=1, travelers=1, hotel=49 -> accommodation 49, meals mid 30,
    # activities some 20, local 15 => subtotal 114; *1.1 = 125.4 -> 125.
    from app.schemas.trip import TripEstimateRequest
    from app.services.trip_service import estimate_trip

    res = estimate_trip(
        TripEstimateRequest(nights=1, travelers=1, hotel_price_per_night_usd=49)
    )
    assert res.subtotal == 114
    assert res.total_estimate == 125  # 125.4 rounds down; not a .5 boundary
    assert res.per_person == 125


# --------------------------------------------------------------------------- #
# Budget estimate — endpoint (full stack via TestClient)
# --------------------------------------------------------------------------- #


def test_post_estimate_happy_path(client):
    resp = client.post(
        "/trips/estimate",
        json={
            "city": "Da Nang",
            "nights": 3,
            "travelers": 2,
            "flight_total_usd": 240,
            "hotel_price_per_night_usd": 90,
            "meal_style": "mid",
            "activity_level": "some",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["breakdown"]["accommodation"] == 270
    assert body["subtotal"] == 855
    assert body["total_estimate"] == 941
    assert body["per_person"] == 470.5
    assert isinstance(body["assumptions"], list) and body["assumptions"]


def test_post_estimate_minimal_body_ok(client):
    # only required fields -> defaults applied, still 200
    resp = client.post("/trips/estimate", json={"nights": 2, "travelers": 1})
    assert resp.status_code == 200
    assert resp.json()["breakdown"]["flights"] == 0


def test_post_estimate_bad_enum_returns_422(client):
    resp = client.post(
        "/trips/estimate",
        json={"nights": 1, "travelers": 1, "meal_style": "lavish"},
    )
    assert resp.status_code == 422


def test_post_estimate_zero_nights_returns_422(client):
    resp = client.post("/trips/estimate", json={"nights": 0, "travelers": 1})
    assert resp.status_code == 422


def test_create_trip_idempotent(client):
    payload = {"title": "Idem Trip", "travelers": 2}
    h = {"Idempotency-Key": "trip-key-1"}
    first = client.post("/trips", json=payload, headers=h).json()
    second = client.post("/trips", json=payload, headers=h).json()
    assert first["id"] == second["id"]
    ids = [t["id"] for t in client.get("/trips").json()["results"]]
    assert ids.count(first["id"]) == 1


def test_add_item_idempotent(client):
    trip = client.post("/trips", json={"title": "T", "travelers": 1}).json()
    item = {"day": 1, "kind": "note", "title": "X"}
    h = {"Idempotency-Key": "item-key-1"}
    first = client.post(f"/trips/{trip['id']}/items", json=item, headers=h).json()
    second = client.post(f"/trips/{trip['id']}/items", json=item, headers=h).json()
    assert first["id"] == second["id"]


def test_add_item_idempotency_key_reuse_across_trips_conflicts(client):
    a = client.post("/trips", json={"title": "A", "travelers": 1}).json()
    b = client.post("/trips", json={"title": "B", "travelers": 1}).json()
    item = {"day": 1, "kind": "note", "title": "X"}
    h = {"Idempotency-Key": "shared-key"}
    assert (
        client.post(f"/trips/{a['id']}/items", json=item, headers=h).status_code == 201
    )
    # Same key against a different trip is a conflict, not a wrong-item replay.
    resp = client.post(f"/trips/{b['id']}/items", json=item, headers=h)
    assert resp.status_code == 409


def test_delete_trip_is_soft(client):
    trip = client.post("/trips", json={"title": "Doomed", "travelers": 1}).json()
    assert client.delete(f"/trips/{trip['id']}").status_code == 204
    assert client.get(f"/trips/{trip['id']}").status_code == 404
    ids = [t["id"] for t in client.get("/trips").json()["results"]]
    assert trip["id"] not in ids
    # idempotent: already-deleted → 404, not 500
    assert client.delete(f"/trips/{trip['id']}").status_code == 404


def test_idempotency_key_reusable_after_soft_delete(client):
    # Create with a key, soft-delete the trip, then reuse the same key:
    # the tombstoned row's key is cleared, so the re-create must succeed (not 500).
    h = {"Idempotency-Key": "recycle-key"}
    first = client.post(
        "/trips", json={"title": "One", "travelers": 1}, headers=h
    ).json()
    assert client.delete(f"/trips/{first['id']}").status_code == 204
    resp = client.post("/trips", json={"title": "Two", "travelers": 1}, headers=h)
    assert resp.status_code == 201
    assert resp.json()["id"] != first["id"]
