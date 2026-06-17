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
