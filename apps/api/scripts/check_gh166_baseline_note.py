#!/usr/bin/env python3
"""SC-11: the gh-166 SUMMARY must record an explicit baseline decision.

Adding a golden moves the `journal` capability's pass_rate, which is what the
regression gate reads — `evalkit.baseline` skips a golden_id present in only
one report, so a new case never trips the gate by count. The decision to
refresh `eval/baselines/main.json` or to accept the delta must therefore be
recorded, not left implicit.

This asserts the record exists and is specific: one of the two fixed branch
tokens plus two numeric pass_rate values on the same line. It does not judge
whether the decision was right.
"""

from __future__ import annotations

import re
from pathlib import Path

# scripts -> apps/api -> apps -> repo root. Resolved from the file, not the
# cwd: this runs from apps/api but reads a file at the repo root.
REPO_ROOT = Path(__file__).resolve().parents[3]
SUMMARY = REPO_ROOT / "specs" / "gh-166-list-trips-tool" / "SUMMARY.md"
TOKENS = ("refreshed", "accepted")


def main() -> int:
    if not SUMMARY.exists():
        print(f"FAIL  {SUMMARY} not found")
        return 1

    lines = [
        ln for ln in SUMMARY.read_text().splitlines() if "Baseline decision:" in ln
    ]
    if not lines:
        print("FAIL  SUMMARY.md has no 'Baseline decision:' line")
        return 1

    # The token must be the word the line LEADS with, not merely present in it:
    # "accepted, not refreshed" contains both, and a check that reports the
    # wrong branch is worse than no check.
    # \b so "acceptedly" cannot pass as "accepted", IGNORECASE so a naturally
    # capitalised "Accepted" is not rejected. Both were live defects.
    decision = re.compile(
        r"Baseline decision:\s*\**(" + "|".join(TOKENS) + r")\b",
        re.IGNORECASE,
    )
    for line in lines:
        found = decision.search(line)
        numbers = re.findall(r"\d+\.\d+", line)
        if found and len(numbers) >= 2:
            print(
                f"ok  baseline decision recorded: {found.group(1)}, "
                f"pass_rates {numbers[:2]}"
            )
            return 0

    print(
        "FAIL  the 'Baseline decision:' line must LEAD with one of "
        f"{TOKENS} and carry two numeric pass_rate values; got: {lines[0].strip()!r}"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
