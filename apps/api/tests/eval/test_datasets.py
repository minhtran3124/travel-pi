"""Tests for `JsonDatasetStore` and the restructured capability × scenario
golden matrix (agent-eval-pipeline task 2.4).

`TAXONOMY` below is a **test-local stand-in** for the real project taxonomy
that `eval/adapters/config.py` (task 2.1, built independently this same wave)
is expected to supply at runtime — it must declare the same 10 capability
strings used as `eval/datasets/*.json` filenames (`flight_search`, `hotels`,
`booking`, `budget`, `journal`, `memory`, `language`, `dates`, `errors`,
`routing`; the last is not part of the PLAN.md §4 nine-capability list but is
explicitly named in task 2.4's file list, closing the MIN-65-flagged
"routing.json has no multi-intent cases" gap) or `JsonDatasetStore` will
reject every case in that file as an unknown capability.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from evalkit.dataset import JsonDatasetStore
from evalkit.registry import Taxonomy
from evalkit.types import Golden

REAL_DATASET_DIR = Path(__file__).resolve().parents[2] / "eval" / "datasets"

CAPABILITIES = [
    "flight_search",
    "hotels",
    "booking",
    "budget",
    "journal",
    "memory",
    "language",
    "dates",
    "errors",
    "routing",
    "suggestions",
]
SCENARIOS = ["happy", "ambiguous", "multi_turn", "tool_failure", "adversarial"]

TAXONOMY = Taxonomy(capabilities=CAPABILITIES, scenarios=SCENARIOS)


def _real_store() -> JsonDatasetStore:
    return JsonDatasetStore(REAL_DATASET_DIR, TAXONOMY)


def test_real_dataset_directory_loads_without_error():
    store = _real_store()
    assert len(store.load()) > 0


def test_total_case_count_at_least_60():
    assert len(_real_store().load()) == 113


def test_journal_list_trips_goldens_declare_tools_expected():
    """SC-8 (gh-166): a golden's `expected_tools` is inert unless the golden
    also declares `tools_expected` — goldens declare their metrics explicitly
    and `DEFAULT_METRICS_BY_CAPABILITY` is empty, so a check absent from the
    list never runs.
    """
    by_id = {case.id: case for case in _real_store().load(capability="journal")}
    for case_id in ("journal-ambiguous-vi-01", "journal-happy-en-02"):
        case = by_id.get(case_id)
        assert case is not None, f"golden {case_id!r} is missing"
        assert case.expected_tools == ["list_trips"]
        assert "tools_expected" in (case.metrics or []), (
            f"golden {case_id!r} declares expected_tools but not the "
            "'tools_expected' metric — the expectation would never be checked"
        )


def test_every_taxonomy_capability_has_at_least_one_case():
    store = _real_store()
    for capability in CAPABILITIES:
        cases = store.load(capability=capability)
        assert cases, f"capability {capability!r} has zero goldens"


def test_smoke_suite_between_15_and_20_cases():
    count = len(_real_store().load(suite="smoke"))
    assert 15 <= count <= 20, f"expected 15-20 smoke cases, got {count}"


def test_smoke_suite_never_declares_a_judged_metric():
    """The keyless smoke suite must be scoreable with no judge — a smoke
    golden that opts into a G-Eval rubric would silently need a real key.
    """
    judged_metrics = {
        "response_language",
        "search_vs_booking",
        "no_hallucination",
        "format_quality",
        "memory_recall",
        "suggestion_relevance",
        "ask_coverage",
    }
    for case in _real_store().load(suite="smoke"):
        declared = set(case.metrics or [])
        assert not (declared & judged_metrics), (
            f"smoke golden {case.id!r} declares judged metric(s) "
            f"{declared & judged_metrics}"
        )


def test_suggestions_capability_has_ten_full_suite_cases():
    cases = _real_store().load(capability="suggestions")
    assert len(cases) == 10
    for case in cases:
        assert case.suite == "full"


def test_multi_intent_goldens_declare_tasks_expected():
    """Multi-domain-phrased routing goldens (`routing-multi-*`) are re-derived
    from supervisor v10 (brief-2.1 Evidence/Inference row), not copied from
    the legacy `multi_intent.json`. v10 fans out to two sub-agents only when
    the phrasing spans two genuinely distinct domains (budget+concierge,
    planner+concierge) — those declare `expected_tasks` (>=2 entries) and the
    `tasks_expected` metric, with no `expected_flow`. Phrasings that mention
    multiple topics but resolve to one flow (planner owns flights+weather)
    keep `expected_flow`/`flow_match` and no `expected_tasks`, even though
    they're still id-prefixed `routing-multi-` for the phrasing shape.
    """
    store = _real_store()
    multi_intent_cases = [
        case
        for case in store.load(capability="routing")
        if case.id.startswith("routing-multi-")
    ]
    assert multi_intent_cases
    for case in multi_intent_cases:
        if case.expected_tasks is not None:
            assert len(case.expected_tasks) >= 2
            assert "tasks_expected" in (case.metrics or [])
            assert case.expected_flow is None
        else:
            assert case.expected_flow is not None
            assert "flow_match" in (case.metrics or [])


def test_filter_by_language_returns_only_that_language():
    store = _real_store()
    for case in store.load(language="vi"):
        assert case.language == "vi"
    for case in store.load(language="en"):
        assert case.language == "en"
    assert store.load(language="vi") and store.load(language="en")


def test_filter_by_scenario_returns_only_that_scenario():
    store = _real_store()
    for case in store.load(scenario="multi_turn"):
        assert case.scenario == "multi_turn"
        assert case.turns is not None and case.input is None


def test_filters_combine_with_and_semantics():
    store = _real_store()
    cases = store.load(capability="hotels", scenario="happy", language="vi")
    assert cases
    for case in cases:
        assert case.capability == "hotels"
        assert case.scenario == "happy"
        assert case.language == "vi"


def test_load_rejects_unsupported_filter_key():
    with pytest.raises(ValueError, match="unsupported filter"):
        _real_store().load(nope="x")


def test_every_case_id_is_globally_unique_in_the_real_dataset():
    store = _real_store()
    ids = [case.id for case in store.load()]
    assert len(ids) == len(set(ids))


def test_duplicate_id_across_files_raises(tmp_path):
    _write(tmp_path, "a.json", [_case("dup-id", "flight_search", "happy")])
    _write(tmp_path, "b.json", [_case("dup-id", "hotels", "happy")])
    with pytest.raises(ValueError, match="duplicate golden id"):
        JsonDatasetStore(tmp_path, TAXONOMY)


def test_unknown_capability_raises_naming_file_and_case(tmp_path):
    _write(tmp_path, "bad.json", [_case("bad-01", "not_a_capability", "happy")])
    with pytest.raises(ValueError, match="bad.json.*bad-01.*not_a_capability"):
        JsonDatasetStore(tmp_path, TAXONOMY)


def test_unknown_scenario_raises_naming_file_and_case(tmp_path):
    _write(tmp_path, "bad.json", [_case("bad-01", "flight_search", "not_a_scenario")])
    with pytest.raises(ValueError, match="bad.json.*bad-01.*not_a_scenario"):
        JsonDatasetStore(tmp_path, TAXONOMY)


def test_case_missing_both_input_and_turns_raises(tmp_path):
    bad = _case("bad-01", "flight_search", "happy")
    del bad["input"]
    _write(tmp_path, "bad.json", [bad])
    with pytest.raises(ValueError, match="invalid golden"):
        JsonDatasetStore(tmp_path, TAXONOMY)


def test_non_list_file_raises(tmp_path):
    (tmp_path / "bad.json").write_text('{"not": "a list"}', encoding="utf-8")
    with pytest.raises(ValueError, match="expected a JSON list"):
        JsonDatasetStore(tmp_path, TAXONOMY)


def test_non_dict_element_raises(tmp_path):
    (tmp_path / "bad.json").write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ValueError, match="expected a JSON object"):
        JsonDatasetStore(tmp_path, TAXONOMY)


def test_unknown_metric_raises_naming_file_case_and_metric(tmp_path):
    case = _case("bad-01", "flight_search", "happy")
    case["metrics"] = ["flow_match", "not_a_real_metric"]
    _write(tmp_path, "bad.json", [case])
    with pytest.raises(ValueError, match="bad.json.*bad-01.*not_a_real_metric"):
        JsonDatasetStore(tmp_path, TAXONOMY, known_metrics={"flow_match"})


def test_known_metrics_none_skips_metric_validation(tmp_path):
    """Default (`known_metrics=None`) never checks `metrics` — the store
    stays importable/usable with zero coupling to `evalkit.metrics`."""
    case = _case("ok-01", "flight_search", "happy")
    case["metrics"] = ["totally_made_up"]
    _write(tmp_path, "ok.json", [case])
    store = JsonDatasetStore(tmp_path, TAXONOMY)
    assert len(store.load()) == 1


def test_real_dataset_metrics_are_all_registered():
    """Regression: every real golden's `metrics` entries must resolve
    against the real evalkit registry, or `python -m eval --suite full`
    dies mid-flight with a `KeyError` after the judged metrics start
    running (the bug this test guards against)."""
    import evalkit.metrics  # noqa: F401 - populate the registry
    from evalkit.registry import list_metrics

    store = JsonDatasetStore(
        REAL_DATASET_DIR, TAXONOMY, known_metrics=set(list_metrics())
    )
    assert len(store.load()) > 0


def test_hitl_accepts_approve_and_reject():
    approve = Golden(
        **{**_case("hitl-approve", "flight_search", "happy"), "hitl": "approve"}
    )
    reject = Golden(
        **{**_case("hitl-reject", "flight_search", "happy"), "hitl": "reject"}
    )
    assert approve.hitl == "approve"
    assert reject.hitl == "reject"


def test_hitl_rejects_unknown_value(tmp_path):
    case = _case("bad-01", "flight_search", "happy")
    case["hitl"] = "aprove"
    _write(tmp_path, "bad.json", [case])
    with pytest.raises(ValueError, match="bad.json.*bad-01"):
        JsonDatasetStore(tmp_path, TAXONOMY)


def test_save_round_trips_through_the_store(tmp_path):
    store = JsonDatasetStore(tmp_path, TAXONOMY)
    assert store.load() == []
    golden = Golden.model_validate(_case("rt-01", "flight_search", "happy"))
    store.save([golden])
    reloaded = JsonDatasetStore(tmp_path, TAXONOMY)
    assert [g.id for g in reloaded.load()] == ["rt-01"]
    assert (tmp_path / "flight_search.json").exists()


def _case(case_id: str, capability: str, scenario: str) -> dict:
    return {
        "id": case_id,
        "capability": capability,
        "scenario": scenario,
        "language": "en",
        "suite": "full",
        "input": "hello",
    }


def _write(directory: Path, name: str, cases: list[dict]) -> None:
    import json

    (directory / name).write_text(json.dumps(cases), encoding="utf-8")
