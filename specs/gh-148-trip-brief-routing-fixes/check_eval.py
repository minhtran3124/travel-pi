"""Exit 0 iff every gated gh-148 golden passed in an eval report.

Usage:
    python check_eval.py <report.json> [<language-tally.json>]

Without a tally (Task 3.1): the six in-scope goldens must pass.
With a tally (Task 3.3, final): the in-scope goldens except
language-ambiguous-en-01, plus the three gh-191 regression goldens, must pass
in the report; language-ambiguous-en-01 is gated on the tally instead
(>= 4 of its 5 extra single runs replied in English) because one judged run
cannot tell a flaky rate (E002). Its judged verdict is printed, not gated.
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
GH191 = ("dates-ambiguous-en-02", "dates-ambiguous-vi-02", "dates-ambiguous-en-03")
FLAKY = "language-ambiguous-en-01"
TALLY_MIN = 4
# Owner decision E003: a check proven to be an eval-metric false positive is
# exempt, printed as EXEMPT, and tracked upstream. Any OTHER failing check on
# the same golden still fails the gate.
EXEMPT = {
    ("budget-ambiguous-en-03", "reply_language"): (
        "#212 detector reads any Latin diacritic as vi; diag-budget-rerun.txt "
        "shows an English reply with state.language=en"
    ),
}


def _check(cases: dict, golden_id: str) -> bool:
    case = cases.get(golden_id)
    if case is None:
        print(f"MISSING {golden_id}")
        return False
    if not case["passed"]:
        bad = [ck.get("name") for ck in case.get("checks", []) if not ck.get("passed")]
        real = [name for name in bad if (golden_id, name) not in EXEMPT]
        if real:
            print(f"FAIL    {golden_id} {real}")
            return False
        for name in bad:
            print(f"EXEMPT  {golden_id} {name}: {EXEMPT[(golden_id, name)]}")
        return True
    print(f"PASS    {golden_id}")
    return True


def main(report_path: str, tally_path: str | None = None) -> int:
    with open(report_path, encoding="utf-8") as fh:
        cases = {c["golden_id"]: c for c in json.load(fh)["per_case"]}
    if tally_path is None:
        gated = IN_SCOPE
    else:
        gated = tuple(g for g in IN_SCOPE if g != FLAKY) + GH191
    ok = all([_check(cases, g) for g in gated])
    if tally_path is not None:
        with open(tally_path, encoding="utf-8") as fh:
            runs = json.load(fh)["runs"]
        passed = sum(1 for r in runs if r["passed"])
        judged = cases.get(FLAKY, {}).get("passed")
        verdict = "PASS" if len(runs) == 5 and passed >= TALLY_MIN else "FAIL"
        print(f"{verdict:<7} {FLAKY} tally {passed}/{len(runs)} (need >= {TALLY_MIN}/5); judged run passed={judged}")
        ok = ok and verdict == "PASS"
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
