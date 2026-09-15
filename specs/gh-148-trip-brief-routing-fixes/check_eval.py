"""Exit 0 iff every in-scope gh-148 golden is present and passed in an eval report.

Usage: python check_eval.py <report.json>
"""

from __future__ import annotations

import json
import sys

IN_SCOPE = (
    "language-ambiguous-en-01",
    "language-multi_turn-vi-01",
    "routing-multi-en-01",
    "journal-multi_turn-vi-01",
    "budget-ambiguous-en-03",
    "memory-multi_turn-vi-04",
)


def main(path: str) -> int:
    with open(path, encoding="utf-8") as fh:
        cases = {c["golden_id"]: c for c in json.load(fh)["per_case"]}
    failed = 0
    for golden_id in IN_SCOPE:
        case = cases.get(golden_id)
        if case is None:
            print(f"MISSING {golden_id}")
            failed += 1
        elif not case["passed"]:
            bad = [ck.get("name") for ck in case.get("checks", []) if not ck.get("passed")]
            print(f"FAIL    {golden_id} {bad}")
            failed += 1
        else:
            print(f"PASS    {golden_id}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
