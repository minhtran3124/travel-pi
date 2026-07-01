"""Flight search tools (specs/travel-agent Task 3.3).

Wrap ``FlightService`` as an LLM tool. Opens its own session via
``session_scope`` and maps domain errors to ``ToolException`` so the agent
can self-correct.  Flights are deterministic — same route + date = same 5
flights — so the agent can reference a specific flight across turns.
"""

from __future__ import annotations

from datetime import datetime, timezone

from langchain_core.tools import ToolException, tool

from app.exceptions import AppError
from app.services.flight_service import DEFAULT_SORT, FlightService
from app.streaming.panels import FlightsPanel
from app.tools._base import log_tool_call, panel_result, session_scope


@tool(response_format="content_and_artifact")
def search_flights(
    origin: str,
    destination: str,
    departure_date: str,
    airline: str | None = None,
    max_price: float | None = None,
    max_stops: int | None = None,
    sort: str = DEFAULT_SORT,
) -> tuple[str, dict | None]:
    """Search flights for a route and date with optional filters and sort.

    Returns up to 5 deterministic flights — same query always returns the same
    results. On success the model sees a short summary and the full comparison is
    sent to the Flights side panel. If no flights match, returns a short message
    and no panel; tell the user none were found and never invent flights.

    :param origin: 3-letter IATA code for the origin airport (e.g. 'HAN', 'SGN', 'NRT').
    :param destination: 3-letter IATA code for the destination airport (e.g. 'HAN', 'SGN', 'NRT').
    :param departure_date: ISO date YYYY-MM-DD. Must be today or later — resolve
        relative dates (e.g. "today", "tomorrow") against the current date given in
        the system prompt; never guess or pass a past date.
    :param airline: 2-letter IATA code to filter by carrier (e.g. 'VN').
    :param max_price: Keep only flights at or below this fare.
    :param max_stops: 0 = nonstop only, 1 = up to one stop.
    :param sort: departure_asc | departure_desc | price_asc | price_desc |
        duration_asc | duration_desc. Defaults to departure_asc.
    :return: A (summary, artifact) tuple. On matches the artifact is a
        ``{"kind": "flights", "data": ...}`` side-panel payload; on no match the
        artifact is ``None`` (no panel) and the summary explains the empty result.
    """
    log_tool_call("search_flights", locals())
    today = datetime.now(timezone.utc).date()
    try:
        parsed_date = datetime.strptime(departure_date, "%Y-%m-%d").date()
    except ValueError as e:
        raise ToolException(
            f"departure_date {departure_date!r} is not a valid YYYY-MM-DD date. "
            f"Today is {today.isoformat()}. Ask the traveller for a concrete date "
            "instead of guessing."
        ) from e
    if parsed_date < today:
        raise ToolException(
            f"departure_date {departure_date} is in the past (today is "
            f"{today.isoformat()}). Do not guess or invent dates — confirm the "
            "traveller's intended date, resolving relative terms like 'today' or "
            "'next Friday' against today."
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
            cheapest = min(results, key=lambda f: f.price)
            earliest = min(results, key=lambda f: f.departure_time)
            summary = (
                f"{len(results)} flights {origin}→{destination} on {departure_date}. "
                f"Cheapest {cheapest.flight_number} ${cheapest.price:.0f}; "
                f"earliest {earliest.flight_number} at {earliest.departure_time:%H:%M}. "
                "The full comparison is in the Flights panel."
            )
            return panel_result(
                summary,
                kind="flights",
                data=FlightsPanel.from_flights(
                    origin, destination, departure_date, results
                ),
            )
        except AppError as e:
            raise ToolException(str(e)) from e
        except ValueError as e:
            raise ToolException(str(e)) from e


FLIGHT_TOOLS = [search_flights]
