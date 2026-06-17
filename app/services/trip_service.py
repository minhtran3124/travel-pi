"""Trip itinerary business logic: CRUD over trips and their items.

Service tier — owns ID generation, existence checks, and the 404s; delegates
all persistence to :class:`~app.crud.trip.TripRepository`. Trips are the
second mutable state in the API (alongside bookings). Sync + raw SQLite, like
the booking service.
"""

import logging
import uuid
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from app.core.config import get_settings
from app.crud.trip import TripRepository
from app.enums import ActivityLevel, BookingStatus, BookingType, MealStyle
from app.exceptions import ConflictError, NotFoundError
from app.schemas.trip import (
    DayPlanItem,
    DayPlanResponse,
    EstimateBreakdown,
    Trip,
    TripCreate,
    TripDetail,
    TripEstimateRequest,
    TripEstimateResponse,
    TripItem,
    TripItemCreate,
    TripItemUpdate,
    TripUpdate,
)
from app.services import place_service, routing_service
from app.services.booking_service import get_booking_service

logger = logging.getLogger(__name__)


def _new_id() -> str:
    return str(uuid.uuid4())


class TripService:
    """Business logic over the trip store."""

    def __init__(self, db_path: str) -> None:
        self._repo = TripRepository(db_path)

    def init_db(self) -> None:
        """Create the backing tables. Called once on application startup."""
        self._repo.init_db()

    def get_trip(self, trip_id: str) -> Trip:
        """Return a trip by UUID, or raise :class:`NotFoundError`."""
        trip = self._repo.get_trip(trip_id)
        if trip is None:
            raise NotFoundError(
                f"Trip {trip_id!r} not found",
                hint="Use GET /trips to list existing trips.",
            )
        return trip

    def list_trips(self) -> list[Trip]:
        """Return every trip, newest first."""
        return self._repo.list_trips()

    def create_trip(self, request: TripCreate) -> Trip:
        """Create a trip (plus any initial items) and return it."""
        trip_id = _new_id()
        items = [
            TripItem(id=_new_id(), trip_id=trip_id, **item.model_dump())
            for item in request.items
        ]
        trip = Trip(
            id=trip_id,
            title=request.title,
            city=request.city,
            start_date=request.start_date,
            end_date=request.end_date,
            travelers=request.travelers,
            notes=request.notes,
            created_at=datetime.now(timezone.utc),
            items=items,
        )
        self._repo.create_trip(trip)
        logger.info("Created trip %s with %d item(s)", trip_id, len(items))
        return self._repo.get_trip(trip_id)

    def update_trip(self, trip_id: str, request: TripUpdate) -> Trip:
        """Replace a trip's top-level fields. 404 if it does not exist."""
        existing = self.get_trip(trip_id)
        updated = existing.model_copy(
            update={
                "title": request.title,
                "city": request.city,
                "start_date": request.start_date,
                "end_date": request.end_date,
                "travelers": request.travelers,
                "notes": request.notes,
            }
        )
        self._repo.update_trip(updated)
        logger.info("Updated trip %s", trip_id)
        return self._repo.get_trip(trip_id)

    def delete_trip(self, trip_id: str) -> None:
        """Delete a trip and its items. 404 if it does not exist."""
        self.get_trip(trip_id)
        self._repo.delete_trip(trip_id)
        logger.info("Deleted trip %s", trip_id)

    def add_item(self, trip_id: str, request: TripItemCreate) -> TripItem:
        """Append an item to a trip. 404 if the trip does not exist."""
        self.get_trip(trip_id)
        item = TripItem(id=_new_id(), trip_id=trip_id, **request.model_dump())
        self._repo.add_item(item)
        logger.info("Added item %s to trip %s", item.id, trip_id)
        return item

    def update_item(
        self, trip_id: str, item_id: str, request: TripItemUpdate
    ) -> TripItem:
        """Replace an item's fields. 404 if the trip or item does not match."""
        self.get_trip(trip_id)
        existing = self._repo.get_item(item_id)
        if existing is None or existing.trip_id != trip_id:
            raise NotFoundError(
                f"Item {item_id!r} not found on trip {trip_id!r}",
                hint="Use GET /trips/{trip_id} to see its items.",
            )
        updated = TripItem(id=item_id, trip_id=trip_id, **request.model_dump())
        self._repo.update_item(updated)
        return self._repo.get_item(item_id)

    def delete_item(self, trip_id: str, item_id: str) -> None:
        """Delete an item from a trip. 404 if the trip or item does not match."""
        self.get_trip(trip_id)
        existing = self._repo.get_item(item_id)
        if existing is None or existing.trip_id != trip_id:
            raise NotFoundError(
                f"Item {item_id!r} not found on trip {trip_id!r}",
                hint="Use GET /trips/{trip_id} to see its items.",
            )
        self._repo.delete_item(item_id)
        logger.info("Deleted item %s from trip %s", item_id, trip_id)

    def get_trip_detail(self, trip_id: str) -> TripDetail:
        """Return a trip enriched with spend rollup and coverage gaps.

        ``total_spent`` sums the ``total_price`` of every non-cancelled
        booking linked by items. ``gaps`` lists days that are missing
        accommodation or have no items at all.  Both fields are computed
        fresh on each call — nothing extra is stored.
        """
        trip = self.get_trip(trip_id)
        booking_svc = get_booking_service()

        # Resolve all booking_ids once to avoid redundant DB lookups in the
        # gaps pass that follows.
        resolved: dict[str, object] = {}
        for item in trip.items:
            if item.booking_id is None or item.booking_id in resolved:
                continue
            try:
                resolved[item.booking_id] = booking_svc.get(item.booking_id)
            except NotFoundError:
                logger.info(
                    "Booking %r not found for item %s — skipping spend",
                    item.booking_id,
                    item.id,
                )
                resolved[item.booking_id] = None

        # Spend rollup: sum confirmed bookings only.
        total = 0.0
        for item in trip.items:
            if item.booking_id is None:
                continue
            booking = resolved.get(item.booking_id)
            if booking is None or booking.status == BookingStatus.CANCELLED:
                continue
            total += booking.total_price
        total_spent = _money(total)

        # Gap detection: iterate day range when dates are known.
        gaps: list[str] = []
        if trip.start_date is not None and trip.end_date is not None:
            num_days = (trip.end_date - trip.start_date).days + 1
            for day_num in range(1, num_days + 1):
                day_items = [i for i in trip.items if i.day == day_num]
                if not day_items:
                    gaps.append(f"Day {day_num} has no planned items.")
                    continue
                has_hotel = any(
                    resolved.get(i.booking_id) is not None
                    and resolved[i.booking_id].type == BookingType.HOTEL
                    and resolved[i.booking_id].status != BookingStatus.CANCELLED
                    for i in day_items
                    if i.booking_id is not None
                )
                if not has_hotel:
                    gaps.append(f"Day {day_num} has no accommodation booked.")

        return TripDetail(**trip.model_dump(), total_spent=total_spent, gaps=gaps)

    async def get_day_plan(self, trip_id: str, target_date: date) -> DayPlanResponse:
        """Return an ordered day plan with optional travel-time annotations.

        Raises :class:`ConflictError` (409) when the trip has no
        ``start_date`` — the day number cannot be computed without it.
        Travel times between consecutive items are fetched from
        ``routing_service`` when both items have resolvable, geo-located
        place IDs; any routing error is silently swallowed (fields stay
        ``None``) so a missing API key never breaks the day plan.
        """
        trip = self.get_trip(trip_id)
        if trip.start_date is None:
            raise ConflictError(
                "This trip has no start_date set.",
                hint=(
                    "This trip has no start_date; set it via PUT /trips/{trip_id}, "
                    "then retry the day-plan."
                ),
            )

        day = (target_date - trip.start_date).days + 1
        day_items = sorted(
            [i for i in trip.items if i.day == day],
            key=lambda i: i.sort_order,
        )

        plan_items: list[DayPlanItem] = []
        for idx, item in enumerate(day_items):
            travel_minutes: float | None = None
            travel_mode: str | None = None

            is_last = idx == len(day_items) - 1
            if not is_last:
                next_item = day_items[idx + 1]
                if item.place_id and next_item.place_id:
                    place_a = place_service.get_place(item.place_id)
                    place_b = place_service.get_place(next_item.place_id)
                    if (
                        place_a is not None
                        and place_a.latitude is not None
                        and place_a.longitude is not None
                        and place_b is not None
                        and place_b.latitude is not None
                        and place_b.longitude is not None
                    ):
                        try:
                            route = await routing_service.get_place_route(
                                item.place_id, next_item.place_id
                            )
                            rec_mode = route.recommended_mode
                            leg = next(
                                leg for leg in route.legs if leg.mode == rec_mode
                            )
                            travel_minutes = leg.duration_minutes
                            travel_mode = rec_mode
                        except Exception:
                            logger.warning(
                                "Routing %s → %s failed — travel fields null",
                                item.place_id,
                                next_item.place_id,
                            )

            plan_items.append(
                DayPlanItem(
                    item=item,
                    travel_to_next_minutes=travel_minutes,
                    travel_to_next_mode=travel_mode,
                )
            )

        return DayPlanResponse(
            trip_id=trip_id, date=target_date, day=day, items=plan_items
        )


# Shared singleton — constructed at import time (cheap: stores the path only).
# The tables are created later from the app's lifespan handler, so importing
# this module has no side effects.
_trip_service = TripService(get_settings().database_path)


def get_trip_service() -> TripService:
    """FastAPI dependency returning the shared trip store."""
    return _trip_service


# --------------------------------------------------------------------------- #
# Budget estimate — a stateless calculator (no DB, no network).
# Rates are USD per person per day, where "day" = one night (see SUMMARY.md /
# PLAN.md: the spec's worked example balances on `nights`, not `nights + 1`).
# --------------------------------------------------------------------------- #

_MEAL_RATES: dict[MealStyle, int] = {
    MealStyle.BUDGET: 15,
    MealStyle.MID: 30,
    MealStyle.FINE: 70,
}
_ACTIVITY_RATES: dict[ActivityLevel, int] = {
    ActivityLevel.NONE: 0,
    ActivityLevel.SOME: 20,
    ActivityLevel.LOTS: 50,
}
_LOCAL_TRANSPORT_PER_DAY = 15  # USD per day, per trip (not per traveler)
_BUFFER_PCT = 10


def _money(value: float, places: int = 2) -> float:
    """Round half-up to ``places`` decimals (avoids round()'s banker's rounding)."""
    quant = Decimal(10) ** -places
    return float(Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP))


def estimate_trip(request: TripEstimateRequest) -> TripEstimateResponse:
    """Compute a line-item budget estimate. Pure function; nothing is stored."""
    nights = request.nights
    travelers = request.travelers
    meal_rate = _MEAL_RATES[request.meal_style]
    activity_rate = _ACTIVITY_RATES[request.activity_level]

    flights = _money(request.flight_total_usd or 0.0)
    accommodation = _money((request.hotel_price_per_night_usd or 0.0) * nights)
    meals = _money(meal_rate * travelers * nights)
    activities = _money(activity_rate * travelers * nights)
    local_transport = _money(_LOCAL_TRANSPORT_PER_DAY * nights)

    breakdown = EstimateBreakdown(
        flights=flights,
        accommodation=accommodation,
        meals=meals,
        activities=activities,
        local_transport=local_transport,
    )
    subtotal = _money(flights + accommodation + meals + activities + local_transport)
    total_estimate = _money(subtotal * (1 + _BUFFER_PCT / 100), places=0)
    per_person = _money(total_estimate / travelers)

    assumptions = [
        f"Meals at '{request.meal_style.value}' = ${meal_rate}/person/day, "
        f"over {nights} night(s) for {travelers} traveler(s).",
        f"Activities at '{request.activity_level.value}' = ${activity_rate}/person/day.",
        f"Local transport = ${_LOCAL_TRANSPORT_PER_DAY}/day (per trip).",
        f"{_BUFFER_PCT}% buffer added for incidentals.",
    ]
    if request.flight_total_usd is None:
        assumptions.append(
            "Flights not provided — excluded. Pass flight_total_usd to include them."
        )
    if request.hotel_price_per_night_usd is None:
        assumptions.append(
            "Accommodation not provided — excluded. Pass hotel_price_per_night_usd "
            "to include it."
        )

    return TripEstimateResponse(
        city=request.city,
        nights=nights,
        travelers=travelers,
        breakdown=breakdown,
        subtotal=subtotal,
        buffer_pct=_BUFFER_PCT,
        total_estimate=total_estimate,
        per_person=per_person,
        assumptions=assumptions,
        notes="Estimate only — excludes visas, shopping, and tips.",
    )
