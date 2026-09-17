"""Round-trip fares must come from a real return-leg search, never from doubling
the outbound fare. Flight generation is seeded deterministically from
origin-destination-date, so we assert on fares directly without touching prose."""

from datetime import datetime, timedelta, timezone

from app.db.engine import get_session_factory
from app.services.flight_service import FlightService
from app.tools.flight_tools import search_flights

_ORIGIN = "HAN"
_DESTINATION = "SGN"


def _round_trip_dates() -> tuple[str, str]:
    """Departure ~45 days out, return a week later — always future so the test never rots."""
    today = datetime.now(timezone.utc).date()
    departure = today + timedelta(days=45)
    return_ = departure + timedelta(days=7)
    return departure.isoformat(), return_.isoformat()


def test_round_trip_return_leg_is_real_not_doubled(agent_db):
    """A round-trip search must surface the REAL return-leg cheapest fare, not the
    outbound fare doubled."""
    departure_date, return_date = _round_trip_dates()

    # Independently compute each leg at the same seam the tool calls into.
    with get_session_factory(agent_db)() as s:
        service = FlightService(s)
        outbound = service.search_flights(_ORIGIN, _DESTINATION, departure_date)
        homebound = service.search_flights(_DESTINATION, _ORIGIN, return_date)
    outbound_cheapest = min(outbound, key=lambda f: f.price)
    return_cheapest = min(homebound, key=lambda f: f.price)
    currency = outbound_cheapest.currency

    # Test-premise guard: the return fare must differ from doubling the outbound,
    # else a naive `return = outbound * 2` could coincidentally pass.
    assert return_cheapest.price != outbound_cheapest.price * 2, (
        "chosen route/date offsets no longer diverge from doubling — adjust "
        "_round_trip_dates() offsets"
    )

    msg = search_flights.invoke(
        {
            "type": "tool_call",
            "id": "t1",
            "name": "search_flights",
            "args": {
                "origin": _ORIGIN,
                "destination": _DESTINATION,
                "departure_date": departure_date,
                "return_date": return_date,
            },
        }
    )

    assert (
        f"Cheapest return {return_cheapest.flight_number} {currency} "
        f"{return_cheapest.price:.0f}" in msg.content
    )
    doubled_snippet = f"{currency} {outbound_cheapest.price * 2:.0f}"
    assert doubled_snippet not in msg.content


def test_one_way_search_labels_summary_and_names_currency(agent_db):
    """A one-way search must be labelled one-way and name the currency, the cue the
    model needs to know what the number covers."""
    departure_date, _ = _round_trip_dates()

    with get_session_factory(agent_db)() as s:
        service = FlightService(s)
        outbound = service.search_flights(_ORIGIN, _DESTINATION, departure_date)
    currency = outbound[0].currency

    msg = search_flights.invoke(
        {
            "type": "tool_call",
            "id": "t1",
            "name": "search_flights",
            "args": {
                "origin": _ORIGIN,
                "destination": _DESTINATION,
                "departure_date": departure_date,
            },
        }
    )

    assert "one-way" in msg.content
    assert currency in msg.content
    assert "return" not in msg.content.lower()
