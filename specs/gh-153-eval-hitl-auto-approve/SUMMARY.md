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

- `Golden.hitl: Literal["approve","reject"] | None` (additive, validated at dataset load).
- `LangGraphRunner.run` reads `out["__interrupt__"]` after every turn, records `{type, draft, turn}` into `Trace.meta["interrupts"]` (always present), and — only when `golden.hitl` is set — resumes once per turn with `Command(resume={"approved": hitl == "approve"})` on the same thread, mirroring `routers/agent.py:385`.
- 12 booking-flow goldens carry `hitl: approve`; `booking-ambiguous-*` / `errors-ambiguous-en-01` stay opt-out (their right answer is a clarifying reply). README documents the field, `meta.interrupts`, and the multi-turn caveat.
- Paid full run (k=3, premium+authenticated): **67/84** (was 58/84); 11 of the 12 `hitl` goldens now pass, including `booking-tool_failure-vi-01` whose NotFound scenario is exercised for the first time. Baseline regenerated (`eval/baselines/main.json`); triage in `TRIAGE.md`.

### Rationale

The interrupt is the product's HITL design, not a bug; the eval harness simply lacks the second half of the conversation the router provides. Resuming inside the runner mirrors `routers/agent.py:385` exactly and touches no app code. Because it flips up to 17 baseline cases, the baseline must be regenerated in the same change (paid run), which is why this is a planned initiative rather than a patch.

### Alternatives considered

- Mark booking goldens `metrics: []` / drop them — hides the gap instead of closing it; rejected.
- Auto-approve every interrupt unconditionally — simpler, but loses the ability to grade the 'ask which hotel' clarification path (booking-ambiguous-*), which should NOT be approved blindly; per-golden opt-in keeps both.

### Deviations

- Rule 1 — Task 1.2: the implementer read `evalkit/types.py` mid-edit (Task 1.1 in flight) and worked around a transient broken field with `Golden.model_construct` in the test helper; the controller restored validated `Golden(**defaults)` before committing (15 passed). Commit 4eff7fe.
- Rule 2 — after task reviews 1.2/1.3: README wording "one per interrupted turn" + the multi-turn-must-set-`hitl` caveat. Commit 7df9785.
- Rule 3 — Task 1.1: the ruff-on-edit hook mangled the `Literal[...]` edit; the implementer re-applied it (memory: ruff-on-edit-strips-unused-imports). Commit bab3557.
- Task 3.1: the first paid attempt was killed mid-run after `api-db-1`/`api-api-1` stopped (external `docker compose down`); stack restarted with `docker compose up -d`, run repeated — only attempt 2 is used.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| Trigger corroborated (intake) | `<intake-era: grep -n 'Command(resume' apps/api/eval/adapters/langgraph_runner.py returned exit 1 before the fix>` | 1 | the runner never resumed | |
| SC-1 A booking golden without `hitl` still yields an empty reply and record | `cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_langgraph_runner.py -q -k "interrupt and not approve and not reject"` | 0 | 1 passed, 12 deselected, 1 warning in 0.06s | SC-1 |
| SC-2 A golden with `hitl: approve` resumes and the trace carries the post-a | `cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_langgraph_runner.py -q -k "hitl_approve"` | 0 | 1 passed, 12 deselected, 1 warning in 0.06s | SC-2 |
| SC-3 A golden with `hitl: reject` captures the cancellation path | `cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_langgraph_runner.py -q -k "hitl_reject"` | 0 | 1 passed, 12 deselected, 1 warning in 0.05s | SC-3 |
| SC-4 `Golden.hitl` accepts approve/reject and rejects a typo at load | `cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_datasets.py -q -k hitl` | 0 | 2 passed, 22 deselected, 1 warning in 0.02s | SC-4 |
| SC-5 Twelve goldens carry `hitl: approve`, no other golden carries `hitl` | `cd apps/api && ../../.venv/bin/python -c "import json,glob;h=[g['id'] for f in glob.glob('eval/datasets/*.json') for g in json.load(open(f)) if g.get('hitl')];assert len(h)==12 and all(g.get('hitl')=='approve' for f in glob.glob('eval/datasets/*.json') for g in json.load(open(f)) if g.get('hitl')),h"` | 0 |  | SC-5 |
| SC-6 The full-suite dry-run still lists 84 goldens keyless | `cd apps/api && OPENAI_API_KEY= ../../.venv/bin/python -m eval --suite full --dry-run` | 0 |   suggestions-happy-en-05  suggestions/happy  metrics=[flow_match, suggestion_re | SC-6 |
| SC-7 The baseline was regenerated after the change from a full k=3 run | `cd apps/api && ../../.venv/bin/python -c "import json;r=json.load(open('eval/baselines/main.json'));m=r['run_meta'];assert m['suite']=='full' and m['repeat']==3 and m['summary']['total_cases']==84,m;b=[c for c in r['per_case'] if c['golden_id']=='booking-happy-en-01'][0];assert any(k['name']=='non_empty_reply' and k['passed'] for k in b['checks']),b"` | 0 |  | SC-7 |
| SC-8 The gate accepts the regenerated baseline | `cd apps/api && mkdir -p eval/reports && cp eval/baselines/main.json eval/reports/latest.json && make eval-compare` | 0 | tolerance=5.0%  exit_code=0 | SC-8 |
| SC-9 README documents `hitl` and `meta.interrupts` | `grep -c -e "hitl" -e "meta.interrupts" apps/api/eval/README.md` | 0 | 11 | SC-9 |
| Task 3.1 paid run (attempt 2; attempt 1 aborted when the Docker stack was stopped externally) | `<paid run, not re-run under --check: cd apps/api && make eval-full>` | 2 | 67/84; make exits 2 while budget/hotels/journal sit below threshold; report is the new baseline | SC-7 |
| Full BE suite at finish (fresh SQLite, `.env` present) | `<not re-run under --check (314s): cd apps/api && DATABASE_URL=sqlite:////tmp/x.db DASHBOARD_BASIC_USER= DASHBOARD_BASIC_PASSWORD= LANGFUSE_ENABLED=false ../../.venv/bin/python -m pytest tests/ -q>` | 1 | 2271 passed, 5 failed — all five (`test_config_llm` ×2, `test_embeddings`, `test_routing_tools` ×2) are the known `.env`-real-key group (memory: env-openai-key-test-breaks-llm-tests); with `.env` renamed they pass: 21 passed; no diff vs main under tests/core, tests/tools, app/core, app/tools | |
| tests/eval whole (cited) | `cd apps/api && ../../.venv/bin/python -m pytest tests/eval -q` | 0 | see status log | |

### Not auto-verified

- `dates-multi_turn-vi-01` still fails (`flow_match` booking vs concierge) — routing variance, not a resume defect; kept with its issue note. Judged variance beyond k=3 (two pass↔fail flips vs the previous baseline) is absorbed by the tolerance gate. The `reject` path is covered only by the FakeLLM test (no golden uses `hitl: reject`).

### Advisory Findings

Correctness review (b8404a8..9e77dd6; enclosing-function, guard-completeness, stack-defects angles), independent scoring, threshold 75:

- score 25 — `apps/api/eval/adapters/langgraph_runner.py:188-218`: a multi-turn golden whose NON-final turn interrupts with `hitl` unset sends the next turn onto a parked thread; LangGraph abandons the paused step and the trace grades a post-abandon conversation (reproduced by the finder with a FakeLLM). Not silent (`meta.interrupts` lists both turns), documented as the README caveat, and no current golden has a mid-sequence booking intent. Follow-up: `break` out of the turn loop when an interrupt is pending and `hitl` is unset.
- score 0 (unmodified line) — `apps/api/evalkit/types.py:50-58`: the input/turns xor validator accepts `turns: []`, which then yields an empty trace as if the golden ran. Pre-existing; reject empty lists in a later pass.

### Intent Findings

Intent review (plan-blind): no gap/drift/excess. One doc note — design.md SC-1..SC-4 map onto PLAN/SUMMARY rows as: design SC-1 → SC-1/2/3 (runner tests); design SC-2 → SC-6 dry-run + `tests/eval` whole; design SC-3 → SC-7 baseline (booking 6/8, was 2/8); design SC-4 → SC-8 compare exit 0.

### Rollback

- `git revert` the branch commits on `fix/gh-153-eval-hitl-auto-approve` (baseline commit first, then af27f9b 7df9785 4eff7fe 076f3ac bab3557); the previous baseline is `eval/reports/baseline-before-153.json` (untracked) or `main.json` at f94e52b on `feat/agent-eval-pipeline`.

### Harness-Delta

- none
