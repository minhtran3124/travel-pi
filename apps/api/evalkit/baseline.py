"""Baseline save/compare: the regression gate (task 1.3).

`JsonBaselineStore` implements the `BaselineStore` port (`evalkit.ports`) by
delegating to `evalkit.report`'s JSON I/O. `compare` diffs a fresh `Report`
against a committed baseline `Report` and renders a readable table; the
caller (a future CLI) decides what to do with the exit code.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from evalkit.report import load_report, save_report
from evalkit.types import Report


class JsonBaselineStore:
    """`BaselineStore` port impl: a committed baseline `Report` as JSON."""

    def save(self, report: Report, path: str) -> None:
        save_report(report, path)

    def load(self, path: str) -> Report:
        return load_report(path)


class CapabilityDiff(BaseModel):
    """One capability's pass-rate delta between baseline and current run."""

    baseline_pass_rate: float | None
    current_pass_rate: float
    delta: float | None  # current - baseline; None when there is no baseline
    regressed: bool  # delta is not None and delta < -tolerance
    is_new: bool = False  # capability absent from the baseline entirely


class Diff(BaseModel):
    """The result of `compare`: per-capability deltas + per-case flips."""

    tolerance: float
    per_capability: dict[str, CapabilityDiff] = Field(default_factory=dict)
    # golden_id -> capability, for cases that flipped pass -> fail / fail -> pass
    regressions: dict[str, str] = Field(default_factory=dict)
    fixes: dict[str, str] = Field(default_factory=dict)
    new_capabilities: list[str] = Field(default_factory=list)

    def exit_code(self) -> int:
        """Non-zero when the regression gate trips.

        The gate fires on EITHER of two rules:

        1. **Capability-level drop** — a capability's current pass rate is
           more than `tolerance` below its baseline pass rate
           (`delta < -tolerance`). Catches broad regressions.
        2. **Masked flip** — a specific case flips pass -> fail inside a
           capability whose pass rate also dropped by ANY amount
           (`delta < 0`), even if that drop is within tolerance. This catches
           a real regression that an unrelated fix in the same capability
           landing in the same run would otherwise cancel out in the
           aggregate rate.

        A capability with no baseline (`is_new=True`) never trips the gate —
        there is nothing to regress against yet (see `compare` docstring).
        """
        for capability_diff in self.per_capability.values():
            if capability_diff.regressed:
                return 1
        for capability in self.regressions.values():
            capability_diff = self.per_capability.get(capability)
            if (
                capability_diff is not None
                and capability_diff.delta is not None
                and capability_diff.delta < 0
            ):
                return 1
        return 0


def compare(report: Report, baseline: Report, tolerance: float = 0.05) -> Diff:
    """Diff *report* (current run) against *baseline* (committed run).

    Per-capability rate deltas are read from each `Report.per_capability`
    (`pass_rate`, populated by `evalkit.report.build_report`). Per-case flips
    are computed from `per_case`, matched by `golden_id`.

    New-capability policy: a capability present in *report* but absent from
    *baseline* is recorded in `new_capabilities` and given a `CapabilityDiff`
    with `baseline_pass_rate=None`, `delta=None`, `regressed=False` — it is
    visible in the table but can never fail the gate, since a first run has
    no prior rate to regress against. A case whose golden_id only exists in
    one of the two reports (added/removed golden) is not a flip and is
    silently skipped — flips are only meaningful for cases present in both.
    """
    baseline_by_id = {case.golden_id: case.passed for case in baseline.per_case}
    current_by_capability = {
        case.golden_id: case.capability for case in report.per_case
    }
    current_pass_by_id = {case.golden_id: case.passed for case in report.per_case}

    regressions: dict[str, str] = {}
    fixes: dict[str, str] = {}
    for golden_id, was_passed in baseline_by_id.items():
        if golden_id not in current_pass_by_id:
            continue
        now_passed = current_pass_by_id[golden_id]
        capability = current_by_capability[golden_id]
        if was_passed and not now_passed:
            regressions[golden_id] = capability
        elif not was_passed and now_passed:
            fixes[golden_id] = capability

    per_capability: dict[str, CapabilityDiff] = {}
    new_capabilities: list[str] = []
    for capability, stats in report.per_capability.items():
        current_rate = stats["pass_rate"]
        baseline_stats = baseline.per_capability.get(capability)
        if baseline_stats is None:
            new_capabilities.append(capability)
            per_capability[capability] = CapabilityDiff(
                baseline_pass_rate=None,
                current_pass_rate=current_rate,
                delta=None,
                regressed=False,
                is_new=True,
            )
            continue
        baseline_rate = baseline_stats["pass_rate"]
        delta = current_rate - baseline_rate
        per_capability[capability] = CapabilityDiff(
            baseline_pass_rate=baseline_rate,
            current_pass_rate=current_rate,
            delta=delta,
            regressed=delta < -tolerance,
        )

    return Diff(
        tolerance=tolerance,
        per_capability=per_capability,
        regressions=regressions,
        fixes=fixes,
        new_capabilities=sorted(new_capabilities),
    )


def render_table(diff: Diff) -> str:
    """Render *diff* as a plain-text table. Pure string return — the caller
    (CLI) is responsible for printing it; keeps IO at the edge.
    """
    header = f"{'capability':<28}{'baseline':>10}{'current':>10}{'delta':>10}  status"
    lines = [header, "-" * len(header)]
    for capability in sorted(diff.per_capability):
        capability_diff = diff.per_capability[capability]
        baseline_cell = (
            "new"
            if capability_diff.baseline_pass_rate is None
            else f"{capability_diff.baseline_pass_rate:.1%}"
        )
        delta_cell = (
            "-" if capability_diff.delta is None else f"{capability_diff.delta:+.1%}"
        )
        status = "REGRESSED" if capability_diff.regressed else "ok"
        if capability_diff.is_new:
            status = "new"
        lines.append(
            f"{capability:<28}{baseline_cell:>10}"
            f"{capability_diff.current_pass_rate:>10.1%}{delta_cell:>10}  {status}"
        )

    if diff.regressions:
        lines.append("")
        lines.append("regressions (pass -> fail):")
        for golden_id, capability in sorted(diff.regressions.items()):
            lines.append(f"  - {golden_id} ({capability})")

    if diff.fixes:
        lines.append("")
        lines.append("fixes (fail -> pass):")
        for golden_id, capability in sorted(diff.fixes.items()):
            lines.append(f"  - {golden_id} ({capability})")

    lines.append("")
    lines.append(f"tolerance={diff.tolerance:.1%}  exit_code={diff.exit_code()}")
    return "\n".join(lines)
