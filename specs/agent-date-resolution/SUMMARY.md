# agent-date-resolution — Summary

Lane: high-risk
Confidence: high
Reason: Four risk flags fire (public contract · existing behavior · weak proof · multi-domain) and the new `resolve_date` agent tool is additive client-visible surface (`/agent/manifest` + MCP tool list), so the public-contract gate applies — additive superset only, no route/envelope change.
Flags: public-contract (additive), existing-behavior, weak-proof, multi-domain
Affects: app/tools/registry.py (agent tool surface → /agent/manifest + MCP), app/core/dates.py, app/prompts/booking + supervisor
Input-type: change request

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> "now, i want to improve that agent dont need to ask the user to confirm about date time.
> But we need to find the way help to check the date/time correctly without any guess or pick random."

Two forks resolved by the user at intake (`AskUserQuestion`):

- **No-date case** — "Vẫn hỏi khi thiếu hẳn ngày": when the traveller gives *no* date signal at
  all, the agent still asks one question. Only the redundant *re-confirmation* of a date the agent
  already resolved is removed.
- **Correctness** — "Thêm tool resolve_date riêng, agent phải gọi trước": a dedicated deterministic
  tool computes the date (code, not LLM arithmetic) and the agent must call it before searching, so
  the resolution is verifiable in the tool trace.

## What changed

<pending — filled at completion>

### Rationale

The agent's date friction has two distinct causes and only one is a prompt problem. (1)
`app/prompts/booking/v5.md` step 1 orders a "single yes/no confirmation before you call the tool" —
that is a confirmation turn before a *search/quote*, which is pure friction. (2) `app/core/dates.py`
deliberately does **not** parse weekday/phrase forms ("next Friday", "cuối tuần này"), leaving that
arithmetic to the LLM where nothing can check it — that is the "guess" the user wants eliminated.
Fixing only the prompt would remove the ask while leaving the unverifiable arithmetic in place, so
both are addressed: `resolve_date` makes the computation deterministic and auditable in the tool
trace, and the prompt then trusts it instead of asking the human to double-check the model's math.
Approval before an actual **booking** is untouched — that gate is about money, not about dates.

### Alternatives considered

- **Date-less / range search** (browse a 7-day window, let the traveller pick) — rejected by the
  user at intake; keeps the "still ask when no date at all" semantics instead.
- **Publicly-stated default date** (e.g. assume today, say so) — deterministic but still chooses for
  the traveller; rejected at intake.
- **Prompt-only fix** (drop the "ask" rule, keep LLM date math) — cheapest, but it is exactly the
  unverifiable guessing the request asks to remove.
- **Extend `resolve_travel_date` in-place without a tool** — the resolution would stay invisible to
  the trace; the user explicitly chose the callable tool for auditability.

### Deviations

- none

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Resolver unit (task 1.1) | `cd apps/api && ../../.venv/bin/python -m pytest tests/core/test_dates.py -q` | 0 | 51 passed |
| Resolver lint (task 1.1) | `cd apps/api && ruff check app/core/dates.py tests/core/test_dates.py` | 0 | clean |
| Resolver spot-check vs a known Saturday (today = Sat 2026-07-11) | ad-hoc REPL over 18 expressions | 0 | "thứ 6 tuần sau"→2026-07-24(Fri) · "friday"→07-17 · "thứ 7"→07-18 (strictly-future) · "cuối tuần này"→07-18(Sat) · "tuần sau"→07-13(Mon) · "3 ngày nữa"→07-14 · "sometime soon"/"07/2026"→AmbiguousDateError |

### Rollback

- Revert code: `git revert <sha>`
- Prompt rollback is independent of code: set `booking`/`supervisor` back to their prior versions in
  `app/prompts/active.yaml` (versioned prompts, old files retained) and rebuild the graph.

### Harness-Delta

- none
