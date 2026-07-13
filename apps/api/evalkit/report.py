"""Report: the stable, versioned aggregation of CaseResults (task 1.3).

`build_report` aggregates a flat list of `CaseResult` into a `Report` with
per-capability BINARY pass rates (fraction of cases where ALL applicable
checks passed — i.e. `CaseResult.passed` — not a mean of check scores; see
`specs/agent-eval-pipeline/research-brief.md` §5). `save_report`/`load_report`
persist the contract as JSON.

`schema_version` starts at "1.0". CI, the baseline diff, the future MCP
server, and the phase-2 failure-mining agent all consume this shape
(`specs/agent-eval-pipeline/design-portability.md`) — changes to the Report
shape must be ADDITIVE (new optional keys), never a rename/removal of an
existing key, or every one of those consumers breaks at once.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from evalkit.registry import Taxonomy
from evalkit.types import CaseResult, Report

SCHEMA_VERSION = "1.0"


def build_report(
    case_results: Sequence[CaseResult],
    taxonomy: Taxonomy,
    run_meta: Mapping[str, Any] | None = None,
) -> Report:
    """Aggregate *case_results* into a versioned `Report`.

    Per capability: `{passed, total, pass_rate, threshold, meets_threshold}`,
    where `pass_rate = passed / total` counts whole cases (`CaseResult.passed`),
    not individual checks. `threshold` comes from `taxonomy.threshold_for`.
    An overall summary (total cases, overall pass rate, capabilities under
    threshold) is folded into `run_meta["summary"]` — `Report` has no
    dedicated summary field, and `run_meta` is the open extension point.
    """
    by_capability: dict[str, list[CaseResult]] = {}
    for case in case_results:
        by_capability.setdefault(case.capability, []).append(case)

    per_capability: dict[str, dict[str, Any]] = {}
    for capability, cases in by_capability.items():
        total = len(cases)
        passed = sum(1 for case in cases if case.passed)
        pass_rate = passed / total if total else 0.0
        threshold = taxonomy.threshold_for(capability)
        per_capability[capability] = {
            "passed": passed,
            "total": total,
            "pass_rate": pass_rate,
            "threshold": threshold,
            "meets_threshold": pass_rate >= threshold,
        }

    total_cases = len(case_results)
    total_passed = sum(1 for case in case_results if case.passed)
    summary = {
        "total_cases": total_cases,
        "total_passed": total_passed,
        "overall_pass_rate": total_passed / total_cases if total_cases else 0.0,
        "capabilities_below_threshold": sorted(
            capability
            for capability, stats in per_capability.items()
            if not stats["meets_threshold"]
        ),
    }

    merged_run_meta = dict(run_meta or {})
    merged_run_meta["summary"] = summary

    return Report(
        schema_version=SCHEMA_VERSION,
        run_meta=merged_run_meta,
        per_case=list(case_results),
        per_capability=per_capability,
    )


def report_exit_code(report: Report) -> int:
    """1 if any capability's `meets_threshold` is False, else 0."""
    return int(
        any(
            not stats.get("meets_threshold", True)
            for stats in report.per_capability.values()
        )
    )


def save_report(report: Report, path: str | Path) -> None:
    """Write *report* as indented JSON to *path*."""
    Path(path).write_text(report.model_dump_json(indent=2), encoding="utf-8")


def load_report(path: str | Path) -> Report:
    """Read a `Report` back from JSON written by `save_report`."""
    return Report.model_validate_json(Path(path).read_text(encoding="utf-8"))
