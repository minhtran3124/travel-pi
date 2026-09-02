"""Trip itinerary business logic: CRUD over trips and their items.

Service tier — owns ID generation, existence checks, and the 404s; delegates
all persistence to :class:`~app.repositories.trip.TripRepository`. Trips are the
second mutable state in the API (alongside bookings). Sync + raw SQLite, like
the booking service.
"""

import logging
import uuid
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from fastapi import Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import AuthUser, get_current_user
from app.core.config import get_settings
from app.db.engine import get_session_factory
from app.db.session import get_session
from app.enums import (
    ActivityLevel,
    BookingStatus,
    BookingType,
    BudgetCategory,
    MealStyle,
    TripItemStatus,
)
from app.exceptions import ConflictError, DomainValidationError, NotFoundError
from app.repositories.trip import TripRepository
from app.schemas.saved_place import ShortlistEntry
from app.schemas.trip import (
    BudgetCategories,
    CategoryBudget,
    DayPlanItem,
    DayPlanResponse,
    EstimateBreakdown,
    Trip,
    TripBudget,
    TripBudgetSet,
    TripCreate,
    TripDetail,
    TripEstimateRequest,
    TripEstimateResponse,
    TripItem,
    TripItemCreate,
    TripItemUpdate,
    TripUpdate,
)
from app.services import weather_service
from app.services.booking_service import BookingService
from app.services.place_service import PlaceService
from app.services.routing_service import RoutingService

logger = logging.getLogger(__name__)

_VALID_SOURCES = {"catalog", "saved"}

# Which budget category a booking's spend lands in. Activities/buffer have no
# booking source yet (activity booking is unshipped, #15).
_BOOKING_TYPE_TO_CATEGORY: dict[BookingType, BudgetCategory] = {
    BookingType.FLIGHT: BudgetCategory.FLIGHTS,
    BookingType.HOTEL: BudgetCategory.HOTELS,
}


def _new_id() -> str:
    return str(uuid.uuid4())


class TripService:
    """Business logic over the trip store."""

    def __init__(self, session: Session, user_id: str) -> None:
        """Bind the store to one owner (#118).

        The owner is a property of the service instance rather than a parameter
        on twenty methods, because every read and mutation already funnels
        through :meth:`get_trip` — scoping that one lookup scopes the whole
        surface, and no future method can forget to pass it.

        :param session: The request-scoped DB session.
        :param user_id: The caller who owns the trips this instance may touch.
        """
        self._session = session
        self._repo = TripRepository(session)
        self._user_id = user_id

    def _bookings(self) -> BookingService:
        """Return a booking store bound to this trip's request session (shared txn).

        :return: A ``BookingService`` sharing this service's session/transaction.
        """
        return BookingService(self._session)

    def get_trip(self, trip_id: str) -> Trip:
        """Return a trip by UUID, or raise :class:`NotFoundError`.

        A trip owned by someone else raises the same ``NotFoundError`` as one
        that does not exist — a distinct "forbidden" would confirm to a probe
        that a guessed id is real (#118).

        :param trip_id: The trip's UUID.
        :return: The matching trip.
        """
        trip = self._repo.get_trip(trip_id, self._user_id)
        if trip is None:
            raise NotFoundError(
                f"Trip {trip_id!r} not found",
                hint="Use GET /trips to list existing trips.",
            )
        return trip

    def list_trips(self) -> list[Trip]:
        """Return the caller's trips, newest first.

        :return: The caller's trips, newest first.
        """
        return self._repo.list_trips(self._user_id)

    def create_trip(
        self, request: TripCreate, idempotency_key: str | None = None
    ) -> Trip:
        """Create a trip (plus any initial items) and return it.

        When ``idempotency_key`` matches an earlier request, the original trip
        is returned and nothing new is stored.

        :param request: The trip creation payload (title, dates, initial items).
        :param idempotency_key: Optional key replaying an earlier create request.
        :return: The stored trip.
        """
        if idempotency_key:
            existing = self._repo.get_trip_by_idempotency_key(
                idempotency_key, self._user_id
            )
            if existing is not None:
                logger.info(
                    "Idempotency-Key %s replayed trip %s",
                    idempotency_key,
                    existing.id,
                )
                return existing

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
        stored = self._repo.create_trip(
            trip, self._user_id, idempotency_key=idempotency_key
        )
        logger.info("Created trip %s with %d item(s)", stored.id, len(items))
        return self._repo.get_trip(stored.id, self._user_id)

    def update_trip(self, trip_id: str, request: TripUpdate) -> Trip:
        """Replace a trip's top-level fields. 404 if it does not exist.

        :param trip_id: The trip's UUID.
        :param request: The new top-level field values.
        :return: The updated trip.
        """
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
        return self._repo.get_trip(trip_id, self._user_id)

    def delete_trip(self, trip_id: str) -> None:
        """Soft-delete a trip (stamp deleted_at, keep the row). 404 if missing
        or already deleted — get_trip filters tombstoned rows, so a repeat
        delete raises NotFoundError (idempotent 404 at the API).

        :param trip_id: The trip's UUID.
        """
        self.get_trip(trip_id)
        self._repo.delete_trip(trip_id, when=datetime.now(timezone.utc).isoformat())
        logger.info("Soft-deleted trip %s", trip_id)

    def add_item(
        self,
        trip_id: str,
        request: TripItemCreate,
        idempotency_key: str | None = None,
    ) -> TripItem:
        """Append an item to a trip. 404 if the trip does not exist.

        When ``idempotency_key`` matches an earlier request, the original item
        is returned and nothing new is stored.

        :param trip_id: The trip's UUID.
        :param request: The item creation payload.
        :param idempotency_key: Optional key replaying an earlier add request.
        :return: The stored trip item.
        """
        trip = self.get_trip(trip_id)
        if idempotency_key:
            existing = self._repo.get_item_by_idempotency_key(idempotency_key)
            if existing is not None:
                # Keys are globally unique; reusing one against a different
                # trip is a client error, not a silent replay of the wrong item.
                if existing.trip_id != trip_id:
                    raise ConflictError(
                        f"Idempotency-Key {idempotency_key!r} was already used "
                        f"for a different trip.",
                        hint="Use a fresh Idempotency-Key per item, or POST to the "
                        "trip the key was first used on.",
                    )
                logger.info(
                    "Idempotency-Key %s replayed item %s",
                    idempotency_key,
                    existing.id,
                )
                return existing
        # Budget guard runs after the replay check (a replay is not a new
        # charge) and before the insert.
        self._enforce_budget(trip, request)
        item = TripItem(id=_new_id(), trip_id=trip_id, **request.model_dump())
        stored = self._repo.add_item(item, idempotency_key=idempotency_key)
        logger.info("Added item %s to trip %s", stored.id, trip_id)
        return stored

    def update_item(
        self, trip_id: str, item_id: str, request: TripItemUpdate
    ) -> TripItem:
        """Replace an item's fields. 404 if the trip or item does not match.

        :param trip_id: The trip's UUID.
        :param item_id: The item's UUID.
        :param request: The new item field values.
        :return: The updated trip item.
        """
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
        """Delete an item from a trip. 404 if the trip or item does not match.

        :param trip_id: The trip's UUID.
        :param item_id: The item's UUID.
        """
        self.get_trip(trip_id)
        existing = self._repo.get_item(item_id)
        if existing is None or existing.trip_id != trip_id:
            raise NotFoundError(
                f"Item {item_id!r} not found on trip {trip_id!r}",
                hint="Use GET /trips/{trip_id} to see its items.",
            )
        self._repo.delete_item(item_id)
        logger.info("Deleted item %s from trip %s", item_id, trip_id)

    # --- shortlist (trip_place_link) ------------------------------------- #

    def add_place_to_trip(
        self, trip_id: str, place_id: str, source: str = "catalog"
    ) -> ShortlistEntry:
        """Shortlist a catalog or saved place onto a trip.

        Validates ``source`` (422) before any DB work, then checks the trip
        exists (404) and the place resolves (404). A repeat of the same
        (trip, place, source) hits the UNIQUE index → 409.

        :param trip_id: The trip's UUID.
        :param place_id: The catalog or saved place id to shortlist.
        :param source: The place source — ``'catalog'`` or ``'saved'``.
        :return: The created shortlist entry.
        """
        if source not in _VALID_SOURCES:
            raise DomainValidationError(
                f"Invalid source {source!r}.",
                hint="source must be 'catalog' or 'saved'.",
            )
        self.get_trip(trip_id)
        # Scope the saved resolve to the caller: place_id is a fresh, model-facing
        # argument (an agent can be steered to another user's saved UUID / SPL-
        # code), so an unscoped resolve here would shortlist — and echo back — a
        # foreign saved place's PII onto the caller's own trip.
        resolved = PlaceService(self._session).resolve(
            place_id, source, user_id=self._user_id
        )
        if resolved is None:
            raise NotFoundError(
                f"Place {place_id!r} not found in source {source!r}.",
                hint=(
                    "For source='catalog' use GET /places to find an id; "
                    "for source='saved' use GET /places/saved."
                ),
            )
        link_id = _new_id()
        try:
            self._repo.add_trip_place(
                link_id,
                trip_id,
                place_id,
                source,
                datetime.now(timezone.utc).isoformat(),
            )
        except IntegrityError:
            raise ConflictError(
                f"Place {place_id!r} is already shortlisted on this trip.",
                hint="It is already on the shortlist; GET /trips/{trip_id}/places.",
            ) from None
        logger.info("Shortlisted %s (%s) onto trip %s", place_id, source, trip_id)
        return ShortlistEntry(link_id=link_id, source=source, place=resolved)

    def list_trip_places(self, trip_id: str) -> list[ShortlistEntry]:
        """Return the trip's shortlist, each entry resolved. Entries whose
        place no longer resolves (e.g. a soft-deleted saved place) are dropped.

        :param trip_id: The trip's UUID.
        :return: The resolved shortlist entries.
        """
        self.get_trip(trip_id)
        entries: list[ShortlistEntry] = []
        for row in self._repo.list_trip_places(trip_id):
            resolved = PlaceService(self._session).resolve(
                row["place_id"], row["source"], user_id=self._user_id
            )
            if resolved is None:
                continue
            entries.append(
                ShortlistEntry(link_id=row["id"], source=row["source"], place=resolved)
            )
        return entries

    def remove_trip_place(self, trip_id: str, link_id: str) -> None:
        """Remove a shortlist entry. 404 if the trip or link does not match.

        :param trip_id: The trip's UUID.
        :param link_id: The shortlist link id to remove.
        """
        self.get_trip(trip_id)
        if not self._repo.delete_trip_place(trip_id, link_id):
            raise NotFoundError(
                f"Shortlist entry {link_id!r} not found on trip {trip_id!r}.",
                hint="Use GET /trips/{trip_id}/places to list link ids.",
            )
        logger.info("Removed shortlist entry %s from trip %s", link_id, trip_id)

    def _resolve_bookings(self, trip: Trip) -> dict[str, object]:
        """Resolve every distinct linked booking_id once. Missing → None.

        :param trip: The trip whose items' bookings to resolve.
        :return: A map of booking id to the resolved booking (``None`` if missing).
        """
        booking_svc = self._bookings()
        resolved: dict[str, object] = {}
        for item in trip.items:
            if item.booking_id is None or item.booking_id in resolved:
                continue
            try:
                resolved[item.booking_id] = booking_svc.get(
                    item.booking_id, user_id=self._user_id
                )
            except NotFoundError:
                logger.info(
                    "Booking %r not found for item %s — skipping spend",
                    item.booking_id,
                    item.id,
                )
                resolved[item.booking_id] = None
        return resolved

    def _spend_by_category(self, trip: Trip) -> dict[BudgetCategory, float]:
        """Sum booked spend per category. Per-item (matches total_spent).

        :param trip: The trip whose booked spend to sum.
        :return: Booked spend keyed by budget category.
        """
        resolved = self._resolve_bookings(trip)
        spend: dict[BudgetCategory, float] = dict.fromkeys(BudgetCategory, 0.0)
        for item in trip.items:
            if item.booking_id is None:
                continue
            booking = resolved.get(item.booking_id)
            if booking is None or booking.status == BookingStatus.CANCELLED:
                continue
            category = _BOOKING_TYPE_TO_CATEGORY.get(booking.type)
            if category is None:
                continue
            spend[category] += booking.total_price
        return {c: _money(v) for c, v in spend.items()}

    def get_trip_budget(self, trip_id: str) -> TripBudget:
        """Return per-category caps vs spend for a trip. 404 if unknown.

        :param trip_id: The trip's UUID.
        :return: The trip's per-category caps versus spend.
        """
        trip = self.get_trip(trip_id)
        caps = self._repo.get_budget_caps(trip_id)
        spend = self._spend_by_category(trip)
        return self._build_budget(trip_id, caps, spend)

    def set_trip_budget(self, trip_id: str, request: TripBudgetSet) -> TripBudget:
        """Replace the trip's caps and return the resulting budget. 404 if unknown.

        :param trip_id: The trip's UUID.
        :param request: The new per-category caps.
        :return: The resulting trip budget.
        """
        self.get_trip(trip_id)
        caps = {
            c.value: getattr(request, c.value)
            for c in BudgetCategory
            if getattr(request, c.value) is not None
        }
        self._repo.set_budget_caps(trip_id, caps)
        logger.info("Set budget on trip %s: %s", trip_id, caps)
        return self.get_trip_budget(trip_id)

    @staticmethod
    def _build_budget(
        trip_id: str, caps: dict[str, float], spend: dict[BudgetCategory, float]
    ) -> TripBudget:
        cat_models: dict[str, CategoryBudget] = {}
        total_cap = 0.0
        any_cap = False
        over = False
        for c in BudgetCategory:
            cap = caps.get(c.value)
            spent = spend[c]
            remaining = _money(cap - spent) if cap is not None else None
            if cap is not None:
                any_cap = True
                total_cap += cap
                if spent > cap:
                    over = True
            cat_models[c.value] = CategoryBudget(
                cap=cap, spent=spent, remaining=remaining
            )
        total_spent = _money(sum(spend.values()))
        return TripBudget(
            trip_id=trip_id,
            categories=BudgetCategories(**cat_models),
            total_cap=_money(total_cap) if any_cap else None,
            total_spent=total_spent,
            total_remaining=_money(total_cap - total_spent) if any_cap else None,
            over_budget=over,
        )

    def _enforce_budget(self, trip: Trip, request: TripItemCreate) -> None:
        """Reject (409) when a linked booking would push its category over cap.

        No-ops unless the new item links a resolvable, non-cancelled booking
        whose category has a cap set. Boundary is strict: spent == cap is OK.

        :param trip: The trip whose caps to enforce.
        :param request: The item being added, whose linked booking is checked.
        """
        if request.booking_id is None:
            return
        caps = self._repo.get_budget_caps(trip.id)
        if not caps:
            return
        try:
            booking = self._bookings().get(request.booking_id, user_id=self._user_id)
        except NotFoundError:
            return  # unpriceable link — consistent with total_spent skipping it
        if booking.status == BookingStatus.CANCELLED:
            return
        category = _BOOKING_TYPE_TO_CATEGORY.get(booking.type)
        if category is None:
            return
        cap = caps.get(category.value)
        if cap is None:
            return
        current = self._spend_by_category(trip)[category]
        projected = _money(current + booking.total_price)
        if projected > cap:
            over_by = _money(projected - cap)
            raise ConflictError(
                f"Adding this ${booking.total_price:.2f} {category.value} booking "
                f"would push {category.value} spend to ${projected:.2f}, over the "
                f"${cap:.2f} budget by ${over_by:.2f}.",
                hint=(
                    f"Raise the {category.value} cap via POST /trips/{trip.id}/budget, "
                    "or link a cheaper booking."
                ),
            )

    def get_trip_detail(self, trip_id: str) -> TripDetail:
        """Return a trip enriched with spend rollup and coverage gaps.

        ``total_spent`` sums the ``total_price`` of every non-cancelled
        booking linked by items. ``gaps`` lists days that are missing
        accommodation or have no items at all.  Both fields are computed
        fresh on each call — nothing extra is stored.

        :param trip_id: The trip's UUID.
        :return: The trip enriched with spend rollup and coverage gaps.
        """
        trip = self.get_trip(trip_id)

        # Resolve all booking_ids once to avoid redundant DB lookups in the
        # gaps pass that follows.
        resolved = self._resolve_bookings(trip)

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

        # Remaining budget rollup: total of set caps minus total_spent. Null when
        # no cap is set anywhere — mirrors TripBudget.total_remaining (#12).
        caps = self._repo.get_budget_caps(trip_id)
        remaining_budget = _money(sum(caps.values()) - total_spent) if caps else None

        # Gap detection: iterate day range when dates are known.
        gaps: list[str] = []
        if trip.start_date is not None and trip.end_date is not None:
            num_days = (trip.end_date - trip.start_date).days + 1
            for day_num in range(1, num_days + 1):
                # Optional items are "nice-to-have" — they don't count as
                # planning a day, so a day with only optional items still
                # reports the no-items gap.
                day_items = [
                    i
                    for i in trip.items
                    if i.day == day_num and i.status != TripItemStatus.OPTIONAL
                ]
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

        return TripDetail(
            **trip.model_dump(),
            total_spent=total_spent,
            remaining_budget=remaining_budget,
            gaps=gaps,
            places=self.list_trip_places(trip_id),
        )

    async def get_day_plan(self, trip_id: str, target_date: date) -> DayPlanResponse:
        """Return an ordered day plan with optional travel-time annotations.

        Raises :class:`ConflictError` (409) when the trip has no
        ``start_date`` — the day number cannot be computed without it.
        Travel times between consecutive items are fetched from
        ``routing_service`` when both items have resolvable, geo-located
        place IDs; any routing error is silently swallowed (fields stay
        ``None``) so a missing API key never breaks the day plan.

        :param trip_id: The trip's UUID.
        :param target_date: The calendar date to build the plan for.
        :return: The ordered day plan with travel-time annotations.
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
        if day < 1:
            raise ConflictError(
                f"Requested date {target_date} is before the trip's start_date"
                f" {trip.start_date}.",
                hint="Pass a date on or after the trip's start_date.",
            )
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
                    _places = PlaceService(self._session)
                    place_a = _places.get_place(item.place_id)
                    place_b = _places.get_place(next_item.place_id)
                    if (
                        place_a is not None
                        and place_a.latitude is not None
                        and place_a.longitude is not None
                        and place_b is not None
                        and place_b.latitude is not None
                        and place_b.longitude is not None
                    ):
                        try:
                            route = await RoutingService(self._session).get_place_route(
                                item.place_id, next_item.place_id
                            )
                            rec_mode = route.recommended_mode
                            leg = next(
                                (lg for lg in route.legs if lg.mode == rec_mode),
                                None,
                            )
                            if leg is not None:
                                travel_minutes = leg.duration_minutes
                                travel_mode = rec_mode
                        except Exception as exc:
                            logger.warning(
                                "day-plan routing failed for %s->%s: %s",
                                item.place_id,
                                next_item.place_id,
                                exc,
                            )

            plan_items.append(
                DayPlanItem(
                    item=item,
                    travel_to_next_minutes=travel_minutes,
                    travel_to_next_mode=travel_mode,
                )
            )

        weather_score: float | None = None
        if trip.city:
            try:
                forecast = await weather_service.get_weather(trip.city, days=16)
                iso = target_date.isoformat()
                day_fc = next((d for d in forecast.daily if d.date == iso), None)
                if day_fc is not None:
                    weather_score = weather_service.compute_weather_score(day_fc)
            except Exception as exc:
                logger.warning(
                    "day-plan weather lookup failed for %s: %s", trip.city, exc
                )

        return DayPlanResponse(
            trip_id=trip_id,
            date=target_date,
            day=day,
            items=plan_items,
            weather_score=weather_score,
        )


def init_db() -> None:
    """Create the trips tables (startup; no request context, uses the factory)."""
    TripRepository(get_session_factory(get_settings().database_url)).init_db()


def get_trip_service(
    session: Annotated[Session, Depends(get_session)],
    auth_user: Annotated[AuthUser, Depends(get_current_user)],
) -> TripService:
    """FastAPI dependency: a trip store bound to the request session AND caller.

    ``get_current_user`` is the *required* variant, so every route depending on
    this now 401s without a valid token. Before #118 these routes had no
    authentication at all and the store was unscoped, which is what made every
    trip readable by anyone.

    :param session: The request-scoped DB session.
    :param auth_user: The authenticated caller; supplies the owner filter.
    :return: A ``TripService`` bound to the request session and caller.
    """
    return TripService(session, auth_user.id)


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
    """Round half-up to ``places`` decimals (avoids round()'s banker's rounding).

    :param value: The number to round.
    :param places: The number of decimal places to round to.
    :return: The half-up rounded value.
    """
    quant = Decimal(10) ** -places
    return float(Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP))


def estimate_trip(request: TripEstimateRequest) -> TripEstimateResponse:
    """Compute a line-item budget estimate. Pure function; nothing is stored.

    :param request: The estimate inputs (nights, travelers, rates, prices).
    :return: The computed line-item budget estimate.
    """
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
