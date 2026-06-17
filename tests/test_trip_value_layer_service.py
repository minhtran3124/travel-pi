"""Tests for TripService value-layer methods: get_trip_detail and get_day_plan.

Coverage:
- total_spent: sums confirmed bookings; excludes cancelled; skips unresolvable.
- gaps: flags days with no items; flags days with no hotel booking; clear on
  full coverage; empty when trip has no dates.
- get_day_plan: returns items for the right day sorted by sort_order; last
  item has null travel fields; trips without start_date raise ConflictError.
"""

import asyncio
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from app.enums import BookingStatus, BookingType
from app.exceptions import ConflictError, NotFoundError
from app.schemas.trip import TripCreate, TripItemCreate

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture()
def svc(tmp_path):
    from app.services.trip_service import TripService

    s = TripService(str(tmp_path / "value_layer.db"))
    s.init_db()
    return s


def _hotel_booking(
    booking_id: str, price: float, status: BookingStatus = BookingStatus.CONFIRMED
):
    """Build a lightweight mock Booking for hotel."""
    b = MagicMock()
    b.id = booking_id
    b.type = BookingType.HOTEL
    b.total_price = price
    b.status = status
    return b


def _flight_booking(booking_id: str, price: float):
    b = MagicMock()
    b.id = booking_id
    b.type = BookingType.FLIGHT
    b.total_price = price
    b.status = BookingStatus.CONFIRMED
    return b


def _mock_booking_svc(bookings_by_id: dict):
    """Return a mock BookingService whose .get() resolves from bookings_by_id."""

    def _get(bid):
        if bid not in bookings_by_id:
            raise NotFoundError(f"Booking {bid!r} not found")
        return bookings_by_id[bid]

    svc = MagicMock()
    svc.get = _get
    return svc


# --------------------------------------------------------------------------- #
# get_trip_detail — total_spent
# --------------------------------------------------------------------------- #


def test_total_spent_sums_two_confirmed_bookings(svc):
    """Two confirmed hotel bookings → total_spent is their combined price."""
    trip = svc.create_trip(
        TripCreate(
            title="Test",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 2),
            items=[
                TripItemCreate(day=1, kind="place", title="Hotel A", booking_id="b1"),
                TripItemCreate(day=2, kind="place", title="Hotel B", booking_id="b2"),
            ],
        )
    )
    mock_svc = _mock_booking_svc(
        {"b1": _hotel_booking("b1", 100.0), "b2": _hotel_booking("b2", 150.0)}
    )

    with patch("app.services.trip_service.get_booking_service", return_value=mock_svc):
        detail = svc.get_trip_detail(trip.id)

    assert detail.total_spent == 250.0


def test_total_spent_excludes_cancelled_booking(svc):
    """A cancelled booking is not counted in total_spent."""
    trip = svc.create_trip(
        TripCreate(
            title="Test",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 1),
            items=[
                TripItemCreate(
                    day=1, kind="place", title="Cancelled hotel", booking_id="b1"
                ),
                TripItemCreate(
                    day=1, kind="place", title="Active hotel", booking_id="b2"
                ),
            ],
        )
    )
    mock_svc = _mock_booking_svc(
        {
            "b1": _hotel_booking("b1", 200.0, BookingStatus.CANCELLED),
            "b2": _hotel_booking("b2", 80.0),
        }
    )

    with patch("app.services.trip_service.get_booking_service", return_value=mock_svc):
        detail = svc.get_trip_detail(trip.id)

    assert detail.total_spent == 80.0


def test_total_spent_skips_unresolvable_booking_no_raise(svc):
    """NotFoundError from the booking service is swallowed; item is skipped."""
    trip = svc.create_trip(
        TripCreate(
            title="Test",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 1),
            items=[
                TripItemCreate(
                    day=1, kind="note", title="Unknown ref", booking_id="ghost"
                ),
                TripItemCreate(
                    day=1, kind="place", title="Real hotel", booking_id="b2"
                ),
            ],
        )
    )
    # "ghost" is not in the dict → NotFoundError will be raised and swallowed.
    mock_svc = _mock_booking_svc({"b2": _hotel_booking("b2", 50.0)})

    with patch("app.services.trip_service.get_booking_service", return_value=mock_svc):
        detail = svc.get_trip_detail(trip.id)  # must not raise

    assert detail.total_spent == 50.0


def test_total_spent_flight_booking_counts(svc):
    """Flight bookings (non-hotel) also roll up into total_spent."""
    trip = svc.create_trip(
        TripCreate(
            title="Test",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 1),
            items=[
                TripItemCreate(
                    day=1, kind="transport", title="Flight", booking_id="f1"
                ),
            ],
        )
    )
    mock_svc = _mock_booking_svc({"f1": _flight_booking("f1", 300.0)})

    with patch("app.services.trip_service.get_booking_service", return_value=mock_svc):
        detail = svc.get_trip_detail(trip.id)

    assert detail.total_spent == 300.0


# --------------------------------------------------------------------------- #
# get_trip_detail — gaps
# --------------------------------------------------------------------------- #


def test_gaps_day_with_no_items_emits_no_planned_items(svc):
    """Day 2 has no items in a 3-day trip → gaps contains a message for Day 2."""
    trip = svc.create_trip(
        TripCreate(
            title="Test",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 3),
            items=[
                TripItemCreate(day=1, kind="place", title="Museum", booking_id="b1"),
                TripItemCreate(day=3, kind="meal", title="Dinner", booking_id="b2"),
            ],
        )
    )
    mock_svc = _mock_booking_svc(
        {"b1": _hotel_booking("b1", 100.0), "b2": _hotel_booking("b2", 50.0)}
    )

    with patch("app.services.trip_service.get_booking_service", return_value=mock_svc):
        detail = svc.get_trip_detail(trip.id)

    assert any("Day 2" in g and "no planned items" in g for g in detail.gaps)


def test_gaps_day_without_hotel_booking_emits_accommodation_message(svc):
    """A day with items but no confirmed hotel booking → accommodation gap."""
    trip = svc.create_trip(
        TripCreate(
            title="Test",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 1),
            items=[
                TripItemCreate(day=1, kind="meal", title="Breakfast"),  # no booking_id
            ],
        )
    )
    # booking service never called (no booking_id on item), so empty dict is fine
    mock_svc = _mock_booking_svc({})

    with patch("app.services.trip_service.get_booking_service", return_value=mock_svc):
        detail = svc.get_trip_detail(trip.id)

    assert any("Day 1" in g and "accommodation" in g for g in detail.gaps)


def test_gaps_all_days_covered_no_accommodation_gap(svc):
    """Every day has a confirmed hotel booking → no accommodation gap messages."""
    trip = svc.create_trip(
        TripCreate(
            title="Test",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 2),
            items=[
                TripItemCreate(day=1, kind="place", title="Hotel D1", booking_id="b1"),
                TripItemCreate(day=2, kind="place", title="Hotel D2", booking_id="b2"),
            ],
        )
    )
    mock_svc = _mock_booking_svc(
        {"b1": _hotel_booking("b1", 100.0), "b2": _hotel_booking("b2", 100.0)}
    )

    with patch("app.services.trip_service.get_booking_service", return_value=mock_svc):
        detail = svc.get_trip_detail(trip.id)

    assert all("accommodation" not in g for g in detail.gaps)


def test_gaps_empty_when_trip_has_no_dates(svc):
    """Undated trips cannot reason about days — gaps must be an empty list."""
    trip = svc.create_trip(TripCreate(title="Undated"))
    mock_svc = _mock_booking_svc({})

    with patch("app.services.trip_service.get_booking_service", return_value=mock_svc):
        detail = svc.get_trip_detail(trip.id)

    assert detail.gaps == []


# --------------------------------------------------------------------------- #
# get_day_plan — items and ordering
# --------------------------------------------------------------------------- #


def test_day_plan_returns_items_for_correct_day_only(svc):
    """Items on other days are excluded; only the target date's items appear."""
    trip = svc.create_trip(
        TripCreate(
            title="Test",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 3),
            items=[
                TripItemCreate(day=1, sort_order=0, kind="place", title="A"),
                TripItemCreate(day=2, sort_order=0, kind="meal", title="Lunch"),
                TripItemCreate(day=1, sort_order=1, kind="activity", title="B"),
            ],
        )
    )
    result = asyncio.run(svc.get_day_plan(trip.id, date(2026, 7, 1)))

    assert result.trip_id == trip.id
    assert result.day == 1
    assert result.date == date(2026, 7, 1)
    assert len(result.items) == 2
    titles = [di.item.title for di in result.items]
    assert titles == ["A", "B"]  # sort_order 0, then 1


def test_day_plan_items_ordered_by_sort_order(svc):
    """Items within a day are returned in ascending sort_order."""
    trip = svc.create_trip(
        TripCreate(
            title="Test",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 1),
            items=[
                TripItemCreate(day=1, sort_order=2, kind="place", title="Third"),
                TripItemCreate(day=1, sort_order=0, kind="place", title="First"),
                TripItemCreate(day=1, sort_order=1, kind="place", title="Second"),
            ],
        )
    )
    result = asyncio.run(svc.get_day_plan(trip.id, date(2026, 7, 1)))

    titles = [di.item.title for di in result.items]
    assert titles == ["First", "Second", "Third"]


def test_day_plan_last_item_has_null_travel_fields(svc):
    """The final DayPlanItem always has travel_to_next_* = None."""
    trip = svc.create_trip(
        TripCreate(
            title="Test",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 1),
            items=[
                TripItemCreate(day=1, sort_order=0, kind="place", title="First"),
                TripItemCreate(day=1, sort_order=1, kind="place", title="Last"),
            ],
        )
    )
    result = asyncio.run(svc.get_day_plan(trip.id, date(2026, 7, 1)))

    last = result.items[-1]
    assert last.travel_to_next_minutes is None
    assert last.travel_to_next_mode is None


def test_day_plan_empty_day_returns_empty_items_list(svc):
    """Requesting a day with no items returns an empty items list (no error)."""
    trip = svc.create_trip(
        TripCreate(
            title="Test",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 2),
            items=[
                TripItemCreate(day=1, kind="place", title="Something"),
            ],
        )
    )
    result = asyncio.run(svc.get_day_plan(trip.id, date(2026, 7, 2)))

    assert result.items == []
    assert result.day == 2


# --------------------------------------------------------------------------- #
# get_day_plan — ConflictError on missing start_date
# --------------------------------------------------------------------------- #


def test_day_plan_no_start_date_raises_conflict_error(svc):
    """Trip without start_date raises ConflictError with status_code 409."""
    trip = svc.create_trip(TripCreate(title="Undated"))

    with pytest.raises(ConflictError) as exc_info:
        asyncio.run(svc.get_day_plan(trip.id, date(2026, 7, 1)))

    assert exc_info.value.status_code == 409
    assert "start_date" in exc_info.value.hint


def test_day_plan_missing_trip_raises_not_found(svc):
    """Unknown trip_id propagates NotFoundError (404) from get_trip."""
    with pytest.raises(NotFoundError):
        asyncio.run(svc.get_day_plan("does-not-exist", date(2026, 7, 1)))
