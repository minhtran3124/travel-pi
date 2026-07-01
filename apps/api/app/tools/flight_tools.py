"""Flight search tools (specs/travel-agent Task 3.3).

Wrap ``FlightService`` as an LLM tool. Opens its own session via
``session_scope`` and maps domain errors to ``ToolException`` so the agent
can self-correct.  Flights are deterministic — same route + date = same 5
flights — so the agent can reference a specific flight across turns.
"""

from __future__ import annotations

from langchain_core.tools import ToolException, tool

from app.exceptions import AppError
from app.services.flight_service import DEFAULT_SORT, FlightService
from app.tools._base import dump, log_tool_call, session_scope


@tool
def search_flights(
    origin: str,
    destination: str,
    departure_date: str,
    airline: str | None = None,
    max_price: float | None = None,
    max_stops: int | None = None,
    sort: str = DEFAULT_SORT,
) -> list:
    """Search flights for a route and date with optional filters and sort.

    Returns up to 5 deterministic flights — same query always returns the same
    results.

    :param origin: 3-letter IATA code for the origin airport (e.g. 'HAN', 'SGN', 'NRT').
    :param destination: 3-letter IATA code for the destination airport (e.g. 'HAN', 'SGN', 'NRT').
    :param departure_date: ISO date YYYY-MM-DD.
    :param airline: 2-letter IATA code to filter by carrier (e.g. 'VN').
    :param max_price: Keep only flights at or below this fare.
    :param max_stops: 0 = nonstop only, 1 = up to one stop.
    :param sort: departure_asc | departure_desc | price_asc | price_desc |
        duration_asc | duration_desc. Defaults to departure_asc.
    :return: Up to 5 flights, each with id, flight_number, airline,
        departure_time, arrival_time, duration_minutes, price,
        seats_available, and stops. If no flights match, returns a dict
        ``{"results": [], "reason": "no_match", "message": ...}`` instead —
        tell the user none were found; never invent flights.
    """
    log_tool_call("search_flights", locals())
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
                return {
                    "results": [],
                    "reason": "no_match",
                    "message": (
                        f"No flights from {origin} to {destination} on "
                        f"{departure_date}{suffix}. Tell the user none were found and "
                        "suggest relaxing the filters — do not invent flights."
                    ),
                }
            return dump(results)
        except AppError as e:
            raise ToolException(str(e)) from e
        except ValueError as e:
            raise ToolException(str(e)) from e


FLIGHT_TOOLS = [search_flights]
