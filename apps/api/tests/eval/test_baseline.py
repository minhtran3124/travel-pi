"""Report/baseline aggregation + regression gate (agent-eval-pipeline task 1.3)."""

from __future__ import annotations

import pytest
from evalkit.baseline import JsonBaselineStore, compare
from evalkit.registry import Taxonomy
from evalkit.report import build_report, load_report, report_exit_code, save_report
from evalkit.types import CaseResult, CheckResult

TAXONOMY = Taxonomy(
    capabilities=["flight_search", "hotels", "booking"],
    scenarios=["happy", "ambiguous"],
    thresholds={"flight_search": 0.9, "hotels": 0.8},
)


def _case(golden_id: str, capability: str, passed: bool) -> CaseResult:
    return CaseResult(
        golden_id=golden_id,
        capability=capability,
        scenario="happy",
        suite="smoke",
        checks=[CheckResult(name="flow_match", passed=passed)],
        passed=passed,
    )


def _clean_flight_search_cases() -> list[CaseResult]:
    """10 cases, 9 passed -> pass_rate 0.9, meets the 0.9 threshold."""
    cases = [
        _case(f"flight_search-happy-{i:03d}", "flight_search", True) for i in range(9)
    ]
    cases.append(_case("flight_search-happy-009", "flight_search", False))
    return cases


# --- build_report -----------------------------------------------------------


def test_build_report_aggregates_binary_pass_rate_per_capability():
    cases = _clean_flight_search_cases()
    report = build_report(cases, TAXONOMY, run_meta={"suite": "smoke"})

    stats = report.per_capability["flight_search"]
    assert stats == {
        "passed": 9,
        "total": 10,
        "pass_rate": 0.9,
        "threshold": 0.9,
        "meets_threshold": True,
    }
    assert report.schema_version == "1.0"
    assert report.run_meta["suite"] == "smoke"
    assert report.run_meta["summary"]["total_cases"] == 10
    assert report.run_meta["summary"]["total_passed"] == 9
    assert report.run_meta["summary"]["capabilities_below_threshold"] == []


def test_build_report_flags_capability_below_threshold():
    cases = [_case("hotels-happy-000", "hotels", False)]
    report = build_report(cases, TAXONOMY)

    assert report.per_capability["hotels"]["meets_threshold"] is False
    assert report.run_meta["summary"]["capabilities_below_threshold"] == ["hotels"]
    assert report_exit_code(report) == 1


def test_build_report_exit_code_zero_when_all_capabilities_meet_threshold():
    report = build_report(_clean_flight_search_cases(), TAXONOMY)
    assert report_exit_code(report) == 0


def test_build_report_empty_case_list_does_not_crash():
    report = build_report([], TAXONOMY)
    assert report.per_capability == {}
    assert report.run_meta["summary"]["total_cases"] == 0
    assert report.run_meta["summary"]["overall_pass_rate"] == 0.0
    assert report_exit_code(report) == 0


def test_report_json_round_trips(tmp_path):
    report = build_report(
        _clean_flight_search_cases(), TAXONOMY, run_meta={"suite": "smoke"}
    )
    path = tmp_path / "report.json"

    save_report(report, path)
    restored = load_report(path)

    assert restored == report


def test_json_baseline_store_save_and_load(tmp_path):
    report = build_report(_clean_flight_search_cases(), TAXONOMY)
    store = JsonBaselineStore()
    path = str(tmp_path / "baseline.json")

    store.save(report, path)
    restored = store.load(path)

    assert restored == report


# --- compare / regression gate ----------------------------------------------


def test_compare_regressed_run_exits_nonzero():
    baseline = build_report(_clean_flight_search_cases(), TAXONOMY)
    # regressed run: only 5/10 pass -> well below baseline 0.9 - tolerance
    regressed_cases = [
        _case(f"flight_search-happy-{i:03d}", "flight_search", i < 5) for i in range(10)
    ]
    regressed = build_report(regressed_cases, TAXONOMY)

    diff = compare(regressed, baseline, tolerance=0.05)

    assert diff.per_capability["flight_search"].regressed is True
    assert diff.exit_code() == 1
    assert "flight_search-happy-005" in diff.regressions


def test_compare_improved_run_exits_zero():
    baseline_cases = [
        _case(f"hotels-happy-{i:03d}", "hotels", i < 8) for i in range(10)
    ]
    baseline = build_report(baseline_cases, TAXONOMY)
    # improved: 10/10 pass now
    improved_cases = [_case(f"hotels-happy-{i:03d}", "hotels", True) for i in range(10)]
    improved = build_report(improved_cases, TAXONOMY)

    diff = compare(improved, baseline, tolerance=0.05)

    assert diff.per_capability["hotels"].regressed is False
    assert diff.exit_code() == 0
    assert diff.fixes  # the 2 previously-failing cases flipped to pass
    assert not diff.regressions


def test_compare_identical_run_exits_zero():
    cases = _clean_flight_search_cases()
    baseline = build_report(cases, TAXONOMY)
    current = build_report(cases, TAXONOMY)

    diff = compare(current, baseline, tolerance=0.05)

    assert diff.exit_code() == 0
    assert diff.per_capability["flight_search"].delta == 0.0
    assert not diff.regressions
    assert not diff.fixes


def test_compare_within_tolerance_dip_exits_zero():
    # baseline 10/10; current 10/10 minus one unrelated case removed keeps a
    # clean flip-free small dip within tolerance (delta = -0.1 dip case below)
    baseline_cases = [_case(f"hotels-happy-{i:03d}", "hotels", True) for i in range(20)]
    baseline = build_report(baseline_cases, TAXONOMY)
    # one case flips pass -> fail out of 20 => delta = -0.05, within tolerance=0.10
    dipped_cases = [_case(f"hotels-happy-{i:03d}", "hotels", i != 0) for i in range(20)]
    dipped = build_report(dipped_cases, TAXONOMY)

    diff = compare(dipped, baseline, tolerance=0.10)

    assert diff.per_capability["hotels"].delta == pytest.approx(-0.05)
    assert diff.per_capability["hotels"].regressed is False
    # rule 2 (masked flip) still fires: a real pass->fail flip happened in a
    # capability whose rate dropped (delta < 0), even though within tolerance
    assert diff.exit_code() == 1
    assert "hotels-happy-000" in diff.regressions


def test_compare_new_capability_does_not_crash_or_gate():
    baseline = build_report(
        [_case("flight_search-happy-000", "flight_search", True)], TAXONOMY
    )
    # current run adds a brand-new capability absent from the baseline
    current_cases = [
        _case("flight_search-happy-000", "flight_search", True),
        _case("booking-happy-000", "booking", False),
    ]
    current = build_report(current_cases, TAXONOMY)

    diff = compare(current, baseline, tolerance=0.05)

    assert diff.new_capabilities == ["booking"]
    booking_diff = diff.per_capability["booking"]
    assert booking_diff.is_new is True
    assert booking_diff.baseline_pass_rate is None
    assert booking_diff.delta is None
    assert booking_diff.regressed is False
    # a failing case in a brand-new capability never trips the gate
    assert diff.exit_code() == 0


def test_render_table_is_a_readable_string():
    baseline = build_report(_clean_flight_search_cases(), TAXONOMY)
    diff = compare(baseline, baseline, tolerance=0.05)

    from evalkit.baseline import render_table

    table = render_table(diff)

    assert isinstance(table, str)
    assert "flight_search" in table
    assert "exit_code=0" in table
