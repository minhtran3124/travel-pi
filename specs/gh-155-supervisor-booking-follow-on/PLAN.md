---
slug: gh-155-supervisor-booking-follow-on
status: shipped
owner: Minh Tran
created: 2026-09-07
---

# Supervisor: no crash on a booking follow-on (#155)

## 1. Motivation

A multi-intent message whose second half is a booking made the supervisor emit `secondary_agent="booking"`, which `SupervisorIntent` rejects, so the whole turn raised `ValidationError` (eval golden `routing-multi_turn-en-01`). The user decided (design.md): bump the supervisor prompt to v11 with an explicit rule and delete the legacy `secondary_agent` field and its fallback so `plan` is the only follow-on channel. Design: `design.md`; research: `research-brief.md`.

## 2. Non-goals

- No tolerant schema for `plan` (a `plan=["booking"]` payload still raises — documented residual).
- No `try/except ValidationError` in the supervisor node.
- No paid eval run; the golden is re-checked only if the user authorises a keyed `--capability routing` run later.
- No change to any other `apps/api/app/**` file than `app/agents/supervisor.py` and `app/prompts/**`.

## Global Constraints

- Branch `fix/gh-155-supervisor-booking-follow-on` off `main`, created with `using-git-worktrees`; run backend commands from `apps/api/` of that worktree with `../../.venv/bin/python` (symlink `.venv` at the worktree root to the main checkout's `.venv` if absent, as review-b7 did).
- Prompt bump convention: copy `v10.md` → `v11.md`, edit only the lines named in Task 1.1, point `active.yaml` `supervisor: 11`, add a CHANGELOG entry at the top headed `## gh-155-supervisor-booking-follow-on — …`. Prompt edits need a graph rebuild before any live check (`docker exec api-api-1 touch app/main.py`).
- `_SecondaryTarget` stays (used by `plan`). The task-loop filter in `supervisor.py` stays as defence in depth.
- Same-wave tasks never share a file. Stage and commit as separate commands; no tooling trailers in commit messages.
- Lane high-risk (user-decided `remove-functionality`): per-task review on; the only functionality removed is the `secondary_agent` field and its fallback.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|------|-------------------------|-----------------------|------------|
| SC-1 | `SupervisorIntent` no longer has a `secondary_agent` field, and a raw payload carrying it is ignored rather than rejected | `cd apps/api && ../../.venv/bin/python -c "from app.agents.supervisor import SupervisorIntent as S;assert 'secondary_agent' not in S.model_fields;i=S.model_validate({'target_agent':'planner','secondary_agent':'booking'});assert not hasattr(i,'secondary_agent')"` | exit 0 |
| SC-2 | Every test that used the legacy field passes on `plan=[...]` | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_supervisor_plan_semantics.py tests/agents/test_task_ledger.py tests/agents/test_supervisor_slots.py tests/agents/test_multi_intent_routing.py tests/agents/test_specialist_metadata_end_to_end.py tests/agents/test_tier_gating.py -q` | exit 0 |
| SC-3 | Supervisor v11 is active, states the booking-follow-on rule, and no longer advertises the legacy field | `cd apps/api && ../../.venv/bin/python -c "from app.prompts.registry import registry;assert registry.active_version('supervisor')==11;t=open('app/prompts/supervisor/v11.md').read();assert 'secondary_agent' not in t;assert 'never a follow-on' in t"` | exit 0 |
| SC-4 | The chat router path that scripted a two-intent turn still works on `plan` | `cd apps/api && DASHBOARD_BASIC_USER= DASHBOARD_BASIC_PASSWORD= ../../.venv/bin/python -m pytest tests/api/agent/test_agent_chat.py -q -k multi_intent` | exit 0 |
| SC-5 | Prompt registry and dashboard still resolve the new version dynamically | `cd apps/api && DASHBOARD_BASIC_USER= DASHBOARD_BASIC_PASSWORD= ../../.venv/bin/python -m pytest tests/api/prompts tests/agents/test_prompt_map.py -q` | exit 0 |

The full BE suite (`pytest tests/`, ~3 min) runs at `finishing-a-development-branch`, not in a task Verify.

## 4. Tasks

### Task 1.1 — Supervisor prompt v11 (wave 1)

- **Files:** apps/api/app/prompts/supervisor/v11.md, apps/api/app/prompts/active.yaml, apps/api/app/prompts/CHANGELOG.md
- **Action:** Copy `v10.md` to `v11.md`. In the "Multi-step Plan" section: delete the three-line bullet starting "The legacy `secondary_agent` field still works" (v10 lines 123–125) and add one bullet after the existing "`plan` must **never** contain `booking`" bullet: "A booking wish inside a multi-intent message is **never a follow-on**: when reserving is the traveller's main ask, set `target_agent=booking` (no `plan`); otherwise leave the booking out of `plan` entirely — the specialist will mention that the traveller can book once they have chosen." Change `active.yaml` `supervisor: 10` → `11`. Prepend a CHANGELOG entry headed `## gh-155-supervisor-booking-follow-on — booking is never a follow-on; legacy secondary_agent retired` with one bullet for supervisor v11 (copied v10; the two edits above) and one for the code half (field + fallback removed, Task 1.2), closing with `` `active.yaml`: supervisor → 11 ``.
- **Verify:** `cd apps/api && ../../.venv/bin/python -c "from app.prompts.registry import registry;assert registry.active_version('supervisor')==11;t=open('app/prompts/supervisor/v11.md').read();assert 'secondary_agent' not in t;assert 'never a follow-on' in t;assert 'never a follow-on' in t.split('## Multi-step Plan')[1]"`
- **Done:** `v11.md` exists and differs from `v10.md` only by the removed bullet and the added bullet (`diff` shows exactly those hunks); `active.yaml` points supervisor at 11; the CHANGELOG entry is the first `## ` heading in the file.
- **Criteria:** SC-3, SC-5
- **Interfaces:** Consumes the prompt registry pointer convention (active.yaml) and v10.md. Produces `apps/api/app/prompts/supervisor/v11.md`, `apps/api/app/prompts/active.yaml` (supervisor → 11), `apps/api/app/prompts/CHANGELOG.md` (entry).

### Task 1.2 — Remove the legacy field and fallback; regression tests (wave 1)

- **Files:** apps/api/app/agents/supervisor.py, apps/api/tests/agents/test_supervisor_plan_semantics.py
- **Action:** Test first, in `test_supervisor_plan_semantics.py`: (a) rename `test_legacy_secondary_agent_is_kept` to `test_legacy_secondary_agent_is_ignored` — build the intent with `SupervisorIntent.model_validate({"target_agent": "planner", "secondary_agent": "budget"})` and assert the task agents are `["planner"]` (the key is dropped, no follow-on); (b) add `test_supervisor_intent_has_no_secondary_agent_field` asserting `"secondary_agent" not in SupervisorIntent.model_fields`; (c) add `test_raw_payload_with_secondary_booking_does_not_raise` — `model_validate({"target_agent": "planner", "secondary_agent": "booking"})` returns an intent with `plan is None`; (d) add `test_plan_with_booking_still_rejected` — `model_validate({"target_agent": "planner", "plan": ["booking"]})` raises `pydantic.ValidationError` (documents the residual). Then in `supervisor.py`: delete the `secondary_agent` field (lines 69–79) and the fallback (`else: legacy = getattr(...)` — make it `candidates = list(raw_plan or [])`), and trim the comment block above the loop to drop the "fall back to the legacy single `secondary_agent`" sentence. Keep `_SecondaryTarget`. Update the `plan` field description's last sentence to mention it is the only follow-on channel.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_supervisor_plan_semantics.py -q`
- **Done:** the four tests pass; `grep -n secondary_agent app/agents/supervisor.py` returns no line; `ruff check app/agents/supervisor.py tests/agents/test_supervisor_plan_semantics.py` reports 0 findings.
- **Criteria:** SC-1
- **Interfaces:** Consumes pydantic's default extra=ignore behaviour on the SupervisorIntent model and the existing task-loop filter (both pre-existing). Produces `apps/api/app/agents/supervisor.py` (no `secondary_agent`), `apps/api/tests/agents/test_supervisor_plan_semantics.py` (4 regression tests).

### Task 2.1 — Migrate task-ledger and slot tests to `plan` (wave 2)

- **Files:** apps/api/tests/agents/test_task_ledger.py, apps/api/tests/agents/test_supervisor_slots.py
- **Action:** `test_task_ledger.py:197-205`: rename `test_null_plan_falls_back_to_legacy_secondary` to `test_one_item_plan_yields_two_tasks`, drop the legacy construction, keep the assertion on `["planner","concierge"]` for `plan=["concierge"]`. `test_supervisor_slots.py`: line 128 `secondary_agent="concierge"` → `plan=["concierge"]` (test name `…forces_secondary…` → `…forces_plan_to_empty…`, assertion `["booking"]` unchanged); line 145 → `plan=["concierge"]` (assertion `["planner","concierge"]` unchanged); line 161 → `plan=["planner"]` (rename to `test_plan_step_equal_to_target_is_dropped`, assertion `["planner"]` unchanged).
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_task_ledger.py tests/agents/test_supervisor_slots.py -q`
- **Done:** both files pass; `grep -c secondary_agent` on each returns 0.
- **Criteria:** SC-2
- **Interfaces:** Consumes `apps/api/app/agents/supervisor.py` from Task 1.2. Produces `apps/api/tests/agents/test_task_ledger.py`, `apps/api/tests/agents/test_supervisor_slots.py` (plan-based).

### Task 2.2 — Migrate routing, metadata and tier-gating tests to `plan` (wave 2)

- **Files:** apps/api/tests/agents/test_multi_intent_routing.py, apps/api/tests/agents/test_specialist_metadata_end_to_end.py, apps/api/tests/agents/test_tier_gating.py
- **Action:** Replace every `SupervisorIntent(target_agent="planner", secondary_agent="concierge")` (routing.py lines 44, 73, 193; metadata.py line 29) with `plan=["concierge"]`, and `SupervisorIntent(target_agent="concierge", secondary_agent="planner")` (tier_gating.py lines 190, 215) with `plan=["planner"]`. Assertions stay as they are (`current_flow == "synthesize"`, cleared results, tier gating dropping the gated step).
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_multi_intent_routing.py tests/agents/test_specialist_metadata_end_to_end.py tests/agents/test_tier_gating.py -q`
- **Done:** the three files pass; `grep -c secondary_agent` on each returns 0.
- **Criteria:** SC-2
- **Interfaces:** Consumes `apps/api/app/agents/supervisor.py` from Task 1.2. Produces `apps/api/tests/agents/test_multi_intent_routing.py`, `apps/api/tests/agents/test_specialist_metadata_end_to_end.py`, `apps/api/tests/agents/test_tier_gating.py` (plan-based).

### Task 2.3 — Migrate the chat router tests to `plan` (wave 2)

- **Files:** apps/api/tests/api/agent/test_agent_chat.py
- **Action:** Lines 240 and 294: `secondary_agent="concierge"` → `plan=["concierge"]`; assertions unchanged.
- **Verify:** `cd apps/api && DASHBOARD_BASIC_USER= DASHBOARD_BASIC_PASSWORD= ../../.venv/bin/python -m pytest tests/api/agent/test_agent_chat.py -q`
- **Done:** file passes; `grep -c secondary_agent tests/api/agent/test_agent_chat.py` returns 0.
- **Criteria:** SC-4
- **Interfaces:** Consumes `apps/api/app/agents/supervisor.py` from Task 1.2. Produces `apps/api/tests/api/agent/test_agent_chat.py` (plan-based).

### Task 3.1 — Evidence and record (wave 3)

- **Files:** specs/gh-155-supervisor-booking-follow-on/SUMMARY.md
- **Action:** Run SC-1…SC-5 and `cd apps/api && grep -rn secondary_agent app tests` (expect no match outside `app/prompts/supervisor/v6.md`–`v10.md` history and CHANGELOG). Fill `### Verify` (one row per SC with `Criterion`), `### Deviations`, `### Not auto-verified` (live model behaviour after v11 not re-run; residual `plan=["booking"]` exposure), `### Rollback` (`git revert` of the commits; `active.yaml` back to 10 restores v10 without deleting v11), and `## What changed`.
- **Verify:** `python3 ../../../.claude/scripts/verify_summary.py --lane specs/gh-155-supervisor-booking-follow-on/SUMMARY.md`
- **Done:** lane check exits 0; every SC id appears in a passing Verify row.
- **Criteria:** SC-1, SC-2, SC-3, SC-4, SC-5
- **Interfaces:** Consumes the outputs of Tasks 1.1–2.3. Produces `specs/gh-155-supervisor-booking-follow-on/SUMMARY.md` (evidence).

## 5. Risks

- **Residual crash path** — `plan=["booking"]` still raises; documented by Task 1.2 test (d). If the eval shows it recurring, open a follow-up for a tolerant schema.
- **Model still emits the retired key** — harmless: pydantic drops it (SC-1), the follow-on is simply not queued.
- **Prompt not reloaded in the dev container** — any manual check must rebuild the graph first (Global Constraints).
- **Other in-flight specs editing the same test files** — `gh-146` touches `nodes.py` and a new test file only; no overlap.
- **Self-review only** — the fork that wrote this plan could not dispatch an independent plan reviewer; the controller should run one pass of the plan-document-reviewer before execution.

## 6. Status Log

- 2026-09-07 — plan written (xia2 Standard + writing-plans) after design approval; contract checker passed; self-reviewed against the plan-reviewer checklist (fork could not dispatch an independent reviewer — see §5); not yet executed.
- 2026-09-07 — design approved (spec reviewer ✅), research-brief Standard, PLAN reviewed ✅ (independent pass); not yet executed
- 2026-09-07 — tasks 1.1, 1.2 complete; commits 75011f0, a719bde (reviews pass/approved)
- 2026-09-07 — tasks 2.1, 2.2, 2.3 complete; commit 4aa0354 (review pass/approved); task 3.1 SUMMARY evidence written
- 2026-09-07 — shipped: review chain complete, receipt at 62f8f77, PR opened → main
