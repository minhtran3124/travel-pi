"""Flight search tools (specs/travel-agent Task 3.3).

Wrap ``FlightService`` as an LLM tool. Opens its own session via
``session_scope`` and maps domain errors to ``ToolException`` so the agent
can self-correct.  Flights are deterministic — same route + date = same 5
flights — so the agent can reference a specific flight across turns.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from langchain_core.tools import ToolException, tool
from pydantic import Field

from app.core.config import get_settings
from app.core.dates import resolve_travel_date, today_in_timezone
from app.exceptions import AppError
from app.schemas.base import AppBaseModel
from app.services.flight_service import DEFAULT_SORT, FlightService
from app.streaming.panels import FlightsPanel
from app.tools._base import log_tool_call, panel_result, session_scope

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
    airline: str | None = Field(
        None, description="Optional 2-letter IATA airline code to filter by."
    )
    max_price: float | None = Field(
        None, description="Optional maximum ticket price filter."
    )
    max_stops: int | None = Field(None, description="Optional maximum number of stops.")
    sort: FlightSort = Field("departure_asc", description="Result ordering.")


@tool(args_schema=SearchFlightsArgs, response_format="content_and_artifact")
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
    :param departure_date: ISO date YYYY-MM-DD. Must be today or later. For any
        non-ISO wording (e.g. "today", "tomorrow", "next Friday"), call the
        resolve_date tool on the traveller's original expression first — never
        compute or guess a date yourself.
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
