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
from app.tools._base import dump, session_scope


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

    origin / destination: 3-letter IATA codes (e.g. 'HAN', 'SGN', 'NRT').
    departure_date: ISO date YYYY-MM-DD.
    airline: 2-letter IATA code to filter by carrier (e.g. 'VN').
    max_price: keep only flights at or below this fare.
    max_stops: 0 = nonstop only, 1 = up to one stop.
    sort: departure_asc | departure_desc | price_asc | price_desc |
          duration_asc | duration_desc. Defaults to departure_asc.
    Returns up to 5 deterministic flights — same query always returns the same
    results. Each item has id, flight_number, airline, departure_time,
    arrival_time, duration_minutes, price, seats_available, and stops.
    """
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
            return dump(results)
        except AppError as e:
            raise ToolException(str(e)) from e
        except ValueError as e:
            raise ToolException(str(e)) from e


FLIGHT_TOOLS = [search_flights]
