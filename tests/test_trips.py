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


# --------------------------------------------------------------------------- #
# CRUD layer (direct TripRepository against a temp DB)
# --------------------------------------------------------------------------- #


@pytest.fixture()
def repo(tmp_path):
    from app.crud.trip import TripRepository

    r = TripRepository(str(tmp_path / "trips_test.db"))
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


def test_repo_delete_trip_cascades_items(repo):
    repo.create_trip(_make_trip(items=[(1, 0, "place", "Bridge")]))
    assert repo.delete_trip("t1") is True
    assert repo.get_trip("t1") is None
    assert repo.get_item("i0") is None


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


# --------------------------------------------------------------------------- #
# Service layer (direct TripService against a temp DB)
# --------------------------------------------------------------------------- #


@pytest.fixture()
def svc(tmp_path):
    from app.services.trip_service import TripService

    s = TripService(str(tmp_path / "svc.db"))
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
