"""Golden/Trace/Report round-trip + validation (agent-eval-pipeline task 1.1)."""

from __future__ import annotations

import pytest
from evalkit.registry import Taxonomy
from evalkit.types import (
    CaseResult,
    CheckResult,
    Golden,
    Report,
    ToolCall,
    Trace,
)
from pydantic import ValidationError


def test_golden_single_turn_round_trip():
    golden = Golden(
        id="flight_search-happy-001",
        capability="flight_search",
        scenario="happy",
        language="en",
        suite="smoke",
        input="Find me a flight from Hanoi to Da Nang next Friday",
        expected_flow="concierge",
        expected_tools=["search_flights"],
    )
    restored = Golden.model_validate_json(golden.model_dump_json())
    assert restored == golden


def test_golden_multi_turn_round_trip():
    golden = Golden(
        id="booking-multi_turn-001",
        capability="booking",
        scenario="multi_turn",
        language="vi",
        suite="full",
        turns=["Tôi muốn đặt khách sạn ở Đà Lạt", "3 đêm, 2 người lớn"],
    )
    restored = Golden.model_validate_json(golden.model_dump_json())
    assert restored == golden
    assert restored.input is None
    assert restored.turns == golden.turns


@pytest.mark.parametrize(
    "kwargs",
    [
        # neither input nor turns
        {},
        # both input and turns
        {"input": "hi", "turns": ["hi"]},
    ],
)
def test_golden_rejects_input_turns_not_exactly_one(kwargs):
    with pytest.raises(ValidationError):
        Golden(
            id="bad-case",
            capability="flight_search",
            scenario="happy",
            language="en",
            suite="smoke",
            **kwargs,
        )


def test_trace_round_trip():
    trace = Trace(
        reply="Here are 3 flights.",
        tool_calls=[
            ToolCall(
                name="search_flights",
                args={"origin": "HAN", "destination": "DAD"},
                output={"count": 3},
            )
        ],
        flow="concierge",
        messages=[{"type": "human", "content": "Find me a flight"}],
        meta={"thread_id": "eval-1"},
    )
    restored = Trace.model_validate_json(trace.model_dump_json())
    assert restored == trace


def test_report_round_trip():
    case = CaseResult(
        golden_id="flight_search-happy-001",
        capability="flight_search",
        scenario="happy",
        suite="smoke",
        checks=[CheckResult(name="flow_match", passed=True, score=1.0)],
        passed=True,
    )
    report = Report(
        schema_version="1",
        run_meta={"suite": "smoke"},
        per_case=[case],
        per_capability={"flight_search": {"pass_rate": 1.0, "total": 1, "passed": 1}},
    )
    restored = Report.model_validate_json(report.model_dump_json())
    assert restored == report


def test_taxonomy_rejects_unknown_capability():
    taxonomy = Taxonomy(
        capabilities=["flight_search", "hotels"],
        scenarios=["happy", "ambiguous"],
        thresholds={"flight_search": 0.9},
    )
    golden = Golden(
        id="unknown-cap-001",
        capability="not_a_real_capability",
        scenario="happy",
        language="en",
        suite="smoke",
        input="anything",
    )
    with pytest.raises(ValueError, match="unknown capability"):
        taxonomy.validate_golden(golden)


def test_taxonomy_accepts_known_capability_and_scenario():
    taxonomy = Taxonomy(
        capabilities=["flight_search", "hotels"],
        scenarios=["happy", "ambiguous"],
    )
    golden = Golden(
        id="known-cap-001",
        capability="hotels",
        scenario="ambiguous",
        language="en",
        suite="smoke",
        input="anything",
    )
    taxonomy.validate_golden(golden)  # must not raise
    assert taxonomy.threshold_for("hotels") == 1.0  # no override -> default
