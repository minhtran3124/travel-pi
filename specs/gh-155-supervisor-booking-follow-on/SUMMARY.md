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

- Supervisor prompt bumped to **v11** (`app/prompts/supervisor/v11.md`, `active.yaml`, CHANGELOG): the legacy "`secondary_agent` still works" sentence is gone and the Multi-step Plan rules state that a booking wish inside a multi-intent message is never a `plan` step.
- `SupervisorIntent.secondary_agent` and its fallback in `app/agents/supervisor.py` are deleted; `plan` is the only follow-on channel (`candidates = list(raw_plan or [])`); the booking/unknown/tier filter in the task loop is unchanged. A raw payload still carrying `secondary_agent` is silently ignored (pydantic default `extra="ignore"`), so the #155 crash cannot recur through that field.
- Regression tests in `tests/agents/test_supervisor_plan_semantics.py` (no field, legacy key ignored, `plan=["booking"]` still rejected — the documented residual — single-task plan); six other test files migrated from `secondary_agent=` to `plan=[…]` with their assertions unchanged.

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
| Trigger corroborated (intake) | `grep -n '_SecondaryTarget = Literal' apps/api/app/agents/supervisor.py` | 0 | still present (types `plan`); the crash path was the now-deleted `secondary_agent` field | |
| SC-1 field gone, legacy key ignored | `cd apps/api && ../../.venv/bin/python -c "from app.agents.supervisor import SupervisorIntent as S;assert 'secondary_agent' not in S.model_fields;i=S.model_validate({'target_agent':'planner','secondary_agent':'booking'});assert not hasattr(i,'secondary_agent')"` | 0 | | SC-1 |
| SC-2 migrated tests | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_supervisor_plan_semantics.py tests/agents/test_task_ledger.py tests/agents/test_supervisor_slots.py tests/agents/test_multi_intent_routing.py tests/agents/test_specialist_metadata_end_to_end.py tests/agents/test_tier_gating.py -q` | 0 | 66 passed | SC-2 |
| SC-3 v11 active + rule text | `cd apps/api && ../../.venv/bin/python -c "from app.prompts.registry import registry;assert registry.active_version('supervisor')==11;t=open('app/prompts/supervisor/v11.md').read();assert 'secondary_agent' not in t;assert 'never' in t"` | 0 | | SC-3 |
| SC-4 chat router two-intent path | `cd apps/api && DASHBOARD_BASIC_USER= DASHBOARD_BASIC_PASSWORD= ../../.venv/bin/python -m pytest tests/api/agent/test_agent_chat.py -q -k multi_intent` | 0 | 2 passed | SC-4 |
| SC-5 registry + dashboard | `cd apps/api && DASHBOARD_BASIC_USER= DASHBOARD_BASIC_PASSWORD= ../../.venv/bin/python -m pytest tests/api/prompts tests/agents/test_prompt_map.py -q` | 0 | 47 passed | SC-5 |
| tests/agents whole (cited) | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents -q` | 0 | 396 passed | |

### Not auto-verified

- The original trigger (model emits `secondary_agent='booking'`) is proven closed by SC-1 (raw payload ignored). The residual `plan=["booking"]` ValidationError is documented by `test_plan_with_booking_still_rejected`, not fixed. The running dev container must be rebuilt (`docker exec api-api-1 touch app/main.py`) for v11 to take effect — not done from this branch. A keyed re-run of `routing-multi_turn-en-01` is user spend, not run.

### Rollback

- `git revert 4aa0354 a719bde 75011f0` on `fix/gh-155-supervisor-booking-follow-on` (restores the field, the fallback, the tests and points active.yaml back at v10).

### Harness-Delta

- none
