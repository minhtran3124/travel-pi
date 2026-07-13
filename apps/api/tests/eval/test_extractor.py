"""Tests for `eval.adapters.extractor.llm_extract` — the production
`Extractor` wired into `OracleFactCheck` (agent-eval-pipeline follow-up
wiring task).

Offline: `get_fast_llm()` is monkeypatched to a `FakeLLM` (the repo's
deterministic test double, `app/clients/llm.py`) so no network/key is ever
needed. The wiring-bug test at the bottom is the one that matters most: it
pins each extraction schema's field names against `DbOracle.lookup()`'s
REAL return keys — a rename on either side must fail this test, not degrade
silently to "no claimed value found" in production.
"""

from __future__ import annotations

from app.clients.llm import FakeLLM
from eval.adapters.db_oracle import DbOracle
from eval.adapters.extractor import (
    _SCHEMAS,
    _FlightOffersClaim,
    llm_extract,
)


def _patch_llm(monkeypatch, structured_response):
    fake = FakeLLM(structured_responses=[structured_response])
    monkeypatch.setattr("eval.adapters.extractor.get_fast_llm", lambda: fake)
    return fake


# --- llm_extract: stated value / no value / unsupported kind / failure -----


def test_extracts_the_stated_price_from_a_flight_reply(monkeypatch):
    _patch_llm(monkeypatch, _FlightOffersClaim(min_price=123.0))

    result = llm_extract("The cheapest flight I found is $123.", "flight_offers", {})

    assert result == {"min_price": 123.0}


def test_returns_none_when_the_reply_states_no_price(monkeypatch):
    _patch_llm(monkeypatch, _FlightOffersClaim())  # every field null

    result = llm_extract(
        "I couldn't find any flights for that route.", "flight_offers", {}
    )

    assert result is None


def test_returns_none_for_an_unsupported_kind_without_calling_the_llm(monkeypatch):
    called = {"n": 0}

    def _boom():
        called["n"] += 1
        raise AssertionError(
            "get_fast_llm should not be called for an unsupported kind"
        )

    monkeypatch.setattr("eval.adapters.extractor.get_fast_llm", _boom)

    result = llm_extract("anything", "weather_forecast", {})

    assert result is None
    assert called["n"] == 0


def test_returns_none_when_extraction_raises(monkeypatch):
    class _BoomLLM:
        def with_structured_output(self, schema):
            class _Boom:
                def invoke(self, prompt):
                    raise RuntimeError("provider unavailable")

            return _Boom()

    monkeypatch.setattr("eval.adapters.extractor.get_fast_llm", lambda: _BoomLLM())

    result = llm_extract("The cheapest flight is $123.", "flight_offers", {})

    assert result is None


# --- the wiring-bug test: schema fields must exist in DbOracle's real keys -


def test_schema_field_names_line_up_with_dboracle_lookup_keys(seeded_session):
    """Every field an extraction schema can produce for `kind` must be a real
    key in `DbOracle.lookup(kind, ...)`'s output — otherwise `OracleFactCheck`
    silently treats a legitimate extracted claim as "no overlapping fields"
    (indistinguishable from a hallucination). This must fail if either side
    renames a field without updating the other.
    """
    oracle = DbOracle(seeded_session)

    cases: dict[str, dict] = {
        "flight_offers": {
            "origin": "SGN",
            "destination": "DAD",
            "departure_date": "2026-08-20",
        },
        "hotel_availability": {
            "city": "Hanoi",
            "check_in": "2026-08-10",
            "check_out": "2026-08-12",
        },
        "fx_rate": {"from_code": "USD", "to_code": "VND"},
    }

    for kind, params in cases.items():
        oracle_keys = set(oracle.lookup(kind, params).keys())
        schema_fields = set(_SCHEMAS[kind].model_fields.keys())
        assert schema_fields <= oracle_keys, (
            f"{kind}: extractor schema fields {schema_fields} are not all "
            f"present in DbOracle.lookup() keys {oracle_keys}"
        )

    # trip_budget needs a seeded trip (same pattern as test_db_oracle.py).
    from app.schemas.trip import TripBudgetSet, TripCreate
    from app.services.trip_service import TripService

    trips = TripService(seeded_session)
    trip = trips.create_trip(TripCreate(title="extractor wiring test trip"))
    trips.set_trip_budget(trip.id, TripBudgetSet(flights=1000.0, hotels=500.0))

    oracle_keys = set(oracle.lookup("trip_budget", {"trip_id": trip.id}).keys())
    schema_fields = set(_SCHEMAS["trip_budget"].model_fields.keys())
    assert schema_fields <= oracle_keys, (
        f"trip_budget: extractor schema fields {schema_fields} are not all "
        f"present in DbOracle.lookup() keys {oracle_keys}"
    )


def test_every_oracle_kind_has_an_extraction_schema():
    """`DbOracle` supports 4 kinds; the extractor must cover all of them, or
    a golden using an uncovered kind would always read as "not stated" —
    even before any DB/field-name check runs.
    """
    assert set(_SCHEMAS) == {
        "flight_offers",
        "hotel_availability",
        "fx_rate",
        "trip_budget",
    }
