"""MIN-67 / GitHub #98 regression: round-trip fares must come from a real
return-leg search, never from doubling the outbound fare.

The agent searched only the outbound leg (`DAD -> TYO`, 2026-09-01) and told
the traveller "from $136 round-trip total if you take the cheapest one each
way" -- `$68 x 2`. No return leg was ever searched; the number came from no
tool call at all. This pins the fix at the deterministic tool+service seam:
flight generation is seeded from `origin-destination-date` (MD5), so the same
query always returns the same fares and we can assert on them directly
without touching model prose.
"""

from datetime import datetime, timedelta, timezone

from app.db.engine import get_session_factory
from app.services.flight_service import FlightService
from app.tools.flight_tools import search_flights

_ORIGIN = "HAN"
_DESTINATION = "SGN"


def _round_trip_dates() -> tuple[str, str]:
    """Departure ~45 days out, return a week later — always in the future so
    the test never rots, per repo convention (`datetime.now(timezone.utc)`,
    never `utcnow()`)."""
    today = datetime.now(timezone.utc).date()
    departure = today + timedelta(days=45)
    return_ = departure + timedelta(days=7)
    return departure.isoformat(), return_.isoformat()


def test_round_trip_return_leg_is_real_not_doubled(agent_db):
    """A round-trip search must surface the REAL return-leg cheapest fare —
    not the outbound fare doubled (the exact MIN-67 defect)."""
    departure_date, return_date = _round_trip_dates()

    # Independently compute what the deterministic generator produces for
    # each leg, at the same seam the tool itself calls into.
    with get_session_factory(agent_db)() as s:
        service = FlightService(s)
        outbound = service.search_flights(_ORIGIN, _DESTINATION, departure_date)
        homebound = service.search_flights(_DESTINATION, _ORIGIN, return_date)
    outbound_cheapest = min(outbound, key=lambda f: f.price)
    return_cheapest = min(homebound, key=lambda f: f.price)
    currency = outbound_cheapest.currency

    # Guard the test's own premise: the route/dates must genuinely produce a
    # return fare that differs from the outbound fare doubled, otherwise a
    # naive `return = outbound * 2` implementation could coincidentally pass.
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

    # The summary must state the real return-leg cheapest fare and flight
    # number — proof it came from the actual second search, not arithmetic
    # on the outbound result.
    assert (
        f"Cheapest return {return_cheapest.flight_number} {currency} "
        f"{return_cheapest.price:.0f}" in msg.content
    )
    doubled_snippet = f"{currency} {outbound_cheapest.price * 2:.0f}"
    assert doubled_snippet not in msg.content


def test_one_way_search_labels_summary_and_names_currency(agent_db):
    """A one-way search (no `return_date`) must be labelled one-way and name
    the currency — the cue the model needs to know what the number covers."""
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
