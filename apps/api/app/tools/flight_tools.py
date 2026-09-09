"""Flight search tools (specs/travel-agent Task 3.3).

Wrap ``FlightService`` as an LLM tool. Opens its own session via
``session_scope`` and maps domain errors to ``ToolException`` so the agent
can self-correct.  Flights are deterministic — same route + date = same 5
flights — so the agent can reference a specific flight across turns.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Literal

from langchain_core.tools import ToolException, tool
from langgraph.prebuilt import InjectedState
from pydantic import Field

from app.core.config import get_settings
from app.core.dates import resolve_travel_date, today_in_timezone
from app.exceptions import AppError
from app.schemas.base import AppBaseModel
from app.schemas.flight import FlightBookingRequest
from app.services.booking_service import BookingService
from app.services.flight_service import DEFAULT_SORT, FlightService
from app.streaming.panels import FlightsPanel
from app.tools._base import dump, log_tool_call, panel_result, session_scope, tool_error
from app.tools._ranking import rank_by_preference


def _flight_keyword_features(flight) -> list[tuple[list[str], str]]:
    """Preference-matchable features for one flight search result (DESIGN.md D7).

    Time-of-day boundary: "morning" matches a 05:00–11:59 departure, "evening"
    matches 18:00–23:59 — the two ranges travellers most commonly mean by those
    words. Midday and red-eye (00:00–04:59) departures are left unboosted
    (v1 trade-off, boost-only so it never hides a flight that doesn't match).
    """
    features: list[tuple[list[str], str]] = [
        ([flight.airline.name, flight.airline.code], flight.airline.name)
    ]
    hour = flight.departure_time.hour
    if 5 <= hour < 12:
        features.append((["morning", "sáng", "buổi sáng"], "morning departure"))
    elif hour >= 18:
        features.append((["evening", "tối", "buổi tối"], "evening departure"))
    return features


FlightSort = Literal[
    "departure_asc",
    "departure_desc",
    "price_asc",
    "price_desc",
    "duration_asc",
    "duration_desc",
]


class SearchFlightsArgs(AppBaseModel):
    origin: str = Field(
        ..., description="3-letter IATA origin airport code, e.g. 'HAN'."
    )
    destination: str = Field(
        ..., description="3-letter IATA destination airport code, e.g. 'SGN'."
    )
    departure_date: str = Field(
        ...,
        description="Departure date, ISO format YYYY-MM-DD. Must not be in the past.",
    )
    return_date: str | None = Field(
        None,
        description=(
            "Optional return date, ISO format YYYY-MM-DD, to price a round trip. "
            "When set, the return leg (destination→origin) is searched too and its "
            "real fare is returned — never double the outbound fare to estimate a "
            "round-trip total, always search the return leg with this parameter."
        ),
    )
    airline: str | None = Field(
        None, description="Optional 2-letter IATA airline code to filter by."
    )
    max_price: float | None = Field(
        None, description="Optional maximum ticket price filter."
    )
    max_stops: int | None = Field(None, description="Optional maximum number of stops.")
    sort: FlightSort = Field("departure_asc", description="Result ordering.")
    preferences: Annotated[str, InjectedState("preferences")] = Field(
        default="",
        description="Injected — never supplied by the model.",
    )


@tool(args_schema=SearchFlightsArgs, response_format="content_and_artifact")
def search_flights(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str | None = None,
    airline: str | None = None,
    max_price: float | None = None,
    max_stops: int | None = None,
    sort: str = DEFAULT_SORT,
    preferences: Annotated[str, InjectedState("preferences")] = "",
) -> tuple[str, dict | None]:
    """Search flights for a route and date with optional filters and sort.

    Returns up to 5 deterministic flights — same query always returns the same
    results. On success the model sees a short summary and the full comparison is
    sent to the Flights side panel. If no flights match, returns a short message
    and no panel; tell the user none were found and never invent flights. To
    price a round trip, pass ``return_date`` so the return leg is actually
    searched — never double the outbound fare to estimate a total.

    :param origin: 3-letter IATA code for the origin airport (e.g. 'HAN', 'SGN', 'NRT').
    :param destination: 3-letter IATA code for the destination airport (e.g. 'HAN', 'SGN', 'NRT').
    :param departure_date: ISO date YYYY-MM-DD. Must be today or later. For any
        non-ISO wording (e.g. "today", "tomorrow", "next Friday"), call the
        resolve_date tool on the traveller's original expression first — never
        compute or guess a date yourself.
    :param return_date: Optional ISO date YYYY-MM-DD for the return leg
        (destination→origin). When set, its real fare is included in the
        summary — resolve non-ISO wording the same way as ``departure_date``.
    :param airline: 2-letter IATA code to filter by carrier (e.g. 'VN').
    :param max_price: Keep only flights at or below this fare.
    :param max_stops: 0 = nonstop only, 1 = up to one stop.
    :param sort: Result ordering (see ``FlightSort``). Defaults to departure_asc.
    :return: A (summary, artifact) tuple. On matches the artifact is a
        ``{"kind": "flights", "data": ...}`` side-panel payload; on no match the
        artifact is ``None`` (no panel) and the summary explains the empty result.
    """
    log_tool_call("search_flights", locals())
    today = today_in_timezone(get_settings().agent_timezone)
    try:
        departure_date = resolve_travel_date(departure_date, today)
        parsed_date = datetime.strptime(departure_date, "%Y-%m-%d").date()
    except ValueError as e:
        raise ToolException(
            f"departure_date {departure_date!r} could not be resolved to a concrete "
            f"YYYY-MM-DD date. Today is {today.isoformat()}. Call the resolve_date "
            "tool on the traveller's original date expression to get a concrete "
            "date — only ask the traveller if resolve_date reports it ambiguous."
        ) from e
    # 1-day grace: `today` is computed in the server's configured zone, but the
    # traveller's date was resolved against their own timezone (in the prompt), so
    # the two "todays" can differ by up to a day. Tolerate that skew rather than
    # reject a date the traveller correctly considers today/future.
    if parsed_date < today - timedelta(days=1):
        raise ToolException(
            f"departure_date {departure_date} is in the past (today is "
            f"{today.isoformat()}). Do not guess or invent dates — call the "
            "resolve_date tool on the traveller's original date expression to get "
            "the correct concrete date; only ask if resolve_date reports it "
            "ambiguous."
        )
    if return_date is not None:
        try:
            return_date = resolve_travel_date(return_date, today)
            parsed_return_date = datetime.strptime(return_date, "%Y-%m-%d").date()
        except ValueError as e:
            raise ToolException(
                f"return_date {return_date!r} could not be resolved to a concrete "
                f"YYYY-MM-DD date. Today is {today.isoformat()}. Call the "
                "resolve_date tool on the traveller's original date expression to "
                "get a concrete date — only ask the traveller if resolve_date "
                "reports it ambiguous."
            ) from e
        if parsed_return_date < today - timedelta(days=1):
            raise ToolException(
                f"return_date {return_date} is in the past (today is "
                f"{today.isoformat()}). Do not guess or invent dates — call the "
                "resolve_date tool on the traveller's original date expression to "
                "get the correct concrete date; only ask if resolve_date reports "
                "it ambiguous."
            )
    with session_scope() as s:
        try:
            results = FlightService(s).search_flights(
                origin,
                destination,
                departure_date,
                airline=airline,
                max_price=max_price,
                max_stops=max_stops,
                sort=sort,
            )
            if not results:
                applied = []
                if airline:
                    applied.append(f"airline={airline}")
                if max_price is not None:
                    applied.append(f"max_price={max_price}")
                if max_stops is not None:
                    applied.append(f"max_stops={max_stops}")
                suffix = (
                    f" matching your filters ({', '.join(applied)})" if applied else ""
                )
                return (
                    f"No flights from {origin} to {destination} on {departure_date}{suffix}. "
                    "Tell the user none were found and suggest relaxing the filters — "
                    "do not invent flights.",
                    None,
                )
            # Preference boost layers on top of the requested `sort`, stably —
            # the caller's chosen order is kept as the tiebreaker.
            results, matched_reasons = rank_by_preference(
                results, preferences, keyword_fn=_flight_keyword_features
            )
            cheapest = min(results, key=lambda f: f.price)
            earliest = min(results, key=lambda f: f.departure_time)
            currency = cheapest.currency

            return_results = None
            if return_date is not None:
                # Mirrors the REST layer's round-trip pattern (routers/flights.py):
                # a second, independent search on the swapped leg — never a fare
                # derived from the outbound search.
                return_results = FlightService(s).search_flights(
                    destination,
                    origin,
                    return_date,
                    airline=airline,
                    max_price=max_price,
                    max_stops=max_stops,
                    sort=sort,
                )

            if return_results is None:
                summary = (
                    f"{len(results)} one-way flights {origin}→{destination} on "
                    f"{departure_date} ({currency}). Cheapest {cheapest.flight_number} "
                    f"{currency} {cheapest.price:.0f}; earliest {earliest.flight_number} "
                    f"at {earliest.departure_time:%H:%M}. The full comparison is in "
                    "the Flights panel."
                )
            elif return_results:
                return_cheapest = min(return_results, key=lambda f: f.price)
                summary = (
                    f"{len(results)} outbound flights {origin}→{destination} on "
                    f"{departure_date} ({currency}). Cheapest outbound "
                    f"{cheapest.flight_number} {currency} {cheapest.price:.0f}; "
                    f"earliest {earliest.flight_number} at "
                    f"{earliest.departure_time:%H:%M}. {len(return_results)} return "
                    f"flights {destination}→{origin} on {return_date}. Cheapest "
                    f"return {return_cheapest.flight_number} {currency} "
                    f"{return_cheapest.price:.0f}. These are two separate one-way "
                    "fares — the full comparison is in the Flights panel."
                )
            else:
                summary = (
                    f"{len(results)} outbound flights {origin}→{destination} on "
                    f"{departure_date} ({currency}). Cheapest outbound "
                    f"{cheapest.flight_number} {currency} {cheapest.price:.0f}; "
                    f"earliest {earliest.flight_number} at "
                    f"{earliest.departure_time:%H:%M}. No return flights found "
                    f"{destination}→{origin} on {return_date}."
                )
            if matched_reasons:
                summary += f" Prioritized based on your preferences: {', '.join(matched_reasons)}."
            return panel_result(
                summary,
                kind="flights",
                data=FlightsPanel.from_flights(
                    origin, destination, departure_date, results
                ),
            )
        except AppError as e:
            raise tool_error(e) from e
        except ValueError as e:
            raise ToolException(str(e)) from e


class BookFlightArgs(AppBaseModel):
    flight_id: str | None = Field(
        None,
        description=(
            "The `id` of a flight from a search_flights result. Provide this "
            "OR flight_number+origin+destination+departure_date, not both."
        ),
    )
    flight_number: str | None = Field(
        None,
        description=(
            "Carrier code + number, e.g. 'VN123'. Required (with "
            "origin+destination+departure_date) when flight_id is not given."
        ),
    )
    origin: str | None = Field(
        None, description="3-letter IATA origin code, e.g. 'HAN'."
    )
    destination: str | None = Field(
        None, description="3-letter IATA destination code, e.g. 'SGN'."
    )
    departure_date: str | None = Field(None, description="Departure date, YYYY-MM-DD.")
    passenger_name: str = Field(
        ..., description="Full name as printed on the passenger's ID/passport."
    )
    passenger_email: str = Field(
        ..., description="Contact email for the itinerary and e-ticket."
    )
    passenger_phone: str = Field(
        ..., description="Contact phone for airline notifications (delays, gate)."
    )
    notes: str | None = Field(
        None, description="Optional note for the airline (seat/meal preference)."
    )
    passengers: int = Field(
        default=1,
        ge=1,
        description=(
            "Number of seats to book. Get this explicitly from the traveller "
            "rather than assuming 1 — one booking covers all of them, so do "
            "not call book_flight once per traveller."
        ),
    )
    confirm: bool = Field(
        False,
        description=(
            "Must be set to True to execute the booking — prevents accidental "
            "reservations. Leaving it False (the default) will not book anything."
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


@tool(args_schema=BookFlightArgs)
def book_flight(
    passenger_name: str,
    passenger_email: str,
    passenger_phone: str,
    flight_id: str | None = None,
    flight_number: str | None = None,
    origin: str | None = None,
    destination: str | None = None,
    departure_date: str | None = None,
    notes: str | None = None,
    passengers: int = 1,
    confirm: bool = False,
    user_id: Annotated[str, InjectedState("user_id")] = "",
    trip_id: Annotated[str | None, InjectedState("trip_id")] = None,
) -> dict:
    """Book a flight. You MUST pass confirm=True to create the reservation.

    Identify the flight EITHER by ``flight_id`` (from a search_flights result)
    OR by ``flight_number`` + ``origin`` + ``destination`` + ``departure_date``
    — provide one, not both. Raises ``ToolException`` if the flight is not found
    or the identifier is invalid/incomplete.

    :param passenger_name: Full name as printed on the passenger's ID/passport.
    :param passenger_email: Contact email for the itinerary and e-ticket.
    :param passenger_phone: Contact phone for airline notifications.
    :param flight_id: The `id` from a search_flights result (mode A).
    :param flight_number: Carrier code + number, e.g. 'VN123' (mode B).
    :param origin: 3-letter IATA origin code (mode B).
    :param destination: 3-letter IATA destination code (mode B).
    :param departure_date: Departure date YYYY-MM-DD (mode B).
    :param notes: Optional note for the airline.
    :param passengers: Number of seats to book, from the traveller — one
        booking covers all of them, never call this once per traveller.
    :param confirm: Must be True to execute the booking; left False, nothing books.
    :param user_id: The owner id, injected from graph state (not model-supplied);
        stamped on the booking so it is scoped to the authenticated traveller.
    :param trip_id: The active trip id, injected from graph state (not
        model-supplied). None when there is no active trip — the booking is
        then created unattached, not refused.
    :return: The confirmed Booking with id, confirmation_code, status, total_price.
    """
    # Log only the non-PII flight identifiers, not passenger name/email/phone
    # (guidelines: never log sensitive data).
    log_tool_call(
        "book_flight",
        {
            "flight_id": flight_id,
            "flight_number": flight_number,
            "origin": origin,
            "destination": destination,
            "departure_date": departure_date,
            "passengers": passengers,
            "confirm": confirm,
        },
    )
    if not confirm:
        raise ToolException(
            "set confirm=true to book — this action creates a real reservation"
        )
    with session_scope() as s:
        try:
            request = FlightBookingRequest(
                flight_id=flight_id,
                flight_number=flight_number,
                origin=origin,
                destination=destination,
                departure_date=departure_date,
                passenger_name=passenger_name,
                passenger_email=passenger_email,
                passenger_phone=passenger_phone,
                notes=notes,
                passengers=passengers,
                trip_id=trip_id,
            )
            result = BookingService(s).book_flight(request, user_id=user_id)
            return dump(result)
        except AppError as e:
            raise tool_error(e) from e
        except ValueError as e:
            raise ToolException(str(e)) from e


# Planner's flight search (no reservation power — booking owns the money tools).
FLIGHT_SEARCH_TOOLS = [search_flights]
FLIGHT_BOOKING_TOOLS = [book_flight]
# Booking's search + the actual reservation.
FLIGHT_TOOLS = FLIGHT_SEARCH_TOOLS + FLIGHT_BOOKING_TOOLS
