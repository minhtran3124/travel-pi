"""Trip business logic: creation, amendment, retrieval, and expansion.

The service tier for trips — it owns the rules (resolving the destination
city, validating that referenced bookings/places exist, expanding the detail
view) and delegates persistence to :class:`~app.crud.trip.TripRepository`.
Trips are the second piece of mutable state in the API (bookings are the
first).

Booking lookups go through a :class:`BookingService` *passed in by the
router* rather than the module singleton, so the booking store a trip reads
is always the same one the ``/bookings`` endpoints use — which keeps the test
suite's isolated store working without special-casing.
"""

import logging
import uuid
from datetime import datetime, timezone

from app.core.config import get_settings
from app.core.text import best_match
from app.crud.trip import TripRepository
from app.data.cities import CITIES
from app.enums import TripStatus
from app.exceptions import NotFoundError
from app.schemas.trip import (
    Trip,
    TripCreateRequest,
    TripDetail,
    TripItem,
    TripItemDetail,
    TripUpdateRequest,
)
from app.services import place_service
from app.services.booking_service import BookingService

logger = logging.getLogger(__name__)

_DATE_FORMAT = "%Y-%m-%d"

# Resolution target, built once at import: every canonical city record.
_ALL_CITIES: list[dict] = list(CITIES)


def _new_trip_id() -> str:
    """Return a new random UUID4 trip ID."""
    return str(uuid.uuid4())


class TripService:
    """Business logic over the trip store."""

    def __init__(self, db_path: str) -> None:
        self._repo = TripRepository(db_path)

    def init_db(self) -> None:
        """Create the backing table. Called once on application startup."""
        self._repo.init_db()

    # -- resolution / validation helpers ------------------------------------

    def _resolve_city(self, name: str) -> tuple[str, str]:
        """Resolve a free-text city to ``(canonical_name, country)``, fuzzily.

        Raises :class:`NotFoundError` if nothing matches — a trip needs a real
        destination, so (unlike the search endpoints) an unknown city fails
        loudly rather than returning an empty result.
        """
        record = best_match(name, _ALL_CITIES, [lambda c: c["name"]])
        if record is None:
            raise NotFoundError(
                f"Destination city {name!r} not found",
                hint="Use GET /cities?q=<partial-name> to find a supported city.",
            )
        return record["name"], record["country"]

    def _validate_dates(self, start_date: str, end_date: str) -> None:
        """Ensure both dates are ``YYYY-MM-DD`` and end is on/after start.

        Raises ``ValueError`` (the router maps it to a 422) on a bad format or
        an end-before-start range.
        """
        try:
            start = datetime.strptime(start_date, _DATE_FORMAT)
            end = datetime.strptime(end_date, _DATE_FORMAT)
        except ValueError as exc:
            raise ValueError(
                "start_date and end_date must be valid YYYY-MM-DD dates"
            ) from exc
        if end < start:
            raise ValueError(
                f"end_date ({end_date}) must be on or after start_date ({start_date})"
            )

    def _resolve_bookings(
        self, refs: list[str], booking_service: BookingService
    ) -> list[str]:
        """Resolve booking refs (UUID or confirmation code) to canonical IDs.

        Raises :class:`NotFoundError` naming the first ref that does not
        resolve, so a trip can never reference a booking that isn't there.
        """
        resolved: list[str] = []
        for ref in refs:
            try:
                booking = booking_service.get(ref)
            except NotFoundError as exc:
                raise NotFoundError(
                    f"Cannot attach booking {ref!r} to the trip — no such booking",
                    hint="Use GET /bookings to find valid booking IDs or codes.",
                ) from exc
            resolved.append(booking.id)
        return resolved

    def _resolve_items(self, items: list[TripItem]) -> list[TripItem]:
        """Resolve each itinerary stop's place ref to a canonical place ID.

        Raises :class:`NotFoundError` naming the first place that does not
        resolve. Day/note are carried through unchanged; order is preserved.
        """
        resolved: list[TripItem] = []
        for item in items:
            place = place_service.get_place(item.place_id)
            if place is None:
                raise NotFoundError(
                    f"Itinerary place {item.place_id!r} not found",
                    hint=(
                        "Use GET /places/search?city=<city> to find a valid "
                        "place_id (or pass the short PLC-XXXX code)."
                    ),
                )
            resolved.append(TripItem(place_id=place.id, day=item.day, note=item.note))
        return resolved

    def _replay(self, idempotency_key: str | None) -> Trip | None:
        """Return a prior trip for ``idempotency_key``, if one exists."""
        if not idempotency_key:
            return None
        existing = self._repo.get_by_idempotency_key(idempotency_key)
        if existing is not None:
            logger.info(
                "Idempotency-Key %s replayed trip %s", idempotency_key, existing.id
            )
        return existing

    # -- commands / queries --------------------------------------------------

    def create(
        self,
        request: TripCreateRequest,
        *,
        booking_service: BookingService,
        idempotency_key: str | None = None,
    ) -> Trip:
        """Create a trip after validating its city, dates, and references.

        Raises :class:`NotFoundError` for an unknown city/booking/place and
        ``ValueError`` (→ 422) for a bad date range. When ``idempotency_key``
        matches an earlier request the original trip is returned unchanged.
        """
        replayed = self._replay(idempotency_key)
        if replayed is not None:
            return replayed

        city, country = self._resolve_city(request.destination_city)
        self._validate_dates(request.start_date, request.end_date)
        booking_ids = self._resolve_bookings(request.booking_ids, booking_service)
        items = self._resolve_items(request.items)

        trip = Trip(
            id=_new_trip_id(),
            name=request.name,
            destination_city=city,
            country=country,
            start_date=request.start_date,
            end_date=request.end_date,
            booking_ids=booking_ids,
            items=items,
            status=TripStatus.PLANNING,
            notes=request.notes,
            created_at=datetime.now(timezone.utc),
        )
        self._repo.add(trip, idempotency_key=idempotency_key)
        logger.info("Created trip %s to %s", trip.id, city)
        return trip

    def get(self, trip_id: str) -> Trip:
        """Return a trip by UUID *or* its ``TRP-XXXXXX`` confirmation code.

        Raises :class:`NotFoundError` if neither matches.
        """
        trip = self._repo.get(trip_id) or self._repo.get_by_confirmation_code(trip_id)
        if trip is None:
            raise NotFoundError(
                f"Trip {trip_id!r} not found",
                hint=(
                    "Accepts the trip UUID or its TRP-XXXXXX confirmation "
                    "code. Use GET /trips to list existing trips."
                ),
            )
        return trip

    def get_detail(
        self, trip_id: str, *, booking_service: BookingService
    ) -> TripDetail:
        """Return a trip with its bookings and itinerary places resolved.

        A booking that was referenced but has since disappeared is skipped
        (it can't normally happen — bookings are never hard-deleted); a place
        that no longer resolves comes back with ``place: null``.
        """
        trip = self.get(trip_id)

        bookings = []
        for booking_id in trip.booking_ids:
            try:
                bookings.append(booking_service.get(booking_id))
            except NotFoundError:
                logger.warning(
                    "Trip %s references missing booking %s", trip.id, booking_id
                )

        itinerary = [
            TripItemDetail(
                place_id=item.place_id,
                day=item.day,
                note=item.note,
                place=place_service.get_place(item.place_id),
            )
            for item in trip.items
        ]

        return TripDetail(
            id=trip.id,
            name=trip.name,
            destination_city=trip.destination_city,
            country=trip.country,
            start_date=trip.start_date,
            end_date=trip.end_date,
            booking_ids=trip.booking_ids,
            items=trip.items,
            status=trip.status,
            notes=trip.notes,
            created_at=trip.created_at,
            bookings=bookings,
            itinerary=itinerary,
        )

    def update(
        self,
        trip_id: str,
        request: TripUpdateRequest,
        *,
        booking_service: BookingService,
    ) -> Trip:
        """Apply a partial update and return the amended trip.

        Only fields present in the request are changed. The same validation
        as :meth:`create` applies to any field that *is* changed.
        """
        trip = self.get(trip_id)
        changed = request.model_fields_set

        city, country = trip.destination_city, trip.country
        if "destination_city" in changed and request.destination_city is not None:
            city, country = self._resolve_city(request.destination_city)

        start_date = request.start_date if "start_date" in changed else trip.start_date
        end_date = request.end_date if "end_date" in changed else trip.end_date
        if "start_date" in changed or "end_date" in changed:
            self._validate_dates(start_date, end_date)

        booking_ids = trip.booking_ids
        if "booking_ids" in changed and request.booking_ids is not None:
            booking_ids = self._resolve_bookings(request.booking_ids, booking_service)

        items = trip.items
        if "items" in changed and request.items is not None:
            items = self._resolve_items(request.items)

        updated = Trip(
            id=trip.id,
            name=request.name if "name" in changed else trip.name,
            destination_city=city,
            country=country,
            start_date=start_date,
            end_date=end_date,
            booking_ids=booking_ids,
            items=items,
            status=request.status if "status" in changed else trip.status,
            notes=request.notes if "notes" in changed else trip.notes,
            created_at=trip.created_at,
        )
        self._repo.update(updated)
        logger.info("Updated trip %s", trip.id)
        return updated

    def cancel(self, trip_id: str) -> Trip:
        """Soft-cancel a trip (status → cancelled) and return it. Idempotent."""
        trip = self.get(trip_id)
        if trip.status == TripStatus.CANCELLED:
            return trip
        self._repo.update_status(trip.id, TripStatus.CANCELLED.value)
        logger.info("Cancelled trip %s", trip.id)
        return self.get(trip.id)

    def query(
        self,
        *,
        q: str | None = None,
        status: str | None = None,
        destination: str | None = None,
    ) -> list[Trip]:
        """Return trips filtered by ``q``/``status``/``destination``, newest first.

        ``q`` is a case-insensitive substring matched against the trip ID,
        confirmation code, name, and destination city. ``status`` keeps only
        rows in that lifecycle state. ``destination`` is a case-insensitive
        substring on the destination city.
        """
        trips = self._repo.list_all()

        needle = (q or "").strip().lower()
        if needle:
            trips = [
                t
                for t in trips
                if needle in t.id.lower()
                or needle in t.confirmation_code.lower()
                or needle in t.name.lower()
                or needle in t.destination_city.lower()
            ]

        if status:
            trips = [t for t in trips if t.status.value == status]

        dest = (destination or "").strip().lower()
        if dest:
            trips = [t for t in trips if dest in t.destination_city.lower()]

        return trips


# Shared singleton — constructed at import time (cheap: it only stores the
# configured path). The backing table is created later, from the app's
# lifespan handler, so importing this module has no side effects.
_trip_service = TripService(get_settings().database_path)


def get_trip_service() -> TripService:
    """FastAPI dependency returning the shared trip store."""
    return _trip_service
