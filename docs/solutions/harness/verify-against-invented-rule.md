---
problem_type: failure
module: harness
tags: verification, testing, invariants, parametrize, anchor-dependence, evidence, self-review, false-proof
severity: critical
applicable_when: Implementing behavior whose correct output depends on WHEN it runs (weekday, month boundary, timezone, business hours, fiscal period) — or any time you are about to write a test whose expected values you derived from a rule you yourself invented.
affects:
  - apps/api/app/core/dates.py
  - apps/api/tests/core/test_dates.py
supersedes: null
confidence: high
confirmed_at: 2026-07-11
---

## Applicable When

Implementing behavior whose correct output depends on **when** it runs — weekday, month boundary,
timezone, business hours, fiscal period — or any time you are about to write a test whose expected
values you derived from a rule you invented yourself.

## Symptom

A P0 shipped with a **full green proof chain behind it**: 51 passing unit tests, an ad-hoc REPL
spot-check over 18 expressions, and a live end-to-end probe against the real agent. `SUMMARY.md`
recorded the live transcript as evidence the feature was verified.

The behavior was wrong. `"thứ 6 tuần sau"` ("Friday of next week") resolved to **2026-07-24** when
the correct answer was **2026-07-17** — off by exactly 7 days, on 3 of every 7 possible days of the
week, silently, with no exception raised, into a flow that ends in a paid booking.

## Wrong Approach

Three checks, all passed, none of them verification:

1. **The pinned rule was invented, then checked against itself.** The plan declared `"next <weekday>"
   = next occurrence strictly after today, + 7 days`. The implementation matched that rule. The
   spot-check confirmed the implementation matched that rule. Nobody ever asked whether *the rule*
   matched what "thứ 6 tuần sau" means in Vietnamese. It does not: it means the Friday of the next
   calendar week.

2. **The tests pinned a single anchor** — `TODAY = 2026-07-09`, a Thursday. On a Thursday anchor the
   buggy and correct algorithms **coincide**. The one anchor chosen was the one where the bug is
   invisible.

3. **The live probe recorded the wrong answer as proof.** The agent replied "24/07/2026" and that
   went into the evidence table as a passing row, because the reviewer (me) was checking that the
   agent *behaved* — resolved without asking — not that the date was *right*.

The module also contradicted itself in plain sight: `"tuần sau"` resolved week-anchored (→ Monday of
next week, 07-13) while `"thứ 2 tuần sau"` resolved to 07-20. The same phrase, two different weeks —
printed in the spot-check output and read straight past.

## Why It Failed

Every check asked the same question — **"does the code do what the rule says?"** — and none asked
**"does the rule say the right thing?"** A test whose expected values come from the same head that
wrote the implementation is a tautology with a green tick on it. Scale and repetition do not fix
this: 51 of those tests are still 51 restatements of one assumption.

The anchor problem compounds it. When behavior depends on *when it runs*, a single pinned "now" is
not a test of the behavior — it is a test of one slice of it, and there is no reason to believe the
slice you happened to pick is the one that fails.

## Correct Approach

**Assert invariants, not values — and sweep every anchor.**

An invariant catches a wrong *rule*; a table of expected values only restates it.

```python
# Value table — restates the rule; passes even when the rule is wrong.
assert resolve("thứ 6 tuần sau", thursday) == "2026-07-17"

# Invariant — catches the wrong rule, on every anchor, without knowing the answer.
_WEEK_ANCHORS = [date(2026, 7, 6) + timedelta(days=i) for i in range(7)]

@pytest.mark.parametrize("anchor", _WEEK_ANCHORS, ids=lambda d: d.strftime("%A"))
def test_next_weekday_never_overshoots_next_week_window(anchor):
    # "<weekday> tuần sau" must land inside the 7-day window that "tuần sau" opens.
    next_week_monday = date.fromisoformat(resolve("tuần sau", anchor))
    next_friday      = date.fromisoformat(resolve("thứ 6 tuần sau", anchor))
    assert next_week_monday <= next_friday <= next_week_monday + timedelta(days=6)
```

This invariant is derivable from the *meaning* of the phrase, not from the implementation — which is
exactly why it fails on the buggy code and passes on the correct code, without anyone having to be
right about "07-17" in advance.

Then: **ground the rule outside your own head.** For a semantic convention (what a phrase means, what
a user expects), the source of truth is the domain, not the plan you just wrote. If nothing external
can settle it, that is itself the signal — make the code *ask* rather than pick (this module raises
`AmbiguousDateError` for exactly that case).

And when a check prints output, **read the output, not just the exit code.** The contradiction was on
screen.

## Guardrail

`proposed:` A lint/review check that flags a test module which (a) defines a single module-level
`TODAY`/`NOW` constant and (b) tests functions taking that value as a parameter, without any
`parametrize` over multiple anchors — the exact shape of `tests/core/test_dates.py` before the fix.
Anchor-dependent behavior tested from one anchor should have to justify itself.

## Related

- [negative-grep-is-not-absence](negative-grep-is-not-absence.md)
- [../agent/llm-parses-code-computes.md](../agent/llm-parses-code-computes.md)
