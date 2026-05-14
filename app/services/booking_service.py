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
from app.enums import BookingSort, BookingType
from app.exceptions import NotFoundError
from app.schemas.booking import Booking
from app.schemas.flight import FlightBookingRequest
from app.schemas.hotel import HotelBookingRequest
from app.services import flight_service, hotel_service

logger = logging.getLogger(__name__)

_DATE_FORMAT = "%Y-%m-%d"

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


def _count_nights(check_in: str, check_out: str) -> int:
    """Number of nights between two YYYY-MM-DD dates (minimum 1)."""
    nights = (
        datetime.strptime(check_out, _DATE_FORMAT)
        - datetime.strptime(check_in, _DATE_FORMAT)
    ).days
    return max(nights, 1)


class BookingService:
    """Business logic over the booking store."""

    def __init__(self, db_path: str) -> None:
        self._repo = BookingRepository(db_path)

    def init_db(self) -> None:
        """Create the backing table. Called once on application startup."""
        self._repo.init_db()

    def get(self, booking_id: str) -> Booking:
        """Return a booking by ID, or raise :class:`NotFoundError`."""
        booking = self._repo.get(booking_id)
        if booking is None:
            raise NotFoundError("Booking not found")
        return booking

    def list_all(self) -> list[Booking]:
        """Return every booking, newest first. Used by the dashboard ledger."""
        return self._repo.list_all()

    def query(
        self,
        *,
        q: str | None = None,
        booking_type: str | None = None,
        sort: str = BookingSort.CREATED_DESC.value,
    ) -> list[Booking]:
        """Return bookings filtered by ``q``/``booking_type`` and sorted.

        ``q`` is a case-insensitive substring matched against the booking ID,
        customer name, and customer email. ``booking_type`` keeps only
        ``"flight"`` or ``"hotel"`` rows (other values are ignored). Unknown
        ``sort`` values fall back to newest-first.
        """
        bookings = self._repo.list_all()

        needle = (q or "").strip().lower()
        if needle:
            bookings = [
                booking
                for booking in bookings
                if needle in booking.id.lower()
                or needle in booking.customer_name.lower()
                or needle in booking.customer_email.lower()
            ]

        if booking_type in (BookingType.FLIGHT.value, BookingType.HOTEL.value):
            bookings = [b for b in bookings if b.type == booking_type]

        sort_key, reverse = BOOKING_SORTS.get(
            sort, BOOKING_SORTS[BookingSort.CREATED_DESC.value]
        )
        return sorted(bookings, key=sort_key, reverse=reverse)

    def book_flight(self, request: FlightBookingRequest) -> Booking:
        """Create a flight booking. Raises :class:`NotFoundError` if unknown."""
        flight = flight_service.find_flight_by_id(request.flight_id)
        if flight is None:
            raise NotFoundError("Flight not found")

        booking = Booking(
            id=_new_booking_id(),
            type=BookingType.FLIGHT,
            reference_id=flight.id,
            customer_name=request.passenger_name,
            customer_email=request.passenger_email,
            total_price=request.total_price,
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
            },
        )
        self._repo.add(booking)
        logger.info("Created flight booking %s for flight %s", booking.id, flight.id)
        return booking

    def book_hotel(self, request: HotelBookingRequest) -> Booking:
        """Create a hotel booking. Raises :class:`NotFoundError` if unknown.

        ``total_price`` is computed server-side as
        ``price_per_night * nights``.
        """
        hotel = hotel_service.get_hotel(request.hotel_id)
        if hotel is None:
            raise NotFoundError("Hotel not found")

        nights = _count_nights(request.check_in, request.check_out)
        booking = Booking(
            id=_new_booking_id(),
            type=BookingType.HOTEL,
            reference_id=hotel.id,
            customer_name=request.guest_name,
            customer_email=request.guest_email,
            total_price=hotel.price_per_night * nights,
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
                "guests": request.guests,
                "price_per_night": hotel.price_per_night,
            },
        )
        self._repo.add(booking)
        logger.info(
            "Created hotel booking %s for hotel %s (%d night(s))",
            booking.id,
            hotel.id,
            nights,
        )
        return booking


# Shared singleton — constructed at import time (cheap: it only stores the
# configured path). The backing table is created later, from the app's
# lifespan handler, so importing this module has no side effects.
_booking_service = BookingService(get_settings().database_path)


def get_booking_service() -> BookingService:
    """FastAPI dependency returning the shared booking store."""
    return _booking_service
