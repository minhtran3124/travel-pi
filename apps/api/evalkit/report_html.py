"""Render a `Report` as a single self-contained HTML page (no assets, no CDN).

Same portability contract as the rest of `evalkit/` (stdlib only — no `app.*`,
no web framework, no template engine): a project gets the viewer for free by
consuming the versioned Report shape, and the page can be opened straight from
disk or attached to a CI artifact.

Reads only documented `Report` keys (`per_case`, `per_capability`,
`run_meta["summary"]`), so an ADDITIVE schema change never breaks it.

Usage:
    python -m evalkit.report_html eval/reports/latest.json eval/reports/latest.html
"""

from __future__ import annotations

import sys
from html import escape
from pathlib import Path
from typing import Any

from evalkit.types import CaseResult, Report

_CSS = """
:root {
  color-scheme: light dark;
  --bg: #f6f7f9; --panel: #fff; --line: #e3e6ea; --ink: #14181d; --muted: #6b7480;
  --pass: #16794a; --pass-bg: #e6f4ec; --fail: #b3261e; --fail-bg: #fdecea;
  --bar: #dfe3e8;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f1216; --panel: #171b21; --line: #262c34; --ink: #e6e9ed; --muted: #98a1ac;
    --pass: #5bd39b; --pass-bg: #12301f; --fail: #ff8a80; --fail-bg: #331715;
    --bar: #2b323a;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 32px 24px 64px; background: var(--bg); color: var(--ink);
  font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}
.wrap { max-width: 1040px; margin: 0 auto; }
h1 { font-size: 24px; margin: 0 0 4px; }
.sub { color: var(--muted); font-size: 13px; margin-bottom: 24px; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 28px; }
.tile { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; }
.tile .k { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }
.tile .v { font-size: 26px; font-weight: 600; margin-top: 4px; font-variant-numeric: tabular-nums; }
.v.pass { color: var(--pass); } .v.fail { color: var(--fail); }
h2 { font-size: 16px; margin: 28px 0 10px; }
table { width: 100%; border-collapse: collapse; background: var(--panel); border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
th, td { text-align: left; padding: 9px 14px; border-bottom: 1px solid var(--line); font-size: 14px; }
th { color: var(--muted); font-weight: 500; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }
tr:last-child td { border-bottom: 0; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
.bar { height: 6px; background: var(--bar); border-radius: 3px; overflow: hidden; min-width: 90px; }
.bar > i { display: block; height: 100%; background: var(--pass); }
.bar.below > i { background: var(--fail); }
.badge { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 12px; font-weight: 600; }
.badge.pass { color: var(--pass); background: var(--pass-bg); }
.badge.fail { color: var(--fail); background: var(--fail-bg); }
.controls { display: flex; gap: 8px; align-items: center; margin: 28px 0 10px; flex-wrap: wrap; }
.controls h2 { margin: 0; flex: 1; }
button {
  font: inherit; font-size: 13px; padding: 5px 12px; border-radius: 999px; cursor: pointer;
  border: 1px solid var(--line); background: var(--panel); color: var(--muted);
}
button[aria-pressed="true"] { color: var(--ink); border-color: var(--ink); }
details.case { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; margin-bottom: 8px; }
details.case > summary { padding: 11px 14px; cursor: pointer; display: flex; gap: 10px; align-items: center; }
details.case > summary::-webkit-details-marker { display: none; }
.case-id { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px; }
.case-meta { color: var(--muted); font-size: 12px; margin-left: auto; }
.checks { padding: 0 14px 12px; }
.checks table { border-radius: 6px; }
.detail { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; color: var(--muted); word-break: break-word; white-space: pre-wrap; }
"""

_JS = """
const buttons = document.querySelectorAll('[data-filter]');
buttons.forEach((btn) => btn.addEventListener('click', () => {
  const mode = btn.dataset.filter;
  buttons.forEach((b) => b.setAttribute('aria-pressed', String(b === btn)));
  document.querySelectorAll('details.case').forEach((el) => {
    const failed = el.dataset.passed === 'false';
    el.hidden = mode === 'failed' ? !failed : mode === 'passed' ? failed : false;
  });
}));
"""


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _badge(passed: bool) -> str:
    return (
        f'<span class="badge {"pass" if passed else "fail"}">'
        f"{'PASS' if passed else 'FAIL'}</span>"
    )


def _tiles(report: Report) -> str:
    summary: dict[str, Any] = report.run_meta.get("summary", {})
    total = summary.get("total_cases", len(report.per_case))
    passed = summary.get(
        "total_passed", sum(1 for case in report.per_case if case.passed)
    )
    failed = total - passed
    rate = summary.get("overall_pass_rate", passed / total if total else 0.0)
    below = summary.get("capabilities_below_threshold", [])

    tiles = [
        ("Test cases", str(total), ""),
        ("Passed", str(passed), "pass"),
        ("Failed", str(failed), "fail" if failed else ""),
        # Neutral on purpose: an 83% overall rate is not itself a failure — the
        # gate is per-capability thresholds, which the next tile reports.
        ("Pass rate", _pct(rate), ""),
        ("Below threshold", str(len(below)), "fail" if below else ""),
    ]
    cells = "".join(
        f'<div class="tile"><div class="k">{escape(label)}</div>'
        f'<div class="v {cls}">{escape(value)}</div></div>'
        for label, value, cls in tiles
    )
    return f'<div class="tiles">{cells}</div>'


def _capability_table(report: Report) -> str:
    rows = []
    for capability in sorted(report.per_capability):
        stats = report.per_capability[capability]
        rate = float(stats.get("pass_rate", 0.0))
        ok = bool(stats.get("meets_threshold", False))
        rows.append(
            "<tr>"
            f"<td>{escape(capability)}</td>"
            f'<td class="num">{stats.get("passed", 0)}/{stats.get("total", 0)}</td>'
            f'<td class="num">{_pct(rate)}</td>'
            f'<td class="num">{_pct(float(stats.get("threshold", 0.0)))}</td>'
            f'<td><div class="bar {"" if ok else "below"}">'
            f'<i style="width:{min(max(rate, 0.0), 1.0) * 100:.1f}%"></i></div></td>'
            f"<td>{_badge(ok)}</td>"
            "</tr>"
        )
    return (
        "<h2>Per capability</h2><table><thead><tr>"
        "<th>Capability</th><th>Passed</th><th>Pass rate</th><th>Threshold</th>"
        "<th></th><th>Status</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _case_block(case: CaseResult) -> str:
    checks = "".join(
        "<tr>"
        f"<td>{escape(check.name)}</td>"
        f"<td>{_badge(check.passed)}</td>"
        f'<td class="num">{"" if check.score is None else f"{check.score:.2f}"}</td>'
        f'<td class="detail">{escape(check.detail or "")}</td>'
        "</tr>"
        for check in case.checks
    )
    return (
        f'<details class="case" data-passed="{str(case.passed).lower()}"'
        f"{' open' if not case.passed else ''}>"
        f"<summary>{_badge(case.passed)}"
        f'<span class="case-id">{escape(case.golden_id)}</span>'
        f'<span class="case-meta">{escape(case.capability)} / {escape(case.scenario)}'
        f" · {len(case.checks)} checks</span></summary>"
        f'<div class="checks"><table><thead><tr><th>Check</th><th>Result</th>'
        f"<th>Score</th><th>Detail</th></tr></thead><tbody>{checks}"
        "</tbody></table></div></details>"
    )


def render_html(report: Report, *, title: str = "Agent eval report") -> str:
    """Render *report* as a standalone HTML document (string)."""
    meta = report.run_meta
    subtitle = " · ".join(
        f"{key}={meta[key]}"
        for key in ("suite", "capability", "language")
        if meta.get(key)
    )
    skipped = meta.get("skipped_judged_metrics")
    if skipped:
        subtitle += f" · skipped judged metrics: {', '.join(skipped)}"

    # Failing cases first: the report is read to find what broke.
    cases = sorted(report.per_case, key=lambda c: (c.passed, c.capability, c.golden_id))
    case_blocks = "".join(_case_block(case) for case in cases)

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title><style>{_CSS}</style></head>
<body><div class="wrap">
<h1>{escape(title)}</h1>
<div class="sub">schema {escape(report.schema_version)}
{" · " + escape(subtitle) if subtitle else ""}</div>
{_tiles(report)}
{_capability_table(report)}
<div class="controls">
  <h2>Test cases</h2>
  <button data-filter="all" aria-pressed="true">All</button>
  <button data-filter="failed" aria-pressed="false">Failed only</button>
  <button data-filter="passed" aria-pressed="false">Passed only</button>
</div>
{case_blocks}
</div><script>{_JS}</script></body></html>
"""


def save_html(
    report: Report, path: str | Path, *, title: str = "Agent eval report"
) -> None:
    """Write *report* as an HTML page to *path*, creating parent dirs as needed."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_html(report, title=title), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """`python -m evalkit.report_html <report.json> [out.html]` — convert an
    already-saved report (e.g. a past CI artifact) without re-running the suite.
    """
    from evalkit.report import load_report

    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(__doc__ or "", file=sys.stderr)
        return 2
    src = Path(args[0])
    dst = Path(args[1]) if len(args) > 1 else src.with_suffix(".html")
    save_html(load_report(src), dst)
    print(f"html report written to {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
