"""DB-as-Oracle adapter for travel-pi (agent-eval-pipeline task 3.2).

Implements the `Oracle` port (`evalkit.ports.Oracle`) by recomputing ground
truth through the SAME services the agent's tools call — never by
re-deriving the MD5 seed math here, and never by asking the agent. This is
`docs/solutions/agent/llm-parses-code-computes.md` applied at the eval layer
(see also `specs/agent-eval-pipeline/design-agentic-evolution.md` L-A): the
oracle *computes*; `OracleFactCheck` (`evalkit/metrics/oracle.py`) only ever
*extracts and compares* — it never adjudicates correctness on its own.

Kinds implemented — chosen because each is genuinely computable from the
seeded DB today, without duplicating a service's own math:

- ``flight_offers`` — `FlightService.generate_flights` (the same generator
  `search_flights`/`book_flight` tools call): count + cheapest/most
  expensive price for a seeded route + date.
- ``hotel_availability`` — `HotelService.check_availability` (the same
  method `search_hotels` calls): nights, hotel count, available count,
  cheapest available total price.
- ``fx_rate`` — `CurrencyService.convert`: the DB-backed FX rate between two
  currencies. No agent tool calls `CurrencyService` yet (`/currency/convert`
  is HTTP-only, `app/routers/currency.py`), but the fact is genuinely
  DB-computable and the plan names this kind explicitly.
- ``trip_budget`` — `TripService.get_trip_budget`: per-category caps/spend
  for a seeded trip_id. Trips are owner-scoped (#118), so params must also
  carry the ``user_id`` that owns the trip.

  CONSTRAINT (per `specs/agent-eval-pipeline/PLAN.md` task 3.2, and the
  dataset task before it): the single-shot eval harness has no live
  ``trip_id`` to check an agent reply against, so **no golden currently
  declares a ``trip_budget`` oracle_check** — ``eval/datasets/budget.json``
  deliberately has none. Only `tests/eval/test_db_oracle.py` exercises this
  kind today, against a trip it seeds itself. `supports("trip_budget")` is
  still `True` — the kind IS honestly computable — but a golden can only use
  it once a seeded-trip eval flow exists (a future task); wiring one up here
  would mean inventing a fake trip_id no real run could ever produce.

Unsupported kind: `supports()` returns `False`; `lookup()` raises
`ValueError`. Callers (`OracleFactCheck`) MUST check `supports()` first and
treat `False` as not_applicable — never as a pass.
"""

from __future__ import annotations

from typing import Any

from app.services.currency_service import CurrencyService
from app.services.flight_service import FlightService
from app.services.hotel_service import HotelService
from app.services.trip_service import TripService
from sqlalchemy.orm import Session

_KINDS = {"flight_offers", "hotel_availability", "fx_rate", "trip_budget"}


class DbOracle:
    """`Oracle` port impl: recomputes travel-pi ground truth via services.

    Bound to a single `Session` (like the services it wraps) — a caller in a
    request/test context passes its own request-scoped or fixture session;
    this class opens no session of its own.
    """

    def __init__(self, session: Session) -> None:
        self._flights = FlightService(session)
        self._hotels = HotelService(session)
        self._currency = CurrencyService(session)
        self._session = session

    def supports(self, kind: str) -> bool:
        """Whether this oracle can compute ground truth for *kind*."""
        return kind in _KINDS

    def lookup(self, kind: str, params: dict[str, Any]) -> Any:
        """Recompute ground truth for *kind* given *params*.

        :param kind: One of the kinds in `_KINDS`.
        :param params: Kind-specific lookup parameters (see each `_*` helper).
        :raises ValueError: If *kind* is unsupported.
        :raises Exception: Whatever the underlying service raises (e.g. a
            domain `NotFoundError` for an unknown trip/currency) — surfaced
            verbatim rather than swallowed, so a caller can diagnose it.
        """
        if kind == "flight_offers":
            return self._flight_offers(params)
        if kind == "hotel_availability":
            return self._hotel_availability(params)
        if kind == "fx_rate":
            return self._fx_rate(params)
        if kind == "trip_budget":
            return self._trip_budget(params)
        raise ValueError(
            f"DbOracle does not support kind {kind!r}; supported: {sorted(_KINDS)}"
        )

    def _flight_offers(self, params: dict[str, Any]) -> dict[str, Any]:
        """Cheapest/most expensive price + count for a seeded route+date."""
        flights = self._flights.generate_flights(
            params["origin"], params["destination"], params["departure_date"]
        )
        prices = [f.price for f in flights]
        return {
            "count": len(flights),
            "min_price": round(min(prices), 2),
            "max_price": round(max(prices), 2),
            "currency": "USD",
        }

    def _hotel_availability(self, params: dict[str, Any]) -> dict[str, Any]:
        """Nights, hotel/available counts, cheapest available total price."""
        nights, results = self._hotels.check_availability(
            params["city"],
            params["check_in"],
            params["check_out"],
            rooms=params.get("rooms", 1),
            adults=params.get("adults", 2),
            children=params.get("children", 0),
        )
        available = [r for r in results if r.available]
        return {
            "nights": nights,
            "hotel_count": len(results),
            "available_count": len(available),
            "min_total_price": (
                round(min(r.total_price for r in available), 2) if available else None
            ),
        }

    def _fx_rate(self, params: dict[str, Any]) -> dict[str, Any]:
        """The DB-backed FX rate + converted amount between two currencies."""
        result = self._currency.convert(
            params["from_code"], params["to_code"], amount=params.get("amount", 1.0)
        )
        return {"rate": result.rate, "converted": result.converted}

    def _trip_budget(self, params: dict[str, Any]) -> dict[str, Any]:
        """Per-category caps/spend rollup for a seeded trip_id.

        See the module docstring's CONSTRAINT — no golden calls this kind
        yet; it is exercised only by `tests/eval/test_db_oracle.py`, which
        seeds the trip it checks against.
        """
        trips = TripService(self._session, params["user_id"])
        budget = trips.get_trip_budget(params["trip_id"])
        return {
            "total_cap": budget.total_cap,
            "total_spent": budget.total_spent,
            "total_remaining": budget.total_remaining,
            "over_budget": budget.over_budget,
        }
