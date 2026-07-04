"""Hotel search and booking tools (specs/travel-agent Task 3.3).

Wrap ``HotelService`` and ``BookingService`` as LLM tools. Each opens its own
session via ``session_scope`` and maps domain errors to ``ToolException``.
The booking tool requires ``confirm=True`` to guard against accidental
reservations — mutable state in an agent graph needs an explicit opt-in.
``search_hotels`` (dated availability, booking flow) and ``browse_hotels``
(dateless catalog, concierge) are both panel-capable: on matches they return a
short summary plus a ``kind="hotels"`` side-panel artifact; on no match they
return a message and no panel (the mapper never sends an empty panel to the
drawer).
"""

from __future__ import annotations

from datetime import datetime, timezone

from langchain_core.tools import ToolException, tool
from pydantic import Field

from app.exceptions import AppError
from app.schemas.base import AppBaseModel
from app.schemas.hotel import HotelBookingRequest
from app.services.booking_service import BookingService
from app.services.hotel_service import HotelService
from app.streaming.panels import HotelsPanel
from app.tools._base import dump, log_tool_call, panel_result, session_scope


class SearchHotelsArgs(AppBaseModel):
    city: str = Field(
        ...,
        description="Free-text city name — fuzzy matched (e.g. 'danang' → 'Da Nang').",
    )
    check_in: str = Field(
        ...,
        description=(
            "Stay start date, YYYY-MM-DD. Must be today or later — resolve relative "
            "dates against the current date in the system prompt; never guess or "
            "pass a past date."
        ),
    )
    check_out: str = Field(
        ..., description="Stay end date, YYYY-MM-DD. Must be after `check_in`."
    )
    rooms: int = Field(
        ..., description="Number of rooms needed. Required — get it from the traveller."
    )
    adults: int = Field(
        ...,
        description="Adult party size across all rooms. Required — get it from the traveller.",
    )
    children: int = Field(
        ...,
        description="Number of children in the party (0 if none). Required — ask the traveller.",
    )
    min_stars: int | None = Field(
        None, ge=1, le=5, description="Keep only hotels with this star rating or above."
    )
    max_price: float | None = Field(
        None, description="Keep only hotels at or below this nightly rate."
    )
    amenities: list[str] | None = Field(
        None,
        description=(
            "List of required amenities — fuzzy matched, e.g. 'wifi' → 'Free WiFi' "
            "(case/typo/substring tolerant). Does not include breakfast — that's a "
            "separate `breakfast_included` field on the hotel, not an amenity tag."
        ),
    )


class BrowseHotelsArgs(AppBaseModel):
    city: str = Field(
        ...,
        description="Free-text city name — fuzzy matched (e.g. 'danang' → 'Da Nang').",
    )
    min_stars: int | None = Field(
        None, ge=1, le=5, description="Keep only hotels with this star rating or above."
    )
    max_price: float | None = Field(
        None, description="Keep only hotels at or below this nightly rate."
    )
    amenities: list[str] | None = Field(
        None,
        description=(
            "List of required amenities — fuzzy matched, e.g. 'wifi' → 'Free WiFi' "
            "(case/typo/substring tolerant). Does not include breakfast — that's a "
            "separate `breakfast_included` field on the hotel, not an amenity tag."
        ),
    )


class BookHotelArgs(AppBaseModel):
    hotel_id: str = Field(
        ...,
        description="Canonical hotel ID or short code (HTL-XXXXXX) from search_hotels.",
    )
    check_in: str = Field(..., description="Stay start date, YYYY-MM-DD.")
    check_out: str = Field(..., description="Stay end date, YYYY-MM-DD.")
    guest_name: str = Field(
        ..., description="Lead guest full name as on their ID/passport."
    )
    guest_email: str = Field(..., description="Contact email for the reservation.")
    guest_phone: str = Field(
        ..., description="Contact phone for the hotel (late arrival, changes)."
    )
    rooms: int = Field(1, description="Number of rooms to book (default 1).")
    adults: int = Field(2, description="Adult party size across all rooms.")
    children: int = Field(0, description="Child party size across all rooms.")
    notes: str | None = Field(
        None,
        description="Optional note for the hotel (arrival time, bed type preference).",
    )
    confirm: bool = Field(
        False,
        description=(
            "Must be set to True to execute the booking — prevents accidental "
            "reservations. Leaving it False (the default) will not book anything."
        ),
    )


@tool(args_schema=SearchHotelsArgs, response_format="content_and_artifact")
def search_hotels(
    city: str,
    check_in: str,
    check_out: str,
    rooms: int,
    adults: int,
    children: int,
    min_stars: int | None = None,
    max_price: float | None = None,
    amenities: list[str] | None = None,
) -> tuple[str, dict | None]:
    """Search hotels in a city with room availability for specific dates.

    Returns up to 12 hotels. On success the model sees a short summary and the
    full comparison is sent to the Hotels side panel. If no hotels match — either
    the city was not recognized or the filters/dates left nothing — returns a
    short message and no panel; tell the user none were found and never invent
    hotels. It is not an error.

    ``check_in``, ``check_out``, ``rooms``, ``adults`` and ``children`` are all
    required and have no defaults — collect every one from the traveller and never
    guess or assume them. The number of nights is derived from the two dates, so it
    is not a parameter. If any of these values only appeared earlier in the
    conversation, restate them and ask the traveller to confirm before searching.

    :param city: Free-text city name — fuzzy matched (e.g. 'danang' → 'Da Nang').
    :param check_in: Stay start date, YYYY-MM-DD. Must be today or later — resolve
        relative dates against the current date in the system prompt; never guess
        or pass a past date.
    :param check_out: Stay end date, YYYY-MM-DD. Must be after ``check_in``.
    :param rooms: Number of rooms needed. Required — get it from the traveller.
    :param adults: Adult party size across all rooms. Required — get it from the traveller.
    :param children: Number of children in the party (0 if none). Required — ask the traveller.
    :param min_stars: Keep only hotels with this star rating or above.
    :param max_price: Keep only hotels at or below this nightly rate.
    :param amenities: List of required tags, e.g. ['pool', 'wifi', 'breakfast'].
    :return: A (summary, artifact) tuple. On matches the artifact is a
        ``{"kind": "hotels", "data": ...}`` side-panel payload; on no match the
        artifact is ``None`` (no panel) and the summary explains the empty result.
    """
    log_tool_call("search_hotels", locals())
    today = datetime.now(timezone.utc).date()
    try:
        parsed_check_in = datetime.strptime(check_in, "%Y-%m-%d").date()
    except ValueError as e:
        raise ToolException(
            f"check_in {check_in!r} is not a valid YYYY-MM-DD date. "
            f"Today is {today.isoformat()}. Ask the traveller for concrete dates "
            "instead of guessing."
        ) from e
    if parsed_check_in < today:
        raise ToolException(
            f"check_in {check_in} is in the past (today is {today.isoformat()}). "
            "Do not guess or invent dates — confirm the traveller's intended dates, "
            "resolving relative terms like 'today' or 'next weekend' against today."
        )
    with session_scope() as s:
        try:
            svc = HotelService(s)
            nights, results = svc.check_availability(
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
                    return (
                        f"City '{city}' was not recognized, so no hotels could be "
                        "searched. Ask the user to confirm or correct the city — do "
                        "not invent hotels.",
                        None,
                    )
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
                return (
                    f"No hotels in {resolved} for {check_in} to {check_out}{suffix}. "
                    "Tell the user none were found and suggest relaxing the filters — "
                    "do not invent hotels.",
                    None,
                )
            cheapest = min(results, key=lambda h: h.total_price)
            top_rated = max(results, key=lambda h: h.rating)
            summary = (
                f"{len(results)} hotels in {results[0].city} for {check_in} to {check_out} "
                f"({nights} nights, {rooms} room{'s' if rooms > 1 else ''}). "
                f"Cheapest {cheapest.name} ${cheapest.total_price:.0f}; "
                f"top-rated {top_rated.name} ({top_rated.rating:.1f}★). "
                "The full comparison is in the Hotels panel."
            )
            return panel_result(
                summary,
                kind="hotels",
                data=HotelsPanel.from_hotels(
                    results[0].city, check_in, check_out, nights, rooms, results
                ),
            )
        except AppError as e:
            raise ToolException(str(e)) from e
        except ValueError as e:
            raise ToolException(str(e)) from e


@tool(args_schema=BrowseHotelsArgs, response_format="content_and_artifact")
def browse_hotels(
    city: str,
    min_stars: int | None = None,
    max_price: float | None = None,
    amenities: list[str] | None = None,
) -> tuple[str, dict | None]:
    """Answer hotel info/search questions — price, location, amenities, rating — with no dates.

    Use this to browse what's in a city (e.g. "hotels in Da Nang under $100",
    "any 4-star places with a pool?"). It does **not** check date-specific
    availability and does **not** book — for a real reservation with exact
    dates, the booking flow's ``search_hotels`` (availability) and
    ``book_hotel`` handle that.

    Returns up to 12 hotels. On success the model sees a short summary and the
    full comparison is sent to the Hotels side panel. If no hotels match —
    either the city was not recognized or the filters left nothing — returns a
    short message and no panel; tell the user none were found and never invent
    hotels. It is not an error.

    :param city: Free-text city name — fuzzy matched (e.g. 'danang' → 'Da Nang').
    :param min_stars: Keep only hotels with this star rating or above.
    :param max_price: Keep only hotels at or below this nightly rate.
    :param amenities: List of required tags, e.g. ['pool', 'wifi', 'breakfast'].
    :return: A (summary, artifact) tuple. On matches the artifact is a
        ``{"kind": "hotels", "data": ...}`` side-panel payload; on no match the
        artifact is ``None`` (no panel) and the summary explains the empty result.
    """
    log_tool_call("browse_hotels", locals())
    with session_scope() as s:
        try:
            svc = HotelService(s)
            results = svc.search_hotels(
                city, min_stars=min_stars, max_price=max_price, amenities=amenities
            )
            if not results:
                resolved = svc.resolve_city(city)
                if not resolved:
                    return (
                        f"City '{city}' was not recognized, so no hotels could be "
                        "searched. Ask the user to confirm or correct the city — do "
                        "not invent hotels.",
                        None,
                    )
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
                return (
                    f"No hotels in {resolved}{suffix}. Tell the user none were found "
                    "and suggest relaxing the filters — do not invent hotels.",
                    None,
                )
            cheapest = min(results, key=lambda h: h.price_per_night)
            top_rated = max(results, key=lambda h: h.rating)
            summary = (
                f"{len(results)} hotels in {results[0].city}. "
                f"Cheapest {cheapest.name} ${cheapest.price_per_night:.0f}/night; "
                f"top-rated {top_rated.name} ({top_rated.rating:.1f}★). "
                "The full comparison is in the Hotels panel."
            )
            return panel_result(
                summary,
                kind="hotels",
                data=HotelsPanel.from_catalog(results[0].city, results),
            )
        except AppError as e:
            raise ToolException(str(e)) from e
        except ValueError as e:
            raise ToolException(str(e)) from e


@tool(args_schema=BookHotelArgs)
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
    :param confirm: Must be True to execute the booking — prevents accidental
        reservations; left False (the default), nothing is booked.
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


# Concierge's dateless catalog browse (MIN-51) — never asks for dates/occupancy.
HOTEL_SEARCH_TOOLS = [browse_hotels]
HOTEL_BOOKING_TOOLS = [book_hotel]
# Booking's dated availability search + the actual reservation.
HOTEL_TOOLS = [search_hotels] + HOTEL_BOOKING_TOOLS
