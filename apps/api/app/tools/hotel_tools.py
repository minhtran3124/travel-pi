"""Hotel search and booking tools (specs/travel-agent Task 3.3).

Wrap ``HotelService`` and ``BookingService`` as LLM tools. Each opens its own
session via ``session_scope`` and maps domain errors to ``ToolException``.
The booking tool requires ``confirm=True`` to guard against accidental
reservations — mutable state in an agent graph needs an explicit opt-in.
"""

from __future__ import annotations

from langchain_core.tools import ToolException, tool

from app.exceptions import AppError
from app.schemas.hotel import HotelBookingRequest
from app.services.booking_service import BookingService
from app.services.hotel_service import HotelService
from app.tools._base import dump, session_scope


@tool
def search_hotels(
    city: str,
    check_in: str,
    check_out: str,
    rooms: int = 1,
    adults: int = 2,
    children: int = 0,
    min_stars: int | None = None,
    max_price: float | None = None,
    amenities: list[str] | None = None,
) -> list:
    """Search hotels in a city with room availability for specific dates.

    city: free-text city name — fuzzy matched (e.g. 'danang' → 'Da Nang').
    check_in / check_out: YYYY-MM-DD. check_out must be after check_in.
    rooms: number of rooms needed (default 1).
    adults / children: party size across all rooms (default 2 adults, 0 children).
    min_stars: keep only hotels with this star rating or above.
    max_price: keep only hotels at or below this nightly rate.
    amenities: list of required tags, e.g. ['pool', 'wifi', 'breakfast'].
    Returns hotels annotated with available (bool), available_rooms, nights,
    and total_price. An unrecognised city returns an empty list, not an error.
    """
    with session_scope() as s:
        try:
            _nights, results = HotelService(s).check_availability(
                city,
                check_in,
                check_out,
                rooms=rooms,
                adults=adults,
                children=children,
                min_stars=min_stars,
                max_price=max_price,
                amenities=amenities,
            )
            return dump(results)
        except AppError as e:
            raise ToolException(str(e)) from e
        except ValueError as e:
            raise ToolException(str(e)) from e


@tool
def book_hotel(
    hotel_id: str,
    check_in: str,
    check_out: str,
    guest_name: str,
    guest_email: str,
    guest_phone: str,
    rooms: int = 1,
    adults: int = 2,
    children: int = 0,
    notes: str | None = None,
    confirm: bool = False,
) -> dict:
    """Book a hotel room. You MUST pass confirm=True to create the reservation.

    hotel_id: canonical hotel ID or short code (HTL-XXXXXX) from search_hotels.
    check_in / check_out: YYYY-MM-DD stay dates.
    guest_name: lead guest full name as on their ID/passport.
    guest_email: contact email for the reservation.
    guest_phone: contact phone for the hotel (late arrival, changes).
    rooms: number of rooms to book (default 1).
    adults / children: party size across all rooms.
    notes: optional note for the hotel (arrival time, bed type preference).
    confirm: set to True to proceed — prevents accidental bookings.
    Returns the confirmed Booking with id, confirmation_code, and total_price.
    Raises ToolException if the hotel is not found or has no rooms available.
    """
    if not confirm:
        raise ToolException(
            "set confirm=true to book — this action creates a real reservation"
        )
    with session_scope() as s:
        try:
            request = HotelBookingRequest(
                hotel_id=hotel_id,
                check_in=check_in,
                check_out=check_out,
                rooms=rooms,
                adults=adults,
                children=children,
                guest_name=guest_name,
                guest_email=guest_email,
                guest_phone=guest_phone,
                notes=notes,
            )
            result = BookingService(s).book_hotel(request)
            return dump(result)
        except AppError as e:
            raise ToolException(str(e)) from e
        except ValueError as e:
            raise ToolException(str(e)) from e


HOTEL_TOOLS = [search_hotels, book_hotel]
