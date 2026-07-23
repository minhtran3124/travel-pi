---
problem_type: decision
module: agent/tools
tags: llm, structured-output, date-resolution, langgraph, tool-design, determinism, i18n, few-shot, function-calling
severity: critical
applicable_when: An agent tool must turn free-text human input (dates, durations, quantities, budgets) into a precise machine value, and you are choosing between a hardcoded parser, an LLM that returns the final value, or a split.
affects:
  - apps/api/app/tools/date_tools.py
  - apps/api/app/core/dates.py
  - apps/api/app/schemas/date_intent.py
  - apps/api/app/prompts/date_resolution/v1.md
supersedes: null
confidence: high
confirmed_at: 2026-07-11
---

## Applicable When

An agent tool must turn free-text human input into a precise machine value — a date, a duration, a
party size, a budget — and you are choosing between a hardcoded parser, an LLM that returns the
final value, or a split between the two.

## Context

`resolve_date` had to turn a traveller's wording ("thứ 6 tuần sau", "next friday", 来週の月曜日) into
an ISO date. Two attempts failed for opposite reasons, and the failures are what make the eventual
split non-obvious:

1. **A hardcoded lexicon** (`_RELATIVE_DAYS`, `_WEEKDAY_NAMES`, this/next prefix + suffix tables) —
   it worked until a traveller typed `"tuần tới"`, which means exactly what `"tuần sau"` means and
   was simply not in the table. The agent asked them to clarify a phrase that was never ambiguous.
   Adding `"tuần tới"` only queues up `"sang tuần"`, `"tuần kế"`, Japanese, Spanish… The table can
   never converge, and it only ever covers the languages someone thought of.
2. **Letting the LLM compute the date** — the natural fix, and the one that reintroduces the exact
   bug the tool existed to prevent. This feature had already shipped a P0 where `"thứ 6 tuần sau"`
   resolved 7 days late. Date arithmetic is precisely what models are worst at.

## Options Considered

| Option | Language coverage | Arithmetic correctness | Verdict |
|---|---|---|---|
| Hardcoded lexicon | Only the words you enumerate — never converges | Deterministic, testable | Rejected: a treadmill; produced the `"tuần tới"` regression |
| LLM returns the ISO date | Any language | Unverifiable, and models are bad at it | Rejected: this IS the P0 bug class |
| **LLM returns a structured intent; code computes the date** | Any language | Deterministic, testable | **Chosen** |

## Decision & Rationale

**Split the job by what each side is actually good at.** The model reads language; the code does
arithmetic. The model returns a *parsed intent* and **never a date**:

```
"thứ 2 tuần tới"  --LLM--> {kind:"weekday", weekday:0, week:"next"}  --code--> 2026-07-13
"来週の月曜日"      --LLM--> {kind:"weekday", weekday:0, week:"next"}  --code--> 2026-07-13
"2026-07-13"      ------------ code only (0 tokens, 0 latency) --------------> 2026-07-13
"khi nào rảnh"    --LLM--> {kind:"ambiguous", reason:...}            --code--> the agent asks
```

The model can still misread language — but that error is **visible in the tool trace, reproducible,
and fixable with a few-shot**. It can no longer silently add seven days. Every arithmetic invariant
(bare weekday is strictly future; "next <weekday>" lands inside the week that "next week" opens;
nothing resolves into the past) stays in code, pinned by tests that sweep all 7 anchor weekdays.

Three details that make it work:

- **A numeric fast path runs first.** An ISO or `DD/MM` input is language-independent, so it is
  parsed in code: zero tokens, zero latency. Only *words* reach the model.
- **The intent schema's `Field(description=...)` is prompt surface, not documentation.** It becomes
  the function-calling schema the model fills.
- **`ambiguous` is a first-class intent kind**, and it is the *only* path that makes the agent ask a
  question. The prompt must say both halves: never guess to avoid saying ambiguous, and never call
  ordinary-but-unfamiliar phrasing ambiguous — the second half is what the lexicon got wrong.

## Consequences

- **+1 LLM call (cheap/fast model) per worded date**, ~1–2s. Numeric dates cost nothing.
- The tightening is deliberate: `search_flights`/`search_hotels`' backstop (`resolve_travel_date`)
  is now numeric-only, so a word passed straight to a search tool is **rejected toward
  `resolve_date`**. Nothing previously *forced* the round-trip the audit trail depends on; now
  something does.
- A model/provider failure degrades to a ToolException → the agent asks for a concrete date. It
  fails **loudly, never silently with an invented date** — see
  [new-agent-config-node-seeds-null-model](new-agent-config-node-seeds-null-model.md), where exactly
  that happened.
- Generalizes beyond dates: any free-text → precise-value conversion (durations, party sizes,
  budgets, recurrences) should use the same split.

## Related

- [new-agent-config-node-seeds-null-model](new-agent-config-node-seeds-null-model.md)
- [supervisor-active-yaml-is-a-pointer](supervisor-active-yaml-is-a-pointer.md)
- [langgraph-thread-reset-and-prompt-reload](langgraph-thread-reset-and-prompt-reload.md)
- [../harness/verify-against-invented-rule.md](../harness/verify-against-invented-rule.md)
