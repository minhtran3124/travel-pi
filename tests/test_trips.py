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
