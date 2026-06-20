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
    from app.db.base import Base
    from app.db.engine import get_engine, get_session_factory
    from app.services.trip_service import TripService

    url = f"sqlite:///{tmp_path / 'value_layer.db'}"
    Base.metadata.create_all(get_engine(url), checkfirst=True)
    with get_session_factory(url)() as session:
        yield TripService(session)


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

    with patch("app.services.trip_service.BookingService", return_value=mock_svc):
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

    with patch("app.services.trip_service.BookingService", return_value=mock_svc):
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

    with patch("app.services.trip_service.BookingService", return_value=mock_svc):
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

    with patch("app.services.trip_service.BookingService", return_value=mock_svc):
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

    with patch("app.services.trip_service.BookingService", return_value=mock_svc):
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

    with patch("app.services.trip_service.BookingService", return_value=mock_svc):
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

    with patch("app.services.trip_service.BookingService", return_value=mock_svc):
        detail = svc.get_trip_detail(trip.id)

    assert all("accommodation" not in g for g in detail.gaps)


def test_gaps_empty_when_trip_has_no_dates(svc):
    """Undated trips cannot reason about days — gaps must be an empty list."""
    trip = svc.create_trip(TripCreate(title="Undated"))
    mock_svc = _mock_booking_svc({})

    with patch("app.services.trip_service.BookingService", return_value=mock_svc):
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


def test_day_plan_date_before_start_date_raises_conflict_error(svc):
    """A date before the trip's start_date raises ConflictError (409)."""
    trip = svc.create_trip(
        TripCreate(
            title="Future trip",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 5),
            items=[
                TripItemCreate(day=1, kind="place", title="Day 1 activity"),
            ],
        )
    )
    # Request a date 30 days before the trip starts — day would be -29.
    with pytest.raises(ConflictError) as exc_info:
        asyncio.run(svc.get_day_plan(trip.id, date(2026, 7, 1)))

    assert exc_info.value.status_code == 409
    assert (
        "before" in exc_info.value.detail.lower() or "start_date" in exc_info.value.hint
    )


# --------------------------------------------------------------------------- #
# get_day_plan — routing SUCCESS path (monkeypatched, offline)
# --------------------------------------------------------------------------- #


def test_day_plan_populates_travel_fields_when_routing_succeeds(svc, monkeypatch):
    """When both items have geo-located place_ids and routing returns a matching
    leg, travel_to_next_minutes and travel_to_next_mode are populated on the
    first item; the last item still has null travel fields.
    """
    from unittest.mock import AsyncMock

    from app.schemas.route import RouteEndpoint, RouteLeg, RouteResponse
    from app.services import place_service as _place_svc
    from app.services import routing_service as _routing_svc

    # Fake places with coordinates — no DB or catalog needed.
    place_a = MagicMock()
    place_a.id = "place-a"
    place_a.latitude = 16.0544
    place_a.longitude = 108.2022

    place_b = MagicMock()
    place_b.id = "place-b"
    place_b.latitude = 16.0678
    place_b.longitude = 108.2208

    # Fake route: recommended_mode "car", leg with 12.5 minutes.

    fake_leg = RouteLeg(
        mode="car", profile="driving-car", distance_km=5.0, duration_minutes=12.5
    )
    fake_origin = RouteEndpoint(
        kind="place", id="place-a", name="Museum", latitude=16.0544, longitude=108.2022
    )
    fake_dest = RouteEndpoint(
        kind="place", id="place-b", name="Market", latitude=16.0678, longitude=108.2208
    )
    fake_route = RouteResponse(
        origin=fake_origin,
        destination=fake_dest,
        straight_line_km=4.8,
        recommended_mode="car",
        legs=[fake_leg],
        source="estimate",
        attribution="test",
    )

    monkeypatch.setattr(
        _place_svc,
        "get_place",
        lambda pid: place_a if pid == "place-a" else place_b,
    )
    monkeypatch.setattr(
        _routing_svc,
        "get_place_route",
        AsyncMock(return_value=fake_route),
    )

    trip = svc.create_trip(
        TripCreate(
            title="Test",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 1),
            items=[
                TripItemCreate(
                    day=1,
                    sort_order=0,
                    kind="place",
                    title="Museum",
                    place_id="place-a",
                ),
                TripItemCreate(
                    day=1,
                    sort_order=1,
                    kind="place",
                    title="Market",
                    place_id="place-b",
                ),
            ],
        )
    )
    result = asyncio.run(svc.get_day_plan(trip.id, date(2026, 7, 1)))

    assert len(result.items) == 2
    first = result.items[0]
    assert first.travel_to_next_minutes == 12.5
    assert first.travel_to_next_mode == "car"

    last = result.items[-1]
    assert last.travel_to_next_minutes is None
    assert last.travel_to_next_mode is None


# --------------------------------------------------------------------------- #
# get_day_plan — weather_score population
# --------------------------------------------------------------------------- #


def _fake_weather_response(date_iso: str, weather_code: int = 0):
    """Build a minimal WeatherResponse with one DailyForecast for date_iso."""
    from app.schemas.weather import (
        CurrentWeather,
        DailyForecast,
        WeatherLocation,
        WeatherResponse,
    )

    location = WeatherLocation(
        name="Test City",
        latitude=0.0,
        longitude=0.0,
        timezone="UTC",
    )
    current = CurrentWeather(
        time="2026-07-01T12:00",
        temperature_c=28.0,
        apparent_temperature_c=30.0,
        relative_humidity=60,
        wind_speed_kmh=10.0,
        weather_code=weather_code,
        description="Clear sky",
    )
    daily = [
        DailyForecast(
            date=date_iso,
            temp_min_c=22.0,
            temp_max_c=32.0,
            precipitation_probability_max=5,
            weather_code=weather_code,
            description="Clear sky",
        )
    ]
    return WeatherResponse(location=location, current=current, daily=daily)


def test_day_plan_weather_score_populated_when_city_set(svc, monkeypatch):
    """When the trip has a city, weather_score is a float returned by compute_weather_score."""
    from unittest.mock import AsyncMock

    from app.services import weather_service as _weather_svc

    target = date(2026, 7, 1)
    fake_response = _fake_weather_response(target.isoformat(), weather_code=0)

    monkeypatch.setattr(
        _weather_svc, "get_weather", AsyncMock(return_value=fake_response)
    )

    trip = svc.create_trip(
        TripCreate(
            title="Test",
            city="Da Nang",
            start_date=target,
            end_date=target,
        )
    )
    result = asyncio.run(svc.get_day_plan(trip.id, target))

    expected_score = _weather_svc.compute_weather_score(fake_response.daily[0])
    assert result.weather_score is not None
    assert isinstance(result.weather_score, float)
    assert 0.0 <= result.weather_score <= 1.0
    assert result.weather_score == expected_score


def test_day_plan_weather_score_none_when_no_city(svc, monkeypatch):
    """Trip with no city → weather_score is None; get_weather is not called."""
    from unittest.mock import AsyncMock

    from app.services import weather_service as _weather_svc

    mock_get = AsyncMock()
    monkeypatch.setattr(_weather_svc, "get_weather", mock_get)

    trip = svc.create_trip(
        TripCreate(
            title="No city",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 1),
        )
    )
    result = asyncio.run(svc.get_day_plan(trip.id, date(2026, 7, 1)))

    assert result.weather_score is None
    mock_get.assert_not_called()


def test_day_plan_weather_score_none_when_date_outside_forecast(svc, monkeypatch):
    """When no DailyForecast matches target_date, weather_score is None."""
    from unittest.mock import AsyncMock

    from app.services import weather_service as _weather_svc

    # Forecast for a different date than the one we'll query.
    fake_response = _fake_weather_response("2026-08-15")
    monkeypatch.setattr(
        _weather_svc, "get_weather", AsyncMock(return_value=fake_response)
    )

    trip = svc.create_trip(
        TripCreate(
            title="Test",
            city="Da Nang",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 1),
        )
    )
    result = asyncio.run(svc.get_day_plan(trip.id, date(2026, 7, 1)))

    assert result.weather_score is None


def test_day_plan_weather_score_none_on_upstream_error(svc, monkeypatch):
    """get_weather raising an exception → weather_score is None; day plan still returns."""
    from unittest.mock import AsyncMock

    from app.services import weather_service as _weather_svc

    monkeypatch.setattr(
        _weather_svc,
        "get_weather",
        AsyncMock(side_effect=RuntimeError("network down")),
    )

    trip = svc.create_trip(
        TripCreate(
            title="Test",
            city="Da Nang",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 1),
        )
    )
    result = asyncio.run(svc.get_day_plan(trip.id, date(2026, 7, 1)))

    assert result.weather_score is None
    assert result.trip_id == trip.id  # day plan still returned normally
