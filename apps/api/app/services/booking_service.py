"""Booking business logic: creation, filtering, sorting, and retrieval.

This is the service tier — it owns the rules (pricing a hotel stay,
resolving the referenced flight/hotel, searching and sorting the ledger)
and delegates all persistence to :class:`~app.repositories.booking.BookingRepository`.
Bookings are the only mutable state in the API; everything else is
in-memory / read-only.
"""

import logging
import uuid
from datetime import date, datetime, timezone
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.engine import get_session_factory
from app.db.session import get_session
from app.enums import BookingSort, BookingStatus, BookingType
from app.exceptions import ConflictError, DuplicateBookingError, NotFoundError
from app.repositories.booking import BookingRepository
from app.repositories.trip import TripRepository
from app.schemas.booking import (
    Booking,
    FlightBookingDetails,
    HotelBookingDetails,
    confirmation_code_for,
)
from app.schemas.flight import FlightBookingRequest
from app.schemas.hotel import HotelBookingRequest
from app.services import hotel_service
from app.services.flight_service import FlightService
from app.services.hotel_service import HotelService

logger = logging.getLogger(__name__)

# Sort options for the bookings ledger: key -> (sort_key, reverse).
BOOKING_SORTS = {
    BookingSort.CREATED_DESC.value: (lambda booking: booking.created_at, True),
    BookingSort.CREATED_ASC.value: (lambda booking: booking.created_at, False),
    BookingSort.PRICE_DESC.value: (lambda booking: booking.total_price, True),
    BookingSort.PRICE_ASC.value: (lambda booking: booking.total_price, False),
}


def _as_date(value: str) -> date:
    """Parse a ``YYYY-MM-DD`` date string to a :class:`date` for comparison.

    The hotel duplicate check compares stored vs requested dates as *dates*, not
    raw strings, so unpadded input like ``"2027-4-10"`` (which the schema
    validator accepts unchanged) still matches the padded ``"2027-04-10"`` of an
    existing booking instead of escaping the check (gh-194).

    :param value: A date string in ``YYYY-MM-DD`` form.
    :return: The parsed calendar date.
    """
    return datetime.strptime(value, "%Y-%m-%d").date()


def _new_booking_id() -> str:
    """Return a new random UUID4 booking ID.

    :return: A new UUID4 string.
    """
    return str(uuid.uuid4())


def _filter_and_sort(
    bookings: list[Booking],
    *,
    q: str | None,
    booking_type: str | None,
    trip_id: str | None,
    sort: str,
) -> list[Booking]:
    """Filter a booking list by ``q``/``booking_type``/``trip_id`` and sort it.

    Shared by the owner-scoped :meth:`BookingService.query` and the dashboard's
    :meth:`BookingService.query_unscoped`, which differ only in which rows they
    fetch. ``q`` is a case-insensitive substring over id/confirmation
    code/customer name/email; ``booking_type`` keeps only ``"flight"`` or
    ``"hotel"``; ``trip_id`` keeps only bookings linked to that trip; unknown
    ``sort`` falls back to newest-first.

    :param bookings: The bookings to filter and sort.
    :param q: Case-insensitive substring filter, or ``None``.
    :param booking_type: Keep only this type, or ``None`` for all.
    :param trip_id: Keep only bookings linked to this trip, or ``None`` for all.
    :param sort: Sort key; unknown values fall back to newest-first.
    :return: The filtered, sorted bookings.
    """
    needle = (q or "").strip().lower()
    if needle:
        bookings = [
            booking
            for booking in bookings
            if needle in booking.id.lower()
            or needle in booking.confirmation_code.lower()
            or needle in booking.customer_name.lower()
            or needle in booking.customer_email.lower()
        ]

    if booking_type in (BookingType.FLIGHT.value, BookingType.HOTEL.value):
        bookings = [b for b in bookings if b.type == booking_type]

    # Filtered in Python because it mirrors q and type, not because the
    # scale demands it.
    if trip_id is not None:
        bookings = [b for b in bookings if b.trip_id == trip_id]

    sort_key, reverse = BOOKING_SORTS.get(
        sort, BOOKING_SORTS[BookingSort.CREATED_DESC.value]
    )
    return sorted(bookings, key=sort_key, reverse=reverse)


# Bound on confirmation-code collision retries when minting a booking ID. The
# code is a 6-char hash over a 31-char alphabet (31**6 ≈ 887M), so a collision
# is astronomically rare; the loop just guards the unique
# ``ix_bookings_confirmation_code`` index so a collision regenerates the UUID
# instead of failing the insert.
_MAX_ID_ATTEMPTS = 8

# Shared recovery hint for a possible-duplicate booking (gh-194). The agent
# relays it verbatim: ask the traveller, then only retry with the override.
_DUPLICATE_HINT = (
    "This looks like a duplicate of an existing booking. Do NOT rebook "
    "silently — tell the traveller about the existing booking and ask whether "
    "they really want another one. Only call again with allow_duplicate=true "
    "if they explicitly confirm."
)


class BookingService:
    """Business logic over the booking store."""

    def __init__(self, session: Session) -> None:
        self._repo = BookingRepository(session)
        self._session = session

    def _mint_booking_id(self) -> str:
        """Return a fresh UUID whose derived confirmation_code is unused.

        ``confirmation_code`` is unique (``ix_bookings_confirmation_code``) and
        derived deterministically from the ID, so on the rare hash collision we
        regenerate the UUID rather than let the insert fail. The collision check
        is deliberately unscoped: the UNIQUE index spans all owners, so an
        owner-scoped check would miss a cross-user collision.

        :return: A UUID string whose derived ``confirmation_code`` is unused.
        """
        for _ in range(_MAX_ID_ATTEMPTS):
            booking_id = _new_booking_id()
            code = confirmation_code_for(booking_id)
            if not self._repo.confirmation_code_exists(code):
                return booking_id
        raise RuntimeError(
            "Could not mint a collision-free booking confirmation_code "
            f"after {_MAX_ID_ATTEMPTS} attempts"
        )

    def ping(self) -> bool:
        """Return True if the booking store is reachable. Used by /readyz.

        :return: ``True`` if the booking store is reachable.
        """
        return self._repo.ping()

    def get(self, booking_id: str, *, user_id: str) -> Booking:
        """Return the caller's booking by UUID *or* confirmation code.

        Callers can use the friendly 6-char ``confirmation_code`` wherever a
        booking UUID is accepted — we try the UUID first, then look up the
        code via the ``ix_bookings_confirmation_code`` index. Both paths are
        O(log n); no full-table scan. A booking owned by someone else raises
        the same :class:`NotFoundError` as one that does not exist (#118).

        :param booking_id: A booking UUID or 6-char confirmation code.
        :param user_id: The caller who must own the booking.
        :return: The matching booking.
        """
        booking = self._repo.get(booking_id, user_id) or (
            self._repo.get_by_confirmation_code(booking_id, user_id)
        )
        if booking is None:
            raise NotFoundError(
                f"Booking {booking_id!r} not found",
                hint=(
                    "Accepts either the booking UUID or the 6-character "
                    "confirmation_code (e.g. 'AB23XY'). Use GET /bookings to "
                    "list existing bookings."
                ),
            )
        return booking

    def list_all(self, *, user_id: str) -> list[Booking]:
        """Return the caller's bookings, newest first.

        :param user_id: The owner whose bookings to return.
        :return: The caller's bookings, newest first.
        """
        return self._repo.list_all(user_id)

    def list_all_unscoped(self) -> list[Booking]:
        """Return every booking, newest first — operator dashboard only.

        The dashboard ledger has no signed-in caller (it is Basic-auth
        operator access) and shows all bookings across users. No user-facing
        route may call this.

        :return: Every booking, newest first.
        """
        return self._repo.list_all_unscoped()

    def cancel(self, booking_id: str, *, user_id: str) -> Booking:
        """Cancel the caller's booking (by UUID or confirmation code).

        A soft state change — the row is kept, ``status`` becomes
        ``cancelled``. Idempotent: cancelling an already-cancelled booking
        just returns it unchanged. Raises :class:`NotFoundError` if no
        booking matches the caller (#118).

        Cancelling releases the booking's idempotency key, so a cancelled
        booking is never a replay target: re-booking with the same key/turn
        creates a fresh row rather than replaying the cancelled one (gh-193).

        :param booking_id: A booking UUID or confirmation code.
        :param user_id: The caller who must own the booking.
        :return: The cancelled booking.
        """
        booking = self.get(booking_id, user_id=user_id)
        if booking.status == BookingStatus.CANCELLED:
            return booking
        self._repo.update_status(
            booking.id,
            user_id,
            BookingStatus.CANCELLED.value,
            release_idempotency_key=True,
        )
        logger.info("Cancelled booking %s", booking.id)
        return self.get(booking.id, user_id=user_id)

    def query(
        self,
        *,
        user_id: str,
        q: str | None = None,
        booking_type: str | None = None,
        trip_id: str | None = None,
        sort: str = BookingSort.CREATED_DESC.value,
    ) -> list[Booking]:
        """Return the caller's bookings filtered by ``q``/``booking_type``/``trip_id`` and sorted.

        ``q`` is a case-insensitive substring matched against the booking ID,
        confirmation code, customer name, and customer email. ``booking_type``
        keeps only ``"flight"`` or ``"hotel"`` rows (other values are
        ignored). ``trip_id`` keeps only bookings linked to that trip. Unknown
        ``sort`` values fall back to newest-first.

        :param user_id: The owner whose bookings to search.
        :param q: Case-insensitive substring filter over the booking ID,
            confirmation code, customer name, and customer email.
        :param booking_type: Keep only ``"flight"`` or ``"hotel"`` rows; other
            values are ignored.
        :param trip_id: Keep only bookings linked to this trip, or ``None``
            for all.
        :param sort: Sort key; unknown values fall back to newest-first.
        :return: The filtered, sorted bookings.
        """
        return _filter_and_sort(
            self._repo.list_all(user_id),
            q=q,
            booking_type=booking_type,
            trip_id=trip_id,
            sort=sort,
        )

    def query_unscoped(
        self,
        *,
        q: str | None = None,
        booking_type: str | None = None,
        trip_id: str | None = None,
        sort: str = BookingSort.CREATED_DESC.value,
    ) -> list[Booking]:
        """Filter and sort every booking (all owners) — operator dashboard only.

        Same filter/sort semantics as :meth:`query` but over the unscoped
        ledger. No user-facing route may call this.

        :param q: Case-insensitive substring filter (see :meth:`query`).
        :param booking_type: Keep only ``"flight"`` or ``"hotel"`` rows.
        :param trip_id: Keep only bookings linked to this trip, or ``None``
            for all.
        :param sort: Sort key; unknown values fall back to newest-first.
        :return: The filtered, sorted bookings across all owners.
        """
        return _filter_and_sort(
            self._repo.list_all_unscoped(),
            q=q,
            booking_type=booking_type,
            trip_id=trip_id,
            sort=sort,
        )

    def _replay(self, idempotency_key: str | None, user_id: str) -> Booking | None:
        """Return a prior booking for ``idempotency_key`` owned by the caller.

        This is what makes booking POSTs replay-safe: an agent that retries
        after a timeout (or re-runs a plan) sends the same key and gets the
        original booking back instead of creating a duplicate. Scoped to the
        owner so a key collision across users never replays another user's
        booking (#118).

        :param idempotency_key: The client-supplied idempotency key, if any.
        :param user_id: The caller who must own the replayed booking.
        :return: The prior booking for the key, or ``None`` if none exists.
        """
        if not idempotency_key:
            return None
        existing = self._repo.get_by_idempotency_key(idempotency_key, user_id)
        if existing is not None:
            logger.info(
                "Idempotency-Key %s replayed booking %s",
                idempotency_key,
                existing.id,
            )
        return existing

    def _verify_trip_ownership(self, trip_id: str | None, user_id: str) -> None:
        """Raise :class:`NotFoundError` if ``trip_id`` is set but not the caller's.

        Mirrors the ``_validate_trip`` check in ``expense_service.py``: both a
        missing and a foreign trip answer the same ``NotFoundError`` so this
        route can't become an oracle for whether a guessed trip id exists
        (#118). ``None`` (no trip requested) is a no-op.

        :param trip_id: The trip id to attach the booking to, or ``None``.
        :param user_id: The caller who must own the trip.
        """
        if trip_id is None:
            return
        trip = TripRepository(self._session).get_trip(trip_id, user_id)
        if trip is None:
            raise NotFoundError(
                f"Trip {trip_id!r} not found",
                hint="Use GET /trips to list existing trips.",
            )

    def book_flight(
        self,
        request: FlightBookingRequest,
        *,
        user_id: str,
        idempotency_key: str | None = None,
        check_duplicate: bool = False,
    ) -> Booking:
        """Create a flight booking for the caller. 404 if the flight is unknown.

        When ``idempotency_key`` matches an earlier request by the same owner,
        the original booking is returned and nothing new is stored.

        When ``check_duplicate`` is True (the opt-in the agent book tools pass;
        the REST route keeps the default False), a prior *active* booking by the
        same owner for the same flight row with the same ``passengers`` raises
        :class:`~app.exceptions.DuplicateBookingError` instead of silently
        creating a second identical booking (gh-194). The check runs after
        idempotency replay — so a same-turn revise re-run still replays the
        original rather than tripping the check against itself — and after the
        flight is resolved. On Postgres the check and the insert are
        serialized per owner by a transaction-scoped advisory lock, so two
        concurrent requests cannot both pass the check and both insert (gh-198).

        :param request: The flight booking request.
        :param user_id: The owner stamped on the booking (#118).
        :param idempotency_key: Optional key that replays an earlier booking
            instead of creating a duplicate.
        :param check_duplicate: When True, raise
            :class:`~app.exceptions.DuplicateBookingError` if the same owner
            already has an active booking for this flight + passenger count.
        :return: The created (or replayed) booking.
        """
        replayed = self._replay(idempotency_key, user_id)
        if replayed is not None:
            return replayed

        self._verify_trip_ownership(request.trip_id, user_id)

        if request.flight_id:
            flight = FlightService(self._session).find_flight_by_id(request.flight_id)
            if flight is None:
                raise NotFoundError(
                    f"Flight {request.flight_id!r} not found",
                    hint=(
                        "Use the `id` from a GET /flights/search result. If the "
                        "id was issued earlier and no longer resolves, re-run "
                        "the search to get a fresh one."
                    ),
                )
        else:
            flight = FlightService(self._session).find_flight_by_number(
                request.flight_number,
                request.origin.upper(),
                request.destination.upper(),
                request.departure_date,
            )
            if flight is None:
                raise NotFoundError(
                    f"No flight {request.flight_number!r} on "
                    f"{request.origin.upper()}→{request.destination.upper()} "
                    f"on {request.departure_date}",
                    hint=(
                        "Run GET /flights/search with the same origin, "
                        "destination, and departure_date to see the available "
                        "flight_numbers for that route and date."
                    ),
                )

        if check_duplicate:
            self._repo.lock_owner_bookings(user_id)
            # Re-run the replay under the lock: a concurrent same-key request may
            # have committed the winner's row while we waited, and the idempotency
            # contract owes that caller the original booking, not a
            # DuplicateBookingError. Postgres READ COMMITTED sees it now (gh-198
            # CR-1); the pre-lock replay above still short-circuits plain replays.
            replayed = self._replay(idempotency_key, user_id)
            if replayed is not None:
                return replayed
            for existing in self._repo.list_active_by_reference(
                user_id, BookingType.FLIGHT.value, flight.id
            ):
                if existing.details.passengers == request.passengers:
                    raise DuplicateBookingError(
                        f"You already have booking {existing.confirmation_code} "
                        f"for flight {flight.flight_number} on "
                        f"{flight.departure_time.date().isoformat()} for "
                        f"{request.passengers} passenger(s).",
                        existing=existing,
                        hint=_DUPLICATE_HINT,
                    )

        booking = Booking(
            id=self._mint_booking_id(),
            type=BookingType.FLIGHT,
            reference_id=flight.id,
            customer_name=request.passenger_name,
            customer_email=request.passenger_email,
            total_price=flight.price * request.passengers,
            currency=flight.currency,
            created_at=datetime.now(timezone.utc),
            notes=request.notes,
            details=FlightBookingDetails(
                flight_id=flight.id,
                flight_number=flight.flight_number,
                airline=flight.airline.name,
                origin=flight.origin,
                destination=flight.destination,
                departure_time=flight.departure_time.isoformat(),
                arrival_time=flight.arrival_time.isoformat(),
                passengers=request.passengers,
                passenger_name=request.passenger_name,
                passenger_phone=request.passenger_phone,
            ),
            trip_id=request.trip_id,
        )
        self._repo.add(booking, user_id, idempotency_key=idempotency_key)
        logger.info("Created flight booking %s for flight %s", booking.id, flight.id)
        return booking

    def book_hotel(
        self,
        request: HotelBookingRequest,
        *,
        user_id: str,
        idempotency_key: str | None = None,
        check_duplicate: bool = False,
    ) -> Booking:
        """Create a hotel booking for the caller.

        Raises :class:`NotFoundError` if the hotel is unknown, and
        :class:`ConflictError` (409) if the hotel cannot take the requested
        rooms/party for those dates. ``total_price`` is computed server-side
        as ``price_per_night × nights × rooms``. When ``idempotency_key``
        matches an earlier request by the same owner, the original booking is
        returned unchanged.

        When ``check_duplicate`` is True (the opt-in the agent book tools pass;
        the REST route keeps the default False), a prior *active* booking by the
        same owner for the same hotel with the exact same ``check_in`` and
        ``check_out`` raises :class:`~app.exceptions.DuplicateBookingError`
        instead of silently creating a second identical booking (gh-194). The
        check runs after idempotency replay and after the hotel is resolved, and
        after the availability check (a sold-out hotel reports sold-out first,
        gh-200). On Postgres the check and the insert are
        serialized per owner by a transaction-scoped advisory lock, so two
        concurrent requests cannot both pass the check and both insert (gh-198).

        :param request: The hotel booking request.
        :param user_id: The owner stamped on the booking (#118).
        :param idempotency_key: Optional key that replays an earlier booking
            instead of creating a duplicate.
        :param check_duplicate: When True, raise
            :class:`~app.exceptions.DuplicateBookingError` if the same owner
            already has an active booking for this hotel + exact dates.
        :return: The created (or replayed) booking.
        """
        replayed = self._replay(idempotency_key, user_id)
        if replayed is not None:
            return replayed

        self._verify_trip_ownership(request.trip_id, user_id)

        hotel = HotelService(self._session).get_hotel(request.hotel_id)
        if hotel is None:
            raise NotFoundError(
                f"Hotel {request.hotel_id!r} not found",
                hint=(
                    "Use GET /hotels/search?city=<city> or "
                    "GET /hotels/availability to discover a valid hotel_id "
                    "(or the short HTL-XXXX code)."
                ),
            )

        guests = request.adults + request.children
        if not hotel_service.is_available(
            hotel,
            request.check_in,
            request.check_out,
            rooms=request.rooms,
            guests=guests,
        ):
            free = hotel_service.available_rooms(
                hotel, request.check_in, request.check_out
            )
            raise ConflictError(
                f"{hotel.name} cannot take {request.rooms} room(s) for "
                f"{guests} guest(s) on those dates "
                f"({free} room(s) available).",
                hint=(
                    "Try different check_in/check_out dates, reduce rooms "
                    "or party size, or pick another hotel via "
                    "GET /hotels/availability (filter with available_only=true)."
                ),
            )

        if check_duplicate:
            self._repo.lock_owner_bookings(user_id)
            # Re-run the replay under the lock: a concurrent same-key request may
            # have committed the winner's row while we waited, and the idempotency
            # contract owes that caller the original booking, not a
            # DuplicateBookingError. Postgres READ COMMITTED sees it now (gh-198
            # CR-1); the pre-lock replay above still short-circuits plain replays.
            replayed = self._replay(idempotency_key, user_id)
            if replayed is not None:
                return replayed
            req_check_in = _as_date(request.check_in)
            req_check_out = _as_date(request.check_out)
            for existing in self._repo.list_active_by_reference(
                user_id, BookingType.HOTEL.value, hotel.id
            ):
                if (
                    _as_date(existing.details.check_in) == req_check_in
                    and _as_date(existing.details.check_out) == req_check_out
                ):
                    raise DuplicateBookingError(
                        f"You already have booking {existing.confirmation_code} "
                        f"for {existing.details.hotel_name} on "
                        f"{existing.details.check_in}→{existing.details.check_out} "
                        f"({existing.details.rooms} room(s), "
                        f"{existing.details.adults} adult(s), "
                        f"{existing.details.children} child(ren)).",
                        existing=existing,
                        hint=_DUPLICATE_HINT,
                    )

        nights = hotel_service.count_nights(request.check_in, request.check_out)
        booking = Booking(
            id=self._mint_booking_id(),
            type=BookingType.HOTEL,
            reference_id=hotel.id,
            customer_name=request.guest_name,
            customer_email=request.guest_email,
            total_price=hotel.price_per_night * nights * request.rooms,
            currency=hotel.currency,
            created_at=datetime.now(timezone.utc),
            notes=request.notes,
            details=HotelBookingDetails(
                hotel_id=hotel.id,
                hotel_name=hotel.name,
                city=hotel.city,
                check_in=request.check_in,
                check_out=request.check_out,
                nights=nights,
                rooms=request.rooms,
                adults=request.adults,
                children=request.children,
                price_per_night=hotel.price_per_night,
                guest_phone=request.guest_phone,
            ),
            trip_id=request.trip_id,
        )
        self._repo.add(booking, user_id, idempotency_key=idempotency_key)
        logger.info(
            "Created hotel booking %s for hotel %s (%d night(s), %d room(s))",
            booking.id,
            hotel.id,
            nights,
            request.rooms,
        )
        return booking


def init_db() -> None:
    """Create the bookings table (startup; no request context, uses the factory)."""
    BookingRepository(get_session_factory(get_settings().database_url)).init_db()


def get_booking_service(
    session: Annotated[Session, Depends(get_session)],
) -> BookingService:
    """FastAPI dependency: a booking store bound to the request session.

    :param session: The request-scoped SQLAlchemy session.
    :return: A :class:`BookingService` bound to ``session``.
    """
    return BookingService(session)
