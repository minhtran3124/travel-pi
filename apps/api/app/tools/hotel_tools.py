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
from app.tools._base import dump, log_tool_call, session_scope


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

    If no hotels match, returns a dict
    ``{"results": [], "reason": "unknown_city" | "no_match", "message": ...}``
    instead of a list — ``unknown_city`` means the city was not recognised,
    ``no_match`` means the filters/dates left nothing. Tell the user; never
    invent hotels. It is not an error.

    :param city: Free-text city name — fuzzy matched (e.g. 'danang' → 'Da Nang').
    :param check_in: Stay start date, YYYY-MM-DD.
    :param check_out: Stay end date, YYYY-MM-DD. Must be after ``check_in``.
    :param rooms: Number of rooms needed (default 1).
    :param adults: Adult party size across all rooms (default 2).
    :param children: Child party size across all rooms (default 0).
    :param min_stars: Keep only hotels with this star rating or above.
    :param max_price: Keep only hotels at or below this nightly rate.
    :param amenities: List of required tags, e.g. ['pool', 'wifi', 'breakfast'].
    :return: Hotels annotated with available (bool), available_rooms, nights,
        and total_price.
    """
    log_tool_call("search_hotels", locals())
    with session_scope() as s:
        try:
            svc = HotelService(s)
            _nights, results = svc.check_availability(
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
            if not results:
                resolved = svc.resolve_city(city)
                if not resolved:
                    return {
                        "results": [],
                        "reason": "unknown_city",
                        "message": (
                            f"City '{city}' was not recognized, so no hotels could be "
                            "searched. Ask the user to confirm or correct the city — do "
                            "not invent hotels."
                        ),
                    }
                applied = []
                if min_stars is not None:
                    applied.append(f"min_stars={min_stars}")
                if max_price is not None:
                    applied.append(f"max_price={max_price}")
                if amenities:
                    applied.append(f"amenities={amenities}")
                suffix = (
                    f" matching your filters ({', '.join(applied)})" if applied else ""
                )
                return {
                    "results": [],
                    "reason": "no_match",
                    "message": (
                        f"No hotels in {resolved} for {check_in} to {check_out}"
                        f"{suffix}. Tell the user none were found and suggest relaxing "
                        "the filters — do not invent hotels."
                    ),
                }
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

    Raises ``ToolException`` if the hotel is not found or has no rooms available.

    :param hotel_id: Canonical hotel ID or short code (HTL-XXXXXX) from search_hotels.
    :param check_in: Stay start date, YYYY-MM-DD.
    :param check_out: Stay end date, YYYY-MM-DD.
    :param guest_name: Lead guest full name as on their ID/passport.
    :param guest_email: Contact email for the reservation.
    :param guest_phone: Contact phone for the hotel (late arrival, changes).
    :param rooms: Number of rooms to book (default 1).
    :param adults: Adult party size across all rooms.
    :param children: Child party size across all rooms.
    :param notes: Optional note for the hotel (arrival time, bed type preference).
    :param confirm: Set to True to proceed — prevents accidental bookings.
    :return: The confirmed Booking with id, confirmation_code, and total_price.
    """
    log_tool_call("book_hotel", locals())
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
