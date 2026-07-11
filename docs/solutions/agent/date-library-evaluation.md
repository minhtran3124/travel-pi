---
problem_type: decision
module: agent/tools
tags: dependencies, dateparser, python-dateutil, pendulum, nih, date-parsing, raise-dont-guess, build-vs-buy
severity: standard
applicable_when: Tempted to replace app/core/dates.py with an off-the-shelf date library, or facing any build-vs-buy call where the requirement is "raise rather than return something plausible".
affects:
  - apps/api/app/core/dates.py
  - apps/api/requirements.txt
supersedes: null
confidence: high
confirmed_at: 2026-07-11
---

## Applicable When

Someone proposes replacing `app/core/dates.py` with a popular date library — a reasonable instinct,
and one worth having an evidence-backed answer to rather than re-litigating. More generally: any
build-vs-buy call where the requirement is **"raise rather than return something plausible."**

## Context

`app/core/dates.py` is hand-written: a strict numeric parser plus ~60 lines of calendar arithmetic
that turns an LLM-parsed `DateIntent` into an ISO date (see
[llm-parses-code-computes](llm-parses-code-computes.md)). Hand-rolled date logic is a classic
not-invented-here smell — and this particular hand-rolled logic had already shipped a P0 (a weekday
resolved 7 days late). So: is there a battle-tested package that should own this instead?

All candidates were measured empirically in a throwaway venv (`dateparser` 1.4.1, `python-dateutil`
2.9.0, `pendulum` 3.2.0, py3.12), with base date **Saturday 2026-07-11**. The numbers below are
observed, not quoted from docs.

## Options Considered

### `dateparser` — could it replace the LLM parser? (the highest-value question)

It advertises ~200 languages including Vietnamese. Measured with `RELATIVE_BASE=2026-07-11`,
`PREFER_DATES_FROM='future'`:

| input | result |
|---|---|
| `next friday` | **None** |
| `thứ 2 tuần tới` · `thứ 6 tuần sau` · `cuối tuần này` | **None** |
| `来週の月曜日` | **None** |
| `2 ngày nữa` | **None** (yet `3 ngày trước` works — VN *future* offsets are broken) |
| `friday` · `ngày mai` · `in 3 days` | ✅ correct |
| `tuần sau` | 2026-07-18 = **base + 7 days**, NOT Monday-of-next-week (07-13) |
| `07/2026` | **2026-07-11** — silently invents the day from today |

Weekday-plus-week composition — the entire reason the LLM parser exists — is a known, open,
unimplemented limitation ([#573](https://github.com/scrapinghub/dateparser/issues/573),
[#344](https://github.com/scrapinghub/dateparser/issues/344)). Where it *does* answer, it disagrees
with our pinned semantics (`tuần sau`) or **guesses where we must raise** (`07/2026`).

### `python-dateutil` — for the arithmetic and the numeric parse

```python
>>> friday = date(2026, 7, 17)
>>> friday + relativedelta(weekday=FR(+1))
datetime.date(2026, 7, 17)      # the SAME Friday — inclusive of today
```

`relativedelta`'s weekday navigation is **inclusive of today** — which is exactly the off-by-one
class that produced our P0. It is the trap, not the cure. `dateutil.parser.parse('07/2026',
dayfirst=True)` also silently fills the missing day from `default` (→ today), the guess we raise on.

`relativedelta(weeks=+1, weekday=MO(-1))` *does* express Monday-of-next-week correctly — but that is
one line either way (`day - timedelta(days=day.weekday()) + timedelta(days=7)`), so it buys nothing.

### `pendulum`

`p.next(pendulum.FRIDAY)` is genuinely strict, and `start_of('week')` reads well. But it is a whole
datetime library (Rust extension) bought for ~3 one-line helpers, and it still cannot express the
business rules (the weekend-already-underway case, raise-on-passed-weekday).

### Ruled out without measurement

`arrow` (no calendar-week weekday navigation, no NLP) · `ctparse` / `parsedatetime` (English-only) ·
`duckling` / `sutime` (**JVM / Haskell runtime** — disqualified in a FastAPI Docker image) ·
`dateutil.rrule` (recurrence engine; overkill).

## Decision & Rationale

**Keep `app/core/dates.py`. Adopt nothing.**

The reason is not that the hand-rolled code is good — it is that **our requirements are stricter
than every candidate's defaults.** These libraries are designed to *always return something
plausible*. That is a guess. This module exists to **raise so the agent asks a question**. Adopting
one would mean re-implementing every guard on top of a looser foundation: more code, weaker contract.

Two specifics settle it:

- `dateparser` cannot parse the phrases the feature is *for*, and invents a day for `07/2026`.
- `dateutil`'s weekday navigation reproduces the exact P0 semantics we fixed.

And note what the arithmetic actually is: of `_compute`'s ~60 lines, roughly 40 are **guard clauses
validating untrusted LLM output** (a `kind` whose required fields are missing, an out-of-range
offset). No date library validates *our* intent schema. The real arithmetic is a handful of stdlib
lines.

**The P0 was a semantics bug, not an arithmetic bug** — no library would have prevented it. The test
matrix did (all 7 anchor weekdays + a cross-form invariant). Invest there, not in a dependency.

## Consequences

- No new runtime dependency. (`python-dateutil` is not currently a runtime dep — only `posthog`'s
  *test* extra declares it — so any of these would have been genuinely new.)
- We own the semantics, and must keep owning the test matrix that pins them. That is the trade, and
  it is stated deliberately: the safety comes from the tests, not from the code being clever.
- Revisit if `dateparser` ever closes #573/#344 — a maintained community lexicon covering weekday +
  week composition across 200 languages *would* beat an LLM call on both cost and latency. That is
  the trigger to re-open this decision; nothing else is.

## Related

- [llm-parses-code-computes](llm-parses-code-computes.md)
- [../harness/verify-against-invented-rule.md](../harness/verify-against-invented-rule.md)
