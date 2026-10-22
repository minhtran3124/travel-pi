#!/usr/bin/env python3
"""Assert the counting golden's ``expected_flow`` is a flow the supervisor can route to.

The valid set is derived (``ALL_SUBAGENTS`` plus ``SYNTHESIZE_NODE``) rather than
restated, so a renamed or added sub-agent cannot leave it asserting a stale list.
``SYNTHESIZE_NODE`` is included because the multi-intent fan-out path sets
``current_flow`` to the synthesize node's own name.
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
