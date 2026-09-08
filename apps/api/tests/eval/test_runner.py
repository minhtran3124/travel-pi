"""Runner + CLI tests (agent-eval-pipeline task 3.1). Offline — a fake
AgentRunner and fake metrics, no network, no real LLM.
"""

from __future__ import annotations

import json

import evalkit.metrics  # noqa: F401 - registers flow_match/tools_expected/... for the DEFAULT_METRIC_NAMES test
import pytest
from evalkit import cli
from evalkit.registry import Taxonomy, register_metric
from evalkit.runner import DEFAULT_METRIC_NAMES, resolve_metric_names, run_eval
from evalkit.types import CheckResult, Golden, Trace

TAXONOMY = Taxonomy(
    capabilities=["flight_search", "hotels", "routing"],
    scenarios=["happy"],
    thresholds={"flight_search": 0.9, "hotels": 0.5, "routing": 0.5},
)


def _golden(**overrides) -> Golden:
    defaults = {
        "id": "case-001",
        "capability": "flight_search",
        "scenario": "happy",
        "language": "en",
        "suite": "smoke",
        "input": "hello",
    }
    defaults.update(overrides)
    return Golden(**defaults)


class _FakeAgentRunner:
    """`AgentRunner` port impl: canned replies, optional per-golden exception."""

    def __init__(self, raise_for: set[str] | None = None, reply: str = "ok"):
        self.raise_for = raise_for or set()
        self.reply = reply
        self.calls: list[str] = []

    def run(self, golden: Golden) -> Trace:
        self.calls.append(golden.id)
        if golden.id in self.raise_for:
            raise RuntimeError(f"boom-{golden.id}")
        return Trace(reply=self.reply, flow="concierge")


class _FakeDeterministicMetric:
    """A `Metric` with no `k` attribute — must run exactly once, never skipped."""

    def __init__(self, name: str, passed: bool = True):
        self.name = name
        self._passed = passed
        self.call_count = 0

    def evaluate(self, golden, trace, oracle=None) -> CheckResult:
        self.call_count += 1
        return CheckResult(name=self.name, passed=self._passed, detail="fake")


class _FakeJudgedMetric:
    """A `Metric` exposing a mutable `k` attribute — the judged-metric signal."""

    def __init__(self, name: str, k: int = 1):
        self.name = name
        self.k = k
        self.seen_k: list[int] = []

    def evaluate(self, golden, trace, oracle=None) -> CheckResult:
        self.seen_k.append(self.k)
        return CheckResult(name=self.name, passed=True, score=1.0, detail=f"k={self.k}")


class _FakeStore:
    """`DatasetStore` port impl over an in-memory golden list."""

    def __init__(self, goldens: list[Golden]):
        self._goldens = goldens
        self.load_calls: list[dict] = []

    def load(self, **filters):
        self.load_calls.append(filters)
        result = self._goldens
        for key, value in filters.items():
            if value is None:
                continue
            result = [g for g in result if getattr(g, key) == value]
        return list(result)

    def save(self, goldens):
        raise NotImplementedError


# --- metric selection --------------------------------------------------------


def test_golden_explicit_metrics_win_over_capability_default():
    register_metric(_FakeDeterministicMetric("explicit-only"))
    register_metric(_FakeDeterministicMetric("cap-default-not-run"))
    golden = _golden(metrics=["explicit-only"], capability="flight_search")

    assert resolve_metric_names(golden, {"flight_search": ["cap-default-not-run"]}) == [
        "explicit-only",
        "non_empty_reply",
    ]


def test_capability_default_used_when_golden_has_no_explicit_metrics():
    golden = _golden(metrics=None, capability="hotels")
    names = resolve_metric_names(golden, {"hotels": ["cap-default-metric"]})
    assert names == ["cap-default-metric", "non_empty_reply"]


def test_falls_back_to_generic_default_metric_names_for_unlisted_capability():
    golden = _golden(metrics=None, capability="routing")
    assert list(resolve_metric_names(golden, {})) == list(DEFAULT_METRIC_NAMES)


def test_explicit_empty_metrics_list_is_respected_not_defaulted():
    golden = _golden(metrics=[], capability="hotels")
    assert resolve_metric_names(golden, {"hotels": ["should-not-apply"]}) == []


# --- run_eval: selection end-to-end ------------------------------------------


def test_run_eval_runs_only_the_selected_metrics():
    m_explicit = _FakeDeterministicMetric("only-explicit")
    m_unused = _FakeDeterministicMetric("should-not-run")
    register_metric(m_explicit)
    register_metric(m_unused)
    golden = _golden(metrics=["only-explicit"], capability="flight_search")

    report = run_eval([golden], _FakeAgentRunner(), {}, TAXONOMY)

    names_ran = {c.name for c in report.per_case[0].checks}
    assert names_ran == {"only-explicit", "non_empty_reply"}  # always-on check
    assert m_unused.call_count == 0


# --- k-repeat: judged only ----------------------------------------------------


def test_repeat_applies_only_to_metrics_with_a_k_attribute():
    judged = _FakeJudgedMetric("fake-judged-repeat")
    deterministic = _FakeDeterministicMetric("fake-det-repeat")
    register_metric(judged)
    register_metric(deterministic)
    golden = _golden(metrics=["fake-judged-repeat", "fake-det-repeat"])

    run_eval([golden], _FakeAgentRunner(), {}, TAXONOMY, repeat=3)

    assert judged.seen_k == [3]
    assert deterministic.call_count == 1
    assert not hasattr(deterministic, "k")


def test_repeat_below_one_raises():
    with pytest.raises(ValueError, match="repeat must be >= 1"):
        run_eval([], _FakeAgentRunner(), {}, TAXONOMY, repeat=0)


# --- judge-skip: keyless smoke stays green -----------------------------------


def test_judged_metric_skipped_when_no_judge_key_and_recorded_in_run_meta():
    judged = _FakeJudgedMetric("fake-judged-skip")
    register_metric(judged)
    golden = _golden(metrics=["fake-judged-skip"])

    report = run_eval([golden], _FakeAgentRunner(), {}, TAXONOMY, judge_available=False)

    case = report.per_case[0]
    assert [c.name for c in case.checks] == ["non_empty_reply"], (
        "a skipped judged metric must be visibly absent (only the always-on check ran)"
    )
    assert judged.seen_k == [], "a skipped judged metric must never be invoked"
    assert report.run_meta["skipped_judged_metrics"] == ["fake-judged-skip"]


def test_judge_available_true_does_not_skip():
    judged = _FakeJudgedMetric("fake-judged-available")
    register_metric(judged)
    golden = _golden(metrics=["fake-judged-available"])

    report = run_eval([golden], _FakeAgentRunner(), {}, TAXONOMY, judge_available=True)

    assert judged.seen_k == [1]
    assert report.run_meta["skipped_judged_metrics"] == []


# --- agent-run failure: never crash, never drop ------------------------------


def test_agent_exception_becomes_failed_case_not_crash_not_dropped():
    runner = _FakeAgentRunner(raise_for={"bad-1"})
    goldens = [
        _golden(id="ok-1", metrics=[]),
        _golden(id="bad-1", metrics=[]),
        _golden(id="ok-2", metrics=[]),
    ]

    report = run_eval(goldens, runner, {}, TAXONOMY)

    assert [c.golden_id for c in report.per_case] == ["ok-1", "bad-1", "ok-2"]
    assert runner.calls == ["ok-1", "bad-1", "ok-2"], "must continue past the failure"
    bad_case = next(c for c in report.per_case if c.golden_id == "bad-1")
    assert bad_case.passed is False
    assert len(bad_case.checks) == 1
    assert bad_case.checks[0].name == "agent_run"
    assert "boom-bad-1" in bad_case.checks[0].detail


def test_unknown_metric_name_raises_keyerror():
    golden = _golden(metrics=["does-not-exist-anywhere"])
    with pytest.raises(KeyError):
        run_eval([golden], _FakeAgentRunner(), {}, TAXONOMY)


# --- CLI ----------------------------------------------------------------------


def test_cli_dry_run_lists_goldens_and_invokes_no_agent(capsys):
    runner = _FakeAgentRunner()
    goldens = [
        _golden(id="dry-1", capability="flight_search", metrics=["m1"]),
        _golden(id="dry-2", capability="hotels", metrics=["m2"]),
    ]
    store = _FakeStore(goldens)

    exit_code = cli.main(
        ["--suite", "smoke", "--dry-run"],
        dataset_store=store,
        agent_runner=runner,
        metrics={},
        taxonomy=TAXONOMY,
    )

    assert exit_code == 0
    assert runner.calls == [], "--dry-run must never invoke the agent"
    out = capsys.readouterr().out
    assert "dry-1" in out
    assert "dry-2" in out


def test_cli_passes_capability_and_language_filters_to_store():
    store = _FakeStore([])
    cli.main(
        ["--suite", "full", "--capability", "hotels", "--language", "vi", "--dry-run"],
        dataset_store=store,
        agent_runner=_FakeAgentRunner(),
        metrics={},
        taxonomy=TAXONOMY,
    )
    assert store.load_calls == [
        {"suite": "full", "capability": "hotels", "language": "vi"}
    ]


def test_cli_runs_writes_report_and_returns_threshold_exit_code(tmp_path):
    register_metric(_FakeDeterministicMetric("cli-fail-metric", passed=False))
    golden = _golden(id="cli-fail-1", metrics=["cli-fail-metric"], capability="hotels")
    store = _FakeStore([golden])
    out_path = tmp_path / "report.json"

    exit_code = cli.main(
        ["--suite", "smoke", "--out", str(out_path)],
        dataset_store=store,
        agent_runner=_FakeAgentRunner(),
        metrics={},
        taxonomy=TAXONOMY,
    )

    assert exit_code == 1, "hotels threshold is 0.5, a 0% pass rate must fail the gate"
    assert out_path.exists()
    saved = json.loads(out_path.read_text())
    assert saved["per_capability"]["hotels"]["passed"] == 0


def test_cli_repeat_flag_reaches_judged_metric_k():
    judged = _FakeJudgedMetric("cli-judged-repeat")
    register_metric(judged)
    golden = _golden(metrics=["cli-judged-repeat"], capability="flight_search")
    store = _FakeStore([golden])

    cli.main(
        ["--suite", "smoke", "--repeat", "5"],
        dataset_store=store,
        agent_runner=_FakeAgentRunner(),
        metrics={},
        taxonomy=TAXONOMY,
        judge_available=True,
    )

    assert judged.seen_k == [5]


def test_empty_reply_fails_even_when_the_golden_omits_non_empty_reply():
    """Reply-dependent metrics report not_applicable (passed) on an empty
    reply, so `non_empty_reply` is always on: an agent that says nothing must
    never score all-green just because the golden did not list that check."""
    golden = _golden(metrics=["flow_match"], expected_flow="concierge")
    report = run_eval([golden], _FakeAgentRunner(reply=""), {}, TAXONOMY)
    case = report.per_case[0]
    assert case.passed is False
    names = {check.name: check for check in case.checks}
    assert names["flow_match"].passed is True
    assert names["non_empty_reply"].passed is False
