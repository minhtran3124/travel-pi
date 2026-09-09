"""Compare two evalkit Report JSONs case-by-case and fail on any regression.

Written for GH-173, whose ship gate is **two-sided**: the target golden must
improve *and* no other golden may get worse. `make eval-compare` answers a
different question — it diffs a whole run against the committed baseline at the
capability level — so a single-capability before/after pair needs this.

Usage (from ``apps/api/``)::

    ../../.venv/bin/python eval/compare_capability.py \
        eval/reports/gh173-before.json eval/reports/gh173-after.json

Exit 0 when no golden regressed; exit 1 naming every golden that did. A golden
present in only one report is reported but never counted as a regression — the
two runs may legitimately cover different suites.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _results(path: Path) -> dict[str, bool]:
    """Map golden_id -> passed, from an evalkit Report JSON's ``per_case``."""
    report = json.loads(path.read_text())
    return {case["golden_id"]: bool(case["passed"]) for case in report["per_case"]}


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(
            f"usage: {Path(argv[0]).name} <before.json> <after.json>", file=sys.stderr
        )
        return 2

    before = _results(Path(argv[1]))
    after = _results(Path(argv[2]))

    regressions = sorted(
        g for g in before.keys() & after.keys() if before[g] and not after[g]
    )
    fixes = sorted(
        g for g in before.keys() & after.keys() if not before[g] and after[g]
    )
    only_before = sorted(before.keys() - after.keys())
    only_after = sorted(after.keys() - before.keys())

    for golden in fixes:
        print(f"FIXED       {golden}")
    for golden in regressions:
        print(f"REGRESSED   {golden}")
    for golden in only_before:
        print(f"missing in after: {golden}")
    for golden in only_after:
        print(f"new in after:     {golden}")

    print(
        f"before {sum(before.values())}/{len(before)}  "
        f"after {sum(after.values())}/{len(after)}  "
        f"fixed {len(fixes)}  regressed {len(regressions)}"
    )
    return 1 if regressions else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
