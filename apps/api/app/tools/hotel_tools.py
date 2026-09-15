"""Hotel search and booking tools (specs/travel-agent Task 3.3).

Wrap ``HotelService`` and ``BookingService`` as LLM tools. Each opens its own
session via ``session_scope`` and maps domain errors to ``ToolException``.
The booking tool requires ``confirm=True`` to guard against accidental
reservations — mutable state in an agent graph needs an explicit opt-in.
``search_hotels`` (dated availability) and ``browse_hotels`` (dateless catalog)
are both panel-capable: on matches they return a
short summary plus a ``kind="hotels"`` side-panel artifact; on no match they
return a message and no panel (the mapper never sends an empty panel to the
drawer).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import ToolException, tool
from langgraph.prebuilt import InjectedState
from pydantic import Field

from app.core.config import get_settings
from app.core.dates import resolve_travel_date, today_in_timezone
from app.core.text import fold_diacritics
from app.exceptions import AppError, DuplicateBookingError
from app.schemas.base import AppBaseModel
from app.schemas.hotel import HotelBookingRequest
from app.services.booking_service import BookingService
from app.services.content_translation_service import ContentTranslationService
from app.services.hotel_service import HotelService
from app.streaming.panels import HotelsPanel
from app.tools._base import dump, log_tool_call, panel_result, session_scope, tool_error
from app.tools._idempotency import (
    OVERRIDE_REFUSED_HINT,
    duplicate_override_refused,
    duplicate_warned_ids_this_turn,
    turn_idempotency_key,
)
from app.tools._ranking import rank_by_preference


def _hotel_keyword_features(hotel) -> list[tuple[list[str], str]]:
    """Preference-matchable features for one hotel search result (DESIGN.md D7).

    Star rating and property type are matched by exact keyword; the beach/area
    check only fires when the hotel's own address/description actually mentions
    a beach — a keyword heuristic, not semantic understanding of "beachfront",
    so paraphrases can be missed (v1 trade-off, boost-only so it never hides a
    hotel that doesn't match).
    """
    stars = hotel.star_rating
    features: list[tuple[list[str], str]] = [
        ([f"{stars} sao", f"{stars}-star", f"{stars} star"], f"{stars}-star"),
        ([hotel.property_type], hotel.property_type),
    ]
    own_text = fold_diacritics(f"{hotel.description} {hotel.address}".lower())
    if "beach" in own_text or "bien" in own_text:
        features.append(
            (["beach", "beachfront", "biển", "gần biển", "bờ biển"], "beachfront")
        )
    return features


class SearchHotelsArgs(AppBaseModel):
    city: str = Field(
        ...,
        description="Free-text city name — fuzzy matched (e.g. 'danang' → 'Da Nang').",
    )
    check_in: str = Field(
        ...,
        description=(
            "Stay start date, YYYY-MM-DD. Must be today or later. For any non-ISO "
            "wording, call the resolve_date tool on the traveller's original "
            "expression first — never compute or guess a date yourself. If the "
            "traveller gave no dates at all, do NOT call this tool: never use "
            "today's date; ask them (or use browse_hotels where available)."
        ),
    )
    check_out: str = Field(
        ...,
        description=(
            "Stay end date, YYYY-MM-DD. Must be after `check_in`. For any non-ISO "
            "wording, call the resolve_date tool on the traveller's original "
            "expression first — never compute or guess a date yourself."
        ),
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
    preferences: Annotated[str, InjectedState("preferences")] = Field(
        default="",
        description="Injected — never supplied by the model.",
    )
    # Injected conversation language (TravelAgentState.language); hotel
    # descriptions are localized to it at tool time (specs/catalog-content-i18n).
    language: Annotated[str, InjectedState("language")] = Field(
        default="",
        description="Injected — never supplied by the model.",
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
    preferences: Annotated[str, InjectedState("preferences")] = Field(
        default="",
        description="Injected — never supplied by the model.",
    )
    # Injected conversation language (TravelAgentState.language); hotel
    # descriptions are localized to it at tool time (specs/catalog-content-i18n).
    language: Annotated[str, InjectedState("language")] = Field(
        default="",
        description="Injected — never supplied by the model.",
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
    allow_duplicate: bool = Field(
        False,
        description=(
            "Leave False. If the tool reports a possible duplicate (the traveller "
            "already has an active booking for this same hotel and exact dates), "
            "do NOT retry blindly — tell the traveller about the existing booking "
            "and ask whether they really want another one. Set True only after "
            "they explicitly confirm they want a second booking."
        ),
    )
    user_id: Annotated[str, InjectedState("user_id")] = Field(
        default="",
        description="Injected owner id from graph state — never supplied by the model.",
    )
    trip_id: Annotated[str | None, InjectedState("trip_id")] = Field(
        default=None,
        description=(
            "Injected active trip id from graph state — never supplied by "
            "the model. None when there is no active trip; the booking is "
            "then created unattached."
        ),
    )
    messages: Annotated[list, InjectedState("messages")] = Field(
        default_factory=list,
        description=(
            "Injected conversation messages from graph state — never supplied "
            "by the model."
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
    preferences: Annotated[str, InjectedState("preferences")] = "",
    language: Annotated[str, InjectedState("language")] = "",
) -> tuple[str, dict | None]:
    """Search hotels in a city with room availability for specific dates.

    Returns up to 12 hotels. On success the model sees a short summary and the
    full comparison is sent to the Hotels side panel. If no hotels match — either
    the city was not recognized or the filters/dates left nothing — returns a
    short message and no panel; tell the user none were found and never invent
    hotels. It is not an error.

    ``check_in``, ``check_out``, ``rooms``, ``adults`` and ``children`` are all
    required and have no defaults — never guess or assume a value the traveller has
    not given. The number of nights is derived from the two dates, so it is not a
    parameter. Values the traveller gave earlier in the conversation are still
    theirs: search with them instead of asking again, and echo them back in your
    reply so they can correct you. Ask only for a value that is genuinely missing,
    ambiguous, or contradicted by something they said later. Where your own
    instructions require confirming a detail before you call a tool — the booking
    flow does, ahead of a reservation — those come first; this rule is about not
    re-asking for what you already have, never about skipping a confirmation you
    were told to get.

    :param city: Free-text city name — fuzzy matched (e.g. 'danang' → 'Da Nang').
    :param check_in: Stay start date, YYYY-MM-DD. Must be today or later. For any
        non-ISO wording, call the resolve_date tool on the traveller's original
        expression first — never compute or guess a date yourself. With no
        dates from the traveller at all, do not call this tool — never default
        to today.
    :param check_out: Stay end date, YYYY-MM-DD. Must be after ``check_in``. For
        any non-ISO wording, call the resolve_date tool on the traveller's
        original expression first — never compute or guess a date yourself.
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
    today = today_in_timezone(get_settings().agent_timezone)
    try:
        check_in = resolve_travel_date(check_in, today)
        check_out = resolve_travel_date(check_out, today)
        parsed_check_in = datetime.strptime(check_in, "%Y-%m-%d").date()
    except ValueError as e:
        raise ToolException(
            f"check_in {check_in!r} / check_out {check_out!r} could not be resolved to "
            f"concrete YYYY-MM-DD dates. Today is {today.isoformat()}. Call the "
            "resolve_date tool on the traveller's original date expressions to get "
            "concrete dates — only ask the traveller if resolve_date reports one "
            "ambiguous."
        ) from e
    # 1-day grace for timezone skew between the server-configured `today` and the
    # traveller's own zone (their dates were resolved against their tz in the prompt).
    if parsed_check_in < today - timedelta(days=1):
        raise ToolException(
            f"check_in {check_in} is in the past (today is {today.isoformat()}). "
            "Do not guess or invent dates — call the resolve_date tool on the "
            "traveller's original date expressions to get the correct concrete "
            "dates; only ask if resolve_date reports one ambiguous."
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
            results, matched_reasons = rank_by_preference(
                results, preferences, keyword_fn=_hotel_keyword_features
            )
            # `check_availability` returns every hotel matching the city and filters,
            # flagging each one — a sold-out property is in `results` with
            # available=False. Name and count only the bookable ones, or the model
            # quotes "cheapest $190" for a hotel with no free room.
            free = [h for h in results if h.available]
            stay = (
                f"{results[0].city} for {check_in} to {check_out} "
                f"({nights} nights, {rooms} room{'s' if rooms > 1 else ''})"
            )
            if not free:
                summary = (
                    f"{len(results)} hotels in {stay}, but none has a room free for "
                    "those dates. Tell the user none are available and offer to try "
                    "other dates or relax the filters — do not present them as "
                    "bookable. The full list is in the Hotels panel, marked full."
                )
            else:
                cheapest = min(free, key=lambda h: h.total_price)
                top_rated = max(free, key=lambda h: h.rating)
                sold_out = len(results) - len(free)
                summary = (
                    f"{len(results)} hotels in {stay}. "
                    f"Cheapest {cheapest.name} ${cheapest.total_price:.0f}; "
                    f"top-rated {top_rated.name} ({top_rated.rating:.1f}★). "
                )
                if sold_out:
                    summary += (
                        f"{sold_out} of them have no room free for these dates — "
                        "do not offer those. "
                    )
                summary += "The full comparison is in the Hotels panel."
            if matched_reasons:
                summary += f" Prioritized based on your preferences: {', '.join(matched_reasons)}."
            # After ranking (keyword features match the English text), before the panel.
            results = ContentTranslationService(s).localize(
                "hotel", results, ["description"], language
            )
            return panel_result(
                summary,
                kind="hotels",
                data=HotelsPanel.from_hotels(
                    results[0].city, check_in, check_out, nights, rooms, results
                ),
            )
        except AppError as e:
            raise tool_error(e) from e
        except ValueError as e:
            raise ToolException(str(e)) from e


@tool(args_schema=BrowseHotelsArgs, response_format="content_and_artifact")
def browse_hotels(
    city: str,
    min_stars: int | None = None,
    max_price: float | None = None,
    amenities: list[str] | None = None,
    preferences: Annotated[str, InjectedState("preferences")] = "",
    language: Annotated[str, InjectedState("language")] = "",
) -> tuple[str, dict | None]:
    """Answer hotel info/search questions — price, location, amenities, rating — with no dates.

    Use this to browse what's in a city (e.g. "hotels in Da Nang under $100",
    "any 4-star places with a pool?"). Use it when the traveller has given
    **no dates** — it does not check date-specific availability and does not
    book. As soon as they give check-in and check-out, use ``search_hotels``
    instead, which checks real availability for those dates; ``book_hotel``
    (the actual reservation) stays with the booking flow.

    Returns up to 12 hotels, sorted cheapest nightly rate first (best value on
    top) — unless the traveller's known preferences (star rating, hotel type,
    beachfront) boost a better match to the top, in which case cheapest-price
    order is kept only as the tiebreaker. On success the model sees a short
    summary and the full comparison is sent to the Hotels side panel. If no
    hotels match — either the city was not
    recognized or the filters left nothing — returns a short message and no
    panel; tell the user none were found and never invent hotels. It is not an
    error.

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
            # Default sort: cheapest nightly rate first, so the panel leads with
            # the best-value option (ties keep the seed order — sorted() is stable).
            results = sorted(results, key=lambda h: h.price_per_night)
            # Preference boost layers on top, stably — cheapest-first is preserved
            # as the tiebreaker among hotels with equal preference-match scores.
            results, matched_reasons = rank_by_preference(
                results, preferences, keyword_fn=_hotel_keyword_features
            )
            # Re-ranking can move a pricier preferred hotel to position 0, so the
            # "cheapest" callout must still look up the actual min price — not
            # just index 0 — regardless of preference re-order.
            cheapest = min(results, key=lambda h: h.price_per_night)
            top_rated = max(results, key=lambda h: h.rating)
            summary = (
                f"{len(results)} hotels in {results[0].city}. "
                f"Cheapest {cheapest.name} ${cheapest.price_per_night:.0f}/night; "
                f"top-rated {top_rated.name} ({top_rated.rating:.1f}★). "
                "The full comparison is in the Hotels panel."
            )
            if matched_reasons:
                summary += f" Prioritized based on your preferences: {', '.join(matched_reasons)}."
            results = ContentTranslationService(s).localize(
                "hotel", results, ["description"], language
            )
            return panel_result(
                summary,
                kind="hotels",
                data=HotelsPanel.from_catalog(results[0].city, results),
            )
        except AppError as e:
            raise tool_error(e) from e
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
    allow_duplicate: bool = False,
    user_id: Annotated[str, InjectedState("user_id")] = "",
    trip_id: Annotated[str | None, InjectedState("trip_id")] = None,
    messages: Annotated[list, InjectedState("messages")] = None,
    *,
    config: RunnableConfig,
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
    :param allow_duplicate: Leave False. If the tool reports a possible duplicate
        (an existing active booking for the same hotel + exact dates), tell the
        traveller and ask; set True only after they explicitly confirm they want
        another booking.
    :param user_id: The owner id, injected from graph state (not model-supplied);
        stamped on the booking so it is scoped to the authenticated traveller.
    :param trip_id: The active trip id, injected from graph state (not
        model-supplied). None when there is no active trip — the booking is
        then created unattached, not refused.
    :return: The confirmed Booking with id, confirmation_code, and total_price.
    """
    # Log only the booking identifiers, never guest name/email/phone
    # (guidelines: never log sensitive contact details).
    log_tool_call(
        "book_hotel",
        {
            "hotel_id": hotel_id,
            "check_in": check_in,
            "check_out": check_out,
            "rooms": rooms,
            "adults": adults,
            "children": children,
            "confirm": confirm,
            "allow_duplicate": allow_duplicate,
        },
    )
    if not confirm:
        raise ToolException(
            "set confirm=true to book — this action creates a real reservation"
        )
    # Replay-safety within one traveller turn (gh-193): see book_flight.
    # `allow_duplicate` is deliberately OUT of the idempotency args, and — because
    # a blocked duplicate raises before inserting, leaving no row to replay — a
    # same-turn re-run with allow_duplicate=true could otherwise slip a second
    # booking through without the traveller confirming. Guard that per booking id
    # (gh-200): `warned` is the set of booking ids flagged as duplicates this
    # turn, so we force the duplicate check back on whenever any warning stands
    # and honour the override only for a booking that was NOT flagged (a bare
    # legacy marker flags every booking of this tool).
    warned = duplicate_warned_ids_this_turn("book_hotel", messages)
    idempotency_key = turn_idempotency_key(
        "book_hotel",
        {
            "hotel_id": hotel_id,
            "check_in": check_in,
            "check_out": check_out,
            "guest_name": guest_name,
            "guest_email": guest_email,
            "guest_phone": guest_phone,
            "rooms": rooms,
            "adults": adults,
            "children": children,
            "notes": notes,
            "confirm": confirm,
        },
        user_id=user_id,
        config=config,
        messages=messages,
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
                trip_id=trip_id,
            )
            service = BookingService(s)
            try:
                result = service.book_hotel(
                    request,
                    user_id=user_id,
                    idempotency_key=idempotency_key,
                    check_duplicate=(not allow_duplicate) or bool(warned),
                )
            except DuplicateBookingError as e:
                if allow_duplicate and duplicate_override_refused(
                    e.existing.id, warned
                ):
                    raise ToolException(
                        f"{tool_error(e)} {OVERRIDE_REFUSED_HINT}"
                    ) from e
                if not allow_duplicate:
                    raise tool_error(e) from e
                # The warning was about a *different* booking, so the traveller's
                # override stands. Re-book without the duplicate check on the same
                # BookingService/session, so the gh-198 per-owner advisory lock the
                # first attempt took is still held for this insert.
                result = service.book_hotel(
                    request,
                    user_id=user_id,
                    idempotency_key=idempotency_key,
                    check_duplicate=False,
                )
            return dump(result)
        except AppError as e:
            raise tool_error(e) from e
        except ValueError as e:
            raise ToolException(str(e)) from e


# Concierge's dateless catalog browse (MIN-51) — never asks for dates/occupancy.
HOTEL_SEARCH_TOOLS = [browse_hotels]
# Planner's dated availability search (no reservation power — booking owns the money tools).
HOTEL_AVAILABILITY_TOOLS = [search_hotels]
HOTEL_BOOKING_TOOLS = [book_hotel]
# Booking's dated availability search + the actual reservation.
HOTEL_TOOLS = HOTEL_AVAILABILITY_TOOLS + HOTEL_BOOKING_TOOLS
