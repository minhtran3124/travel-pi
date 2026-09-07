"""Tests for `DbOracle` (adapter) and `OracleFactCheck` (metric) —
agent-eval-pipeline task 3.2.

Offline: runs against the repo's own seeded temp-SQLite fixture
(`tests/conftest.py::seeded_session`) — no network, no LLM. The extractor
injected into `OracleFactCheck` is a hand-written stub standing in for the
production LLM extraction call (task 3.1 wires the real one); see the
`Extractor` docstring in `evalkit/metrics/oracle.py`.
"""

from __future__ import annotations

import pytest
from eval.adapters.db_oracle import DbOracle
from evalkit.metrics.oracle import ExtractionError, OracleFactCheck
from evalkit.registry import get_metric
from evalkit.types import Golden, Trace

_FLIGHT_PARAMS = {
    "origin": "SGN",
    "destination": "DAD",
    "departure_date": "2026-08-20",
}  # same route+date as flight_search-happy-vi-01 in eval/datasets/flight_search.json


def _golden(**overrides):
    defaults = {
        "id": "g-1",
        "capability": "flight_search",
        "scenario": "happy",
        "language": "en",
        "suite": "smoke",
        "input": "irrelevant for these tests",
    }
    defaults.update(overrides)
    return Golden(**defaults)


# --- DbOracle: recomputes real seeded values, via the real services --------


def test_flight_offers_recomputes_the_real_seeded_price_range(seeded_session):
    from app.services.flight_service import FlightService

    oracle = DbOracle(seeded_session)
    assert oracle.supports("flight_offers")

    result = oracle.lookup("flight_offers", _FLIGHT_PARAMS)

    # Cross-checked directly against the same generator search_flights calls
    # — proves this is a recompute through the real service, not a hardcoded
    # value or a hand-rolled re-derivation of the seed math.
    flights = FlightService(seeded_session).generate_flights(
        _FLIGHT_PARAMS["origin"],
        _FLIGHT_PARAMS["destination"],
        _FLIGHT_PARAMS["departure_date"],
    )
    prices = [f.price for f in flights]

    assert result["count"] == len(flights) == 5
    assert result["min_price"] == round(min(prices), 2)
    assert result["max_price"] == round(max(prices), 2)
    assert result["min_price"] <= result["max_price"]


def test_hotel_availability_recomputes_real_seeded_availability(seeded_session):
    oracle = DbOracle(seeded_session)
    assert oracle.supports("hotel_availability")

    result = oracle.lookup(
        "hotel_availability",
        {"city": "Hanoi", "check_in": "2026-08-10", "check_out": "2026-08-12"},
    )

    assert result["nights"] == 2
    assert result["available_count"] <= result["hotel_count"]
    if result["available_count"] > 0:
        assert result["min_total_price"] is not None
        assert result["min_total_price"] > 0


def test_fx_rate_recomputes_from_the_seeded_fx_table(seeded_session):
    oracle = DbOracle(seeded_session)
    assert oracle.supports("fx_rate")

    result = oracle.lookup("fx_rate", {"from_code": "USD", "to_code": "VND"})

    assert result["rate"] > 0
    assert result["converted"] == round(result["rate"], 2)


def test_trip_budget_resolves_against_a_trip_seeded_by_this_test(seeded_session):
    """No golden declares a `trip_budget` oracle_check yet — the single-shot
    harness has no live trip_id (see db_oracle.py's module docstring). This
    test is the current only caller of that kind, and seeds its own trip.
    """
    from app.schemas.trip import TripBudgetSet, TripCreate
    from app.services.trip_service import TripService

    trips = TripService(seeded_session, "eval-oracle-owner")
    trip = trips.create_trip(TripCreate(title="Oracle test trip"))
    trips.set_trip_budget(trip.id, TripBudgetSet(flights=1000.0, hotels=500.0))

    oracle = DbOracle(seeded_session)
    assert oracle.supports("trip_budget")

    result = oracle.lookup(
        "trip_budget", {"trip_id": trip.id, "user_id": "eval-oracle-owner"}
    )

    assert result["total_cap"] == 1500.0
    assert result["total_spent"] == 0.0
    assert result["over_budget"] is False


def test_unsupported_kind_is_not_supported(seeded_session):
    oracle = DbOracle(seeded_session)
    assert not oracle.supports("weather_forecast")


def test_lookup_raises_on_unsupported_kind(seeded_session):
    oracle = DbOracle(seeded_session)
    with pytest.raises(ValueError, match="weather_forecast"):
        oracle.lookup("weather_forecast", {})


# --- OracleFactCheck: extraction-then-compare, CODE decides ----------------


def test_passes_when_extractor_reports_the_oracle_value(seeded_session):
    oracle = DbOracle(seeded_session)
    expected = oracle.lookup("flight_offers", _FLIGHT_PARAMS)
    golden = _golden(
        oracle_checks=[{"kind": "flight_offers", "params": _FLIGHT_PARAMS}]
    )
    trace = Trace(reply=f"The cheapest flight is ${expected['min_price']}.")

    def stub_extractor(reply, kind, params):
        return {"min_price": expected["min_price"]}

    metric = OracleFactCheck(extractor=stub_extractor)
    result = metric.evaluate(golden, trace, oracle)

    assert result.passed
    assert "OK" in result.detail


def test_fails_and_catches_a_hallucinated_wrong_price(seeded_session):
    """The test that proves the oracle can actually catch a hallucination:
    the extractor reports a price nowhere close to the real seeded one.
    """
    oracle = DbOracle(seeded_session)
    expected = oracle.lookup("flight_offers", _FLIGHT_PARAMS)
    golden = _golden(
        oracle_checks=[{"kind": "flight_offers", "params": _FLIGHT_PARAMS}]
    )
    wrong_price = expected["min_price"] + 500.0  # nowhere near the real seeded value
    trace = Trace(reply=f"The cheapest flight is ${wrong_price}.")

    def lying_extractor(reply, kind, params):
        return {"min_price": wrong_price}

    metric = OracleFactCheck(extractor=lying_extractor)
    result = metric.evaluate(golden, trace, oracle)

    assert not result.passed
    assert "MISMATCH" in result.detail
    assert str(expected["min_price"]) in result.detail
    assert str(wrong_price) in result.detail


def test_unsupported_kind_is_not_applicable_never_a_pass_by_accident(seeded_session):
    oracle = DbOracle(seeded_session)
    golden = _golden(
        oracle_checks=[{"kind": "weather_forecast", "params": {"city": "Hanoi"}}]
    )
    trace = Trace(reply="It'll be sunny.")

    metric = OracleFactCheck(extractor=lambda reply, kind, params: {"temp": 30})
    result = metric.evaluate(golden, trace, oracle)

    assert result.passed
    assert "not_applicable" in result.detail


def test_a_reply_claiming_nothing_fails_loud_not_a_crash(seeded_session):
    """`None` from the extractor means the AGENT stated no checkable value."""
    oracle = DbOracle(seeded_session)
    golden = _golden(
        oracle_checks=[{"kind": "flight_offers", "params": _FLIGHT_PARAMS}]
    )
    trace = Trace(reply="I found some flights but didn't mention any prices.")

    def empty_extractor(reply, kind, params):
        return None

    metric = OracleFactCheck(extractor=empty_extractor)
    result = metric.evaluate(golden, trace, oracle)

    assert not result.passed
    assert "no claimed value" in result.detail


def test_a_broken_extractor_aborts_the_run_instead_of_failing_the_agent(seeded_session):
    """A broken extractor (bad model/key) must NOT be recorded as an agent
    failure: its `ExtractionError` propagates so the run stops and gets fixed,
    rather than producing a report of failures the agent never caused.
    """
    oracle = DbOracle(seeded_session)
    golden = _golden(
        oracle_checks=[{"kind": "flight_offers", "params": _FLIGHT_PARAMS}]
    )
    trace = Trace(reply="The cheapest flight is $88.")

    def broken_extractor(reply, kind, params):
        raise ExtractionError("403 does not have access to model gpt-5-mini")

    metric = OracleFactCheck(extractor=broken_extractor)

    with pytest.raises(ExtractionError, match="403"):
        metric.evaluate(golden, trace, oracle)


def test_oracle_lookup_failure_fails_loud_not_a_crash(seeded_session):
    oracle = DbOracle(seeded_session)
    golden = _golden(
        oracle_checks=[
            {"kind": "trip_budget", "params": {"trip_id": "not-a-real-trip"}}
        ]
    )
    trace = Trace(reply="You have $200 left in your budget.")

    metric = OracleFactCheck(extractor=lambda r, k, p: {"total_spent": 200.0})
    result = metric.evaluate(golden, trace, oracle)

    assert not result.passed
    assert "oracle lookup failed" in result.detail


def test_no_oracle_checks_is_not_applicable(seeded_session):
    oracle = DbOracle(seeded_session)
    golden = _golden(oracle_checks=None)
    trace = Trace(reply="anything")

    metric = OracleFactCheck(extractor=lambda r, k, p: {})
    result = metric.evaluate(golden, trace, oracle)

    assert result.passed
    assert "not_applicable" in result.detail


def test_no_oracle_configured_is_not_applicable():
    golden = _golden(
        oracle_checks=[{"kind": "flight_offers", "params": _FLIGHT_PARAMS}]
    )
    trace = Trace(reply="anything")

    metric = OracleFactCheck(extractor=lambda r, k, p: {"min_price": 1.0})
    result = metric.evaluate(golden, trace, oracle=None)

    assert result.passed
    assert "not_applicable" in result.detail


def test_default_registered_metric_has_no_extractor_is_not_applicable(seeded_session):
    """The metric registered at import time (no extractor injected yet) must
    never silently pass a real oracle_check as if it were checked.
    """
    oracle = DbOracle(seeded_session)
    metric = get_metric("oracle_fact_check")
    golden = _golden(
        oracle_checks=[{"kind": "flight_offers", "params": _FLIGHT_PARAMS}]
    )
    trace = Trace(reply="whatever")

    result = metric.evaluate(golden, trace, oracle)

    assert result.passed
    assert "not_applicable" in result.detail
