# gh-155-supervisor-booking-follow-on — Summary

Lane: high-risk
Confidence: high
Reason: judgment hard gate `remove-functionality` — the user decided at intake (brainstorming, 2026-09-07) to delete the legacy `SupervisorIntent.secondary_agent` field and its fallback (`supervisor.py:313`), alongside a supervisor prompt bump to v11 with an explicit rule. Plus 2 flags (existing behavior; weak proof — LLM-decided trigger, reproduced 1/3 runs). Direction fixed by the user, so confidence is high.
Flags: existing behavior, weak proof
Affects: apps/api/app/agents/supervisor.py (`SupervisorIntent`, `_SecondaryTarget`), apps/api/app/prompts/supervisor/* (+ active.yaml, CHANGELOG) if the prompt route is chosen, apps/api/tests/agents/*
Input-type: change request (bug #155)
Route: high-risk (human-narrowed) — brainstorming → xia2 (Standard) → writing-plans → using-git-worktrees (branch `fix/gh-155-supervisor-booking-follow-on` off `main`) → subagent-driven-development.
Escalate: no — the remove-functionality gate was decided by the user in brainstorming: option "B + bỏ field legacy secondary_agent" (prompt v11 rule for booking follow-ons + delete the legacy `secondary_agent` field; `plan` is the sole follow-on channel). Recorded here in lieu of an ESCALATIONS block because the human made the call synchronously.

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> cho bug agent #155, #146, #153. each item make design + plan to fix - new branch for each fixing

Issue #155 (opened 2026-09-07 from the review-b7 eval run 2): golden `routing-multi_turn-en-01` — turn 1 "Search flights from Ho Chi Minh City to Bangkok", turn 2 "Also remind me to pack sunscreen and book the cheapest one". The supervisor's structured output set `secondary_agent='booking'`, which `SupervisorIntent` forbids (`_SecondaryTarget = Literal["planner","concierge","journal","budget"]`, supervisor.py:36), so `graph.invoke` raised `ValidationError` and the whole turn errored; a user would get a 500/empty reply.

## What changed

Intake only. No implementation edits.

### Rationale

A crash on a legitimate multi-intent phrasing is a Rule-1-class defect; the v10 prompt only says a booking *target* has no follow-ons, and the Python task filter (supervisor.py:315-330) already drops `booking` steps — the schema is stricter than the code that consumes it. Two credible fixes (widen the schema and rely on the filter; or forbid it in the prompt), so a short design is warranted as the user asked.

### Alternatives considered

- Prompt-only fix (v11 rule 'never queue booking as a follow-on') — cannot make a structured-output call crash-proof; LLMs violate prompt rules, and the golden shows this one does.
- Catch `ValidationError` in the supervisor node and fall back to single-intent — broader safety net, but hides malformed output; can be a second layer, not the primary fix.

### Deviations

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| Trigger corroborated | `grep -n '_SecondaryTarget = Literal' apps/api/app/agents/supervisor.py` | 0 | line 36 forbids booking; the eval report `eval/reports/run2.json` on branch feat/agent-eval-pipeline carries the `agent_run` ValidationError detail for routing-multi_turn-en-01 | |

### Not auto-verified

- Reproduction is nondeterministic (1 of 3 judged runs); the fix must be proven with a FakeLLM-scripted `SupervisorIntent`-shaped raw payload containing `secondary_agent='booking'`, not by re-running the paid eval.

### Rollback

- Intake only: `rm -rf specs/gh-155-supervisor-booking-follow-on/`. Implementation: `git revert <sha>` on the fix branch.

### Harness-Delta

- none
