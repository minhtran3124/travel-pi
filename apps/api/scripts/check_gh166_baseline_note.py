#!/usr/bin/env python3
"""Assert the SUMMARY records an explicit baseline decision.

Adding a golden moves the capability's pass_rate, so the decision to refresh the
baseline or accept the delta must be recorded, not left implicit. This checks the
record exists and is specific (a fixed branch token plus two pass_rate values on
one line); it does not judge whether the decision was right.
"""

from __future__ import annotations

import re
from pathlib import Path

# Resolved from the file, not cwd: runs from apps/api but reads a repo-root file.
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

    # Anchor on the word the line LEADS with: "accepted, not refreshed" contains
    # both tokens, so reporting the wrong branch is worse than no check. \b stops
    # "acceptedly" passing; IGNORECASE allows a capitalised "Accepted".
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
