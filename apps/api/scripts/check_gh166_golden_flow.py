#!/usr/bin/env python3
"""SC-10: the gh-166 counting golden must name a real, observed sub-agent flow.

`expected_flow` is filled from an actual eval run (PLAN.md Task 4.1), never
guessed. This check cannot prove provenance — that stays in the SUMMARY's
`### Not auto-verified` section — but it does prove the value is present and
is a flow the supervisor can route to.

The valid set is `ALL_SUBAGENTS` (`app/agents/constants.py`, which calls itself
the single source of truth) plus `SYNTHESIZE_NODE`. The latter matters: on the
multi-intent fan-out path `nodes.py` sets `current_flow` to the synthesize
node's own name, and the eval runner copies `current_flow` straight into the
`Trace.flow` that `expected_flow` is compared against — so "synthesize" is a
value an honest observation can legitimately produce. Deriving the set rather
than restating it means a renamed or added sub-agent cannot leave this check
asserting against a stale list.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

GOLDEN_ID = "journal-happy-en-02"
DATASET = Path(__file__).resolve().parent.parent / "eval" / "datasets" / "journal.json"


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from app.agents.constants import ALL_SUBAGENTS, SYNTHESIZE_NODE

    known = {*ALL_SUBAGENTS, SYNTHESIZE_NODE}
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
