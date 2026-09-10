#!/usr/bin/env python
"""Guard the routing eval against the GH-180 supervisor crash.

Loads a report JSON produced by ``python -m eval`` and inspects the
``routing-multi_turn-*`` cases. The pre-fix crash surfaces as an ``agent_run``
check with ``passed: false`` and a ``detail`` starting
``agent run raised ValidationError``. This checker exits non-zero when any such
crash is present (or when fewer than two distinct routing cases are found) so it
can gate both the pre-fix fixture (must fail) and a fresh post-fix report (must
pass).

Usage:
    python scripts/check_gh180_routing_report.py <report.json>
"""

from __future__ import annotations

import json
import sys

PREFIX = "routing-multi_turn-"
DETAIL_MAX = 120


def _failing_detail(entry: dict) -> str | None:
    """Return the first failing check's detail for an entry, if any."""
    for check in entry.get("checks") or []:
        if not check.get("passed"):
            detail = check.get("detail")
            if detail:
                return str(detail)
    return None


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: check_gh180_routing_report.py <report.json>", file=sys.stderr)
        return 2

    with open(argv[1], encoding="utf-8") as fh:
        report = json.load(fh)

    per_case = report.get("per_case") or []
    routing = [
        entry
        for entry in per_case
        if str(entry.get("golden_id", "")).startswith(PREFIX)
    ]

    has_validation_error = False
    for entry in routing:
        golden_id = entry.get("golden_id")
        detail = _failing_detail(entry)
        shown = detail[:DETAIL_MAX] if detail else ""
        print(f"{golden_id}\tpassed={entry.get('passed')}\t{shown}")
        for check in entry.get("checks") or []:
            check_detail = check.get("detail")
            if check_detail and "ValidationError" in str(check_detail):
                has_validation_error = True

    distinct = {entry.get("golden_id") for entry in routing}
    if len(distinct) < 2:
        print(
            f"FAIL: expected >=2 distinct {PREFIX}* cases, found {len(distinct)}",
            file=sys.stderr,
        )
        return 1

    if has_validation_error:
        print(
            "FAIL: a routing-multi_turn case crashed with ValidationError",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
