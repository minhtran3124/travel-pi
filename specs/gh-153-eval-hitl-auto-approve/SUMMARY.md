# gh-153-eval-hitl-auto-approve — Summary

Lane: normal
Confidence: medium
Reason: 3 flags (existing behavior — changes what the eval baseline measures for 17 booking-flow goldens; weak proof — the resume path is exercised only by a real graph run; external systems — a paid judged re-baseline is required after the change). No manifest hard gate: eval code only, no app/** change. Multi-file (runner, Golden field, datasets, baseline, tests).
Flags: existing behavior, weak proof, external systems
Affects: apps/api/eval/adapters/langgraph_runner.py (`LangGraphRunner.run` turn loop, lines 183-196), apps/api/evalkit/types.py (`Golden`, additive field), apps/api/eval/datasets/*.json (booking-flow goldens), apps/api/eval/baselines/main.json, apps/api/tests/eval/*
Input-type: change request (eval gap #153)
Route: normal, user asked for design + plan — brainstorming → xia2 (Standard) → writing-plans → using-git-worktrees → subagent-driven-development. Branch `fix/gh-153-eval-hitl-auto-approve` must be cut from `feat/agent-eval-pipeline` (PR #157) until that PR merges — the eval runner does not exist on `main`.
Escalate: no (medium confidence: safe default is an opt-in per-golden resume — `hitl: approve|reject` — that sends `Command(resume={"approved": True})` when the run stops at a `plan_approval` interrupt; the forks are approve-all vs per-golden, and whether the rejected path is also graded). The paid re-baseline is a spend the user must OK at plan time.

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> cho bug agent #155, #146, #153. each item make design + plan to fix - new branch for each fixing

Issue #153 (opened 2026-09-07 from the review-b7 eval run): every booking-flow golden (booking-*, errors-ambiguous-en-01, errors-tool_failure-vi-01, dates-multi_turn-*, routing-ambiguous-en-01, suggestions-happy-*-04 — 17 goldens with `expected_flow: booking`) ends at the `plan` node's `interrupt({"type": "plan_approval", "draft": <user text>})` (nodes.py:275): `Trace.reply == ''`, no tool call, so `tools_expected` / `non_empty_reply` can never pass and the NotFound / graceful-failure scenarios are never exercised. The runner's turn loop (langgraph_runner.py:183-196) only ever sends `HumanMessage` payloads; the production router resumes with `Command(resume=body.resume)` (routers/agent.py:385). Proposed: `LangGraphRunner` resumes with `Command(resume={"approved": True})` when the run interrupts, opt-in per golden, so the booking path is graded.

## What changed

Intake only. No implementation edits.

### Rationale

The interrupt is the product's HITL design, not a bug; the eval harness simply lacks the second half of the conversation the router provides. Resuming inside the runner mirrors `routers/agent.py:385` exactly and touches no app code. Because it flips up to 17 baseline cases, the baseline must be regenerated in the same change (paid run), which is why this is a planned initiative rather than a patch.

### Alternatives considered

- Mark booking goldens `metrics: []` / drop them — hides the gap instead of closing it; rejected.
- Auto-approve every interrupt unconditionally — simpler, but loses the ability to grade the 'ask which hotel' clarification path (booking-ambiguous-*), which should NOT be approved blindly; per-golden opt-in keeps both.

### Deviations

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| Trigger corroborated | `grep -n 'Command(resume' apps/api/eval/adapters/langgraph_runner.py` | 0 | exit 1 today on branch feat/agent-eval-pipeline — the runner never resumes; interrupt payload verified live during review-b7 task 3.2 (`graph.get_state(cfg).tasks[0].interrupts` → plan_approval) | |

### Not auto-verified

- Re-baseline after the change requires a full judged run (84 agent turns + ~105 judge calls) — a user-authorised spend, not part of intake.

### Rollback

- Intake only: `rm -rf specs/gh-153-eval-hitl-auto-approve/`. Implementation: `git revert <sha>` on the fix branch.

### Harness-Delta

- none
