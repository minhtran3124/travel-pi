"""Suite runner: drives every golden through the agent, scores it, and
aggregates the results into a Report (agent-eval-pipeline task 3.1).

`run_eval` is the one function the CLI/CI/tests all call. Metric SELECTION
follows one rule: a golden's own `Golden.metrics` list wins; when unset, the
per-capability default in the caller-supplied `metrics` mapping applies
(``metrics.get(golden.capability, DEFAULT_METRIC_NAMES)``) — a project picks
its own capability -> metric-name defaults by passing its own dict as this
argument, never by editing this module
(`specs/agent-eval-pipeline/design-portability.md`). Concrete `Metric`
instances are resolved by NAME from the process-global registry
(`evalkit.registry.get_metric`) — the same registry every metric module
populates on import via `@register_metric`; `run_eval` never takes metric
*instances* directly, so it stays agnostic to how a project configured them
(k, judge model, tool-arg schemas, ...).

Judge-variance control (``repeat=k``) and the keyless-judge skip are both
driven by ONE convention: a metric that supports repeat exposes a plain,
mutable ``k`` attribute — exactly what
`evalkit.metrics.judged.GEvalJudgedMetric` does; deterministic/trajectory
metrics never define ``k``. `run_eval` never imports the judged module or
checks `isinstance` — ``hasattr(metric, "k")`` is the entire "is this a
judged metric" signal, so this module stays agnostic to which optional
metric extras (`agentevals`, `deepeval`) are even installed.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any

from evalkit.ports import AgentRunner, Oracle
from evalkit.registry import Taxonomy, get_metric
from evalkit.report import build_report
from evalkit.types import CaseResult, CheckResult, Golden, Report

logger = logging.getLogger(__name__)

# Generic, domain-agnostic fallback used when a golden has no explicit
# `metrics` AND its capability has no entry in the caller-supplied default
# map. Deliberately deterministic-only (registered by core with no extras
# required) so this constant is always safely evaluable keyless.
DEFAULT_METRIC_NAMES: tuple[str, ...] = (
    "flow_match",
    "tools_expected",
    "non_empty_reply",
    "reply_language",
)


def resolve_metric_names(
    golden: Golden, default_metrics_by_capability: Mapping[str, Sequence[str]]
) -> Sequence[str]:
    """The metric names applicable to *golden*.

    ``golden.metrics`` wins when set (even an explicit empty list — an
    intentional "check nothing" opt-out, not a signal to fall back). Otherwise
    the caller's per-capability default, else `DEFAULT_METRIC_NAMES`.
    """
    if golden.metrics is not None:
        return golden.metrics
    return default_metrics_by_capability.get(golden.capability, DEFAULT_METRIC_NAMES)


def run_eval(
    goldens: Sequence[Golden],
    agent_runner: AgentRunner,
    metrics: Mapping[str, Sequence[str]],
    taxonomy: Taxonomy,
    oracle: Oracle | None = None,
    repeat: int = 1,
    *,
    judge_available: bool = True,
    run_meta: Mapping[str, Any] | None = None,
) -> Report:
    """Run every golden through *agent_runner*, score it, and build a Report.

    :param goldens: The cases to run (already filtered by suite/capability/...
        by the caller, e.g. via `DatasetStore.load`).
    :param agent_runner: Drives the agent for one golden -> Trace.
    :param metrics: Per-capability DEFAULT metric-NAME set (``{capability:
        [name, ...]}``) — consulted only when a golden has no explicit
        `Golden.metrics`. Project-supplied data; swap it to retarget defaults
        without touching this module.
    :param taxonomy: Supplies per-capability pass-rate thresholds to
        `evalkit.report.build_report`.
    :param oracle: Optional ground-truth port, threaded through to every
        metric's `evaluate()` call.
    :param repeat: k-repeat count applied ONLY to metrics exposing a mutable
        `k` attribute (the judged-metric convention) — deterministic/
        trajectory metrics run their single `evaluate()` call regardless.
    :param judge_available: When False, any selected metric with a `k`
        attribute is SKIPPED (loud log, absent from the case's checks, name
        recorded in the report's `run_meta["skipped_judged_metrics"]`) rather
        than invoked — this is what keeps a keyless smoke run green.
    :param run_meta: Extra caller-supplied metadata folded into the report's
        `run_meta` (e.g. suite/capability/language filters).
    :return: The aggregated `Report`.
    :raises ValueError: if `repeat` < 1.
    :raises KeyError: if a golden requests a metric name with nothing
        registered under it — a dataset/config bug; fails loud rather than
        silently dropping the check.
    """
    if repeat < 1:
        raise ValueError(f"repeat must be >= 1, got {repeat}")

    case_results: list[CaseResult] = []
    skipped_judged: set[str] = set()

    for golden in goldens:
        try:
            trace = agent_runner.run(golden)
        except Exception as exc:
            # A golden's own failure must never crash the whole run, and must
            # never be silently dropped (a dropped case inflates pass rates).
            logger.error("[EVALKIT] agent run raised for golden=%s: %s", golden.id, exc)
            case_results.append(
                CaseResult(
                    golden_id=golden.id,
                    capability=golden.capability,
                    scenario=golden.scenario,
                    suite=golden.suite,
                    checks=[
                        CheckResult(
                            name="agent_run",
                            passed=False,
                            detail=f"agent run raised {type(exc).__name__}: {exc}",
                        )
                    ],
                    passed=False,
                )
            )
            continue

        checks: list[CheckResult] = []
        for name in resolve_metric_names(golden, metrics):
            metric = get_metric(name)
            if hasattr(metric, "k"):
                if not judge_available:
                    logger.warning(
                        "[EVALKIT] SKIP judged metric=%s golden=%s — "
                        "no judge key configured",
                        name,
                        golden.id,
                    )
                    skipped_judged.add(name)
                    continue
                metric.k = repeat
            checks.append(metric.evaluate(golden, trace, oracle))

        case_results.append(
            CaseResult(
                golden_id=golden.id,
                capability=golden.capability,
                scenario=golden.scenario,
                suite=golden.suite,
                checks=checks,
                # A case with no checks at all (every applicable metric was a
                # skipped judged metric) has nothing that failed — vacuously
                # passed, same convention as a metric's own "not_applicable".
                passed=all(check.passed for check in checks) if checks else True,
            )
        )

    merged_run_meta = dict(run_meta or {})
    merged_run_meta["repeat"] = repeat
    merged_run_meta["judge_available"] = judge_available
    merged_run_meta["skipped_judged_metrics"] = sorted(skipped_judged)

    return build_report(case_results, taxonomy, run_meta=merged_run_meta)
