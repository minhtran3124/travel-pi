"""Booking business logic: creation, filtering, sorting, and retrieval.

This is the service tier — it owns the rules (pricing a hotel stay,
resolving the referenced flight/hotel, searching and sorting the ledger)
and delegates all persistence to :class:`~app.crud.booking.BookingRepository`.
Bookings are the only mutable state in the API; everything else is
in-memory / read-only.
"""

import logging
import uuid
from datetime import datetime, timezone

from app.core.config import get_settings
from app.crud.booking import BookingRepository
from app.enums import BookingSort, BookingStatus, BookingType
from app.exceptions import ConflictError, NotFoundError
from app.schemas.booking import Booking
from app.schemas.flight import FlightBookingRequest
from app.schemas.hotel import HotelBookingRequest
from app.services import flight_service, hotel_service

logger = logging.getLogger(__name__)

# Sort options for the bookings ledger: key -> (sort_key, reverse).
BOOKING_SORTS = {
    BookingSort.CREATED_DESC.value: (lambda booking: booking.created_at, True),
    BookingSort.CREATED_ASC.value: (lambda booking: booking.created_at, False),
    BookingSort.PRICE_DESC.value: (lambda booking: booking.total_price, True),
    BookingSort.PRICE_ASC.value: (lambda booking: booking.total_price, False),
}


def _new_booking_id() -> str:
    """Return a new random UUID4 booking ID."""
    return str(uuid.uuid4())


class BookingService:
    """Business logic over the booking store."""

    def __init__(self, db_path: str) -> None:
        self._repo = BookingRepository(db_path)

    def init_db(self) -> None:
        """Create the backing table. Called once on application startup."""
        self._repo.init_db()

    def get(self, booking_id: str) -> Booking:
        """Return a booking by UUID *or* confirmation code.

        Callers can use the friendly 6-char ``confirmation_code`` wherever a
        booking UUID is accepted — we try the UUID first, then fall back to a
        case-insensitive confirmation-code scan. Raises :class:`NotFoundError`
        if neither matches.
        """
        booking = self._repo.get(booking_id)
        if booking is None:
            code = booking_id.strip().upper()
            booking = next(
                (b for b in self._repo.list_all() if b.confirmation_code == code),
                None,
            )
        if booking is None:
            raise NotFoundError("Booking not found")
        return booking

    def list_all(self) -> list[Booking]:
        """Return every booking, newest first. Used by the dashboard ledger."""
        return self._repo.list_all()

    def cancel(self, booking_id: str) -> Booking:
        """Cancel a booking (by UUID or confirmation code) and return it.

        A soft state change — the row is kept, ``status`` becomes
        ``cancelled``. Idempotent: cancelling an already-cancelled booking
        just returns it unchanged. Raises :class:`NotFoundError` if no
        booking matches.
        """
        booking = self.get(booking_id)
        if booking.status == BookingStatus.CANCELLED:
            return booking
        self._repo.update_status(booking.id, BookingStatus.CANCELLED.value)
        logger.info("Cancelled booking %s", booking.id)
        return self.get(booking.id)

    def query(
        self,
        *,
        q: str | None = None,
        booking_type: str | None = None,
        sort: str = BookingSort.CREATED_DESC.value,
    ) -> list[Booking]:
        """Return bookings filtered by ``q``/``booking_type`` and sorted.

        ``q`` is a case-insensitive substring matched against the booking ID,
        confirmation code, customer name, and customer email. ``booking_type``
        keeps only ``"flight"`` or ``"hotel"`` rows (other values are
        ignored). Unknown ``sort`` values fall back to newest-first.
        """
        bookings = self._repo.list_all()

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

        sort_key, reverse = BOOKING_SORTS.get(
            sort, BOOKING_SORTS[BookingSort.CREATED_DESC.value]
        )
        return sorted(bookings, key=sort_key, reverse=reverse)

    def _replay(self, idempotency_key: str | None) -> Booking | None:
        """Return a prior booking for ``idempotency_key``, if one exists.

        This is what makes booking POSTs replay-safe: an agent that retries
        after a timeout (or re-runs a plan) sends the same key and gets the
        original booking back instead of creating a duplicate.
        """
        if not idempotency_key:
            return None
        existing = self._repo.get_by_idempotency_key(idempotency_key)
        if existing is not None:
            logger.info(
                "Idempotency-Key %s replayed booking %s",
                idempotency_key,
                existing.id,
            )
        return existing

    def book_flight(
        self, request: FlightBookingRequest, idempotency_key: str | None = None
    ) -> Booking:
        """Create a flight booking. Raises :class:`NotFoundError` if unknown.

        When ``idempotency_key`` matches an earlier request, the original
        booking is returned and nothing new is stored.
        """
        replayed = self._replay(idempotency_key)
        if replayed is not None:
            return replayed

        flight = flight_service.find_flight_by_number(
            request.flight_number,
            request.origin.upper(),
            request.destination.upper(),
            request.departure_date,
        )
        if flight is None:
            raise NotFoundError(
                f"No flight {request.flight_number!r} on "
                f"{request.origin.upper()}→{request.destination.upper()} "
                f"on {request.departure_date}"
            )

        booking = Booking(
            id=_new_booking_id(),
            type=BookingType.FLIGHT,
            reference_id=flight.id,
            customer_name=request.passenger_name,
            customer_email=request.passenger_email,
            total_price=flight.price,
            currency=flight.currency,
            created_at=datetime.now(timezone.utc),
            notes=request.notes,
            details={
                "flight_id": flight.id,
                "flight_number": flight.flight_number,
                "airline": flight.airline.name,
                "origin": flight.origin,
                "destination": flight.destination,
                "departure_time": flight.departure_time.isoformat(),
                "arrival_time": flight.arrival_time.isoformat(),
                "passenger_name": request.passenger_name,
                "passenger_phone": request.passenger_phone,
            },
        )
        self._repo.add(booking, idempotency_key=idempotency_key)
        logger.info("Created flight booking %s for flight %s", booking.id, flight.id)
        return booking

    def book_hotel(
        self, request: HotelBookingRequest, idempotency_key: str | None = None
    ) -> Booking:
        """Create a hotel booking.

        Raises :class:`NotFoundError` if the hotel is unknown, and
        :class:`ConflictError` (409) if the hotel cannot take the requested
        rooms/party for those dates. ``total_price`` is computed server-side
        as ``price_per_night × nights × rooms``. When ``idempotency_key``
        matches an earlier request, the original booking is returned
        unchanged.
        """
        replayed = self._replay(idempotency_key)
        if replayed is not None:
            return replayed

        hotel = hotel_service.get_hotel(request.hotel_id)
        if hotel is None:
            raise NotFoundError("Hotel not found")

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
                f"({free} room(s) available)."
            )

        nights = hotel_service.count_nights(request.check_in, request.check_out)
        booking = Booking(
            id=_new_booking_id(),
            type=BookingType.HOTEL,
            reference_id=hotel.id,
            customer_name=request.guest_name,
            customer_email=request.guest_email,
            total_price=hotel.price_per_night * nights * request.rooms,
            currency=hotel.currency,
            created_at=datetime.now(timezone.utc),
            notes=request.notes,
            details={
                "hotel_id": hotel.id,
                "hotel_name": hotel.name,
                "city": hotel.city,
                "check_in": request.check_in,
                "check_out": request.check_out,
                "nights": nights,
                "rooms": request.rooms,
                "adults": request.adults,
                "children": request.children,
                "price_per_night": hotel.price_per_night,
                "guest_phone": request.guest_phone,
            },
        )
        self._repo.add(booking, idempotency_key=idempotency_key)
        logger.info(
            "Created hotel booking %s for hotel %s (%d night(s), %d room(s))",
            booking.id,
            hotel.id,
            nights,
            request.rooms,
        )
        return booking


# Shared singleton — constructed at import time (cheap: it only stores the
# configured path). The backing table is created later, from the app's
# lifespan handler, so importing this module has no side effects.
_booking_service = BookingService(get_settings().database_path)


def get_booking_service() -> BookingService:
    """FastAPI dependency returning the shared booking store."""
    return _booking_service
