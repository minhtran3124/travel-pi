---
problem_type: failure
module: harness
tags: grep, evidence, not-observed-vs-absent, prompts, active-yaml, scope, search-methodology
severity: critical
applicable_when: About to conclude "only file X does Y" from a search — especially when removing a rule/behavior that may be stated in several places, and above all across the versioned agent prompts.
affects:
  - apps/api/app/prompts/planner/v7.md
  - apps/api/app/prompts/booking/v6.md
supersedes: null
confidence: high
confirmed_at: 2026-07-11

---

## Applicable When

You are about to conclude *"only file X does Y"* from a search — especially when **removing** a rule
or behavior that could be stated in more than one place, and above all across the versioned agent
prompts under `apps/api/app/prompts/<agent>/`.

## Symptom

A feature whose entire purpose was "stop asking the traveller to confirm a date" shipped with the
confirmation rule **still active on the dominant code path**. The live probe passed. The tests
passed. The feature looked delivered. A code-review agent found `planner/v6.md` — the prompt the
supervisor routes most flight/hotel searches to — still ordering:

> "Resolve relative dates … to a concrete date **yourself**"
> "**Confirm the resolved value once** … get a single yes/no confirmation **before you search**"

…directly contradicting the new grounding note sitting in the *same system message*.

## Wrong Approach

Scoping the change from one filtered grep:

```bash
grep -rn "confirm\|ask" app/prompts/planner/v6.md app/prompts/supervisor/v5.md app/prompts/concierge/v9.md \
  | grep -i "date\|detail\|missing\|guess"
```

It returned one hit, from `concierge`. I concluded: *"Only `booking/v5` has the confirm-date rule"*
and scoped the plan to booking alone.

## Why It Failed

Two compounding reasons:

1. **grep is line-oriented; prose is not.** The rule was wrapped across lines. The line carrying
   `"confirmation before you search"` contained no word from the second filter (`date|detail|missing|guess`),
   so the `AND` of the two greps matched nothing. The rule was *there*; my query could not see it.

2. **A negative result was read as evidence of absence.** `.claude/rules/behavior.md` already states
   `not_observed != absent`. I had the rule, and violated it anyway, because a grep *feels* like a
   proof — it is exhaustive over the thing it actually searched, which is not the thing you care
   about.

The result was worse than a plain miss. The prepended grounding note happened to win over the
contradictory prompt at runtime, so the **live probe passed** and the feature looked complete while
the main path still carried the old orders. We were not correct; we were lucky.

## Correct Approach

**When removing a rule, enumerate and read — do not search for the phrasing you remember.**

```bash
# 1. Which prompts are actually LIVE? (active.yaml is the pointer that selects the version)
cat app/prompts/active.yaml

# 2. Read each ACTIVE prompt end to end. There are ~8 of them; it costs minutes.
#    Do not grep for a phrase you are trying to delete — you are searching for wording you
#    are, by definition, unsure of.
```

If you must search, search **broad and un-ANDed**, then read every hit in context:

```bash
grep -rn -i "confirm" app/prompts/       # one term, no second filter, all families
```

Then **pin the outcome with a test**, so the removal cannot silently regress or be half-applied.
`tests/prompts/test_booking_prompt.py` now asserts, for *both* active prompts, that the mandated
tool appears and the removed phrases are **absent**:

```python
assert "resolve_date" in registry.get("planner")
assert "confirmation before you search" not in registry.get("planner")
```

State the search you actually ran when you claim absence: *"I read all 8 active prompts"* is
evidence; *"grep found nothing"* is not.

## Guardrail

`proposed:` A test that greps **every ACTIVE prompt** (resolved through `active.yaml`, not the
directory) for a list of retired phrases — the "banned phrasing" list a feature declares when it
removes a behavioral rule. A rule deleted from one prompt but alive in another is then a red test,
not a lucky runtime.

## Related

- [verify-against-invented-rule](verify-against-invented-rule.md)
- [../agent/supervisor-active-yaml-is-a-pointer.md](../agent/supervisor-active-yaml-is-a-pointer.md)
