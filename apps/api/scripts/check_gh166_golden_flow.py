#!/usr/bin/env python3
"""SC-10: the gh-166 counting golden must name a real, observed sub-agent flow.

`expected_flow` is filled from an actual eval run (PLAN.md Task 4.1), never
guessed. This check cannot prove provenance — that stays in the SUMMARY's
`### Not auto-verified` section — but it does prove the value is present and
is a flow the supervisor can route to.

`TOOLS_BY_DOMAIN`'s keys are the only canonical set of sub-agent names:
`TravelAgentState.current_flow` is a plain `str`, so there is no enum to read.
Deriving the set here rather than restating it means a renamed or added
sub-agent cannot leave this check asserting against a stale list.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

GOLDEN_ID = "journal-happy-en-02"
DATASET = Path(__file__).resolve().parent.parent / "eval" / "datasets" / "journal.json"


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from app.tools.registry import TOOLS_BY_DOMAIN

    known = set(TOOLS_BY_DOMAIN)
    cases = json.loads(DATASET.read_text())
    match = [c for c in cases if c.get("id") == GOLDEN_ID]
    if not match:
        print(f"FAIL  {GOLDEN_ID} is missing from {DATASET.name}")
        return 1

    flow = match[0].get("expected_flow")
    if not flow:
        print(
            f"FAIL  {GOLDEN_ID} has no expected_flow — fill it from an observed "
            "eval run (PLAN.md Task 4.1), do not guess it"
        )
        return 1
    if flow not in known:
        print(
            f"FAIL  {GOLDEN_ID} expected_flow={flow!r} is not a sub-agent the "
            f"supervisor can route to; known flows are {sorted(known)}"
        )
        return 1

    print(f"ok  {GOLDEN_ID}: expected_flow={flow!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
