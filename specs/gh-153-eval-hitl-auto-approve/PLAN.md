---
slug: gh-153-eval-hitl-auto-approve
status: active
owner: Minh Tran
created: 2026-09-07
---

# Eval runner resumes the HITL plan-approval interrupt (opt-in per golden)

## 1. Motivation

Seventeen booking-flow goldens stop at `plan_node`'s `plan_approval` interrupt: empty reply, no tool call, so `non_empty_reply` / `tools_expected` can never pass and the booking sub-agent is never graded (issue #153, review-b7 baseline 58/84). Production resumes the graph with `Command(resume={"approved": …})` (`app/routers/agent.py:385`); the eval runner never does. Design: `design.md` (approved). Research: `research-brief.md` (Standard).

## 2. Non-goals

- No `apps/api/app/**` change — the product's HITL behaviour (interrupting on vague requests instead of clarifying) stays; `booking-ambiguous-*` / `errors-ambiguous-en-01` keep their open issue.
- No judged eval on CI (E002 of review-b7); the re-baseline is a local paid run.
- No change to `evalkit/` beyond the additive `Golden.hitl` field (boundary test stays).

## Global Constraints

- Branch `fix/gh-153-eval-hitl-auto-approve` is cut from `feat/agent-eval-pipeline` (PR #157) — the runner does not exist on `main`. Work in a worktree; at the worktree root run `ln -s ../../../.venv .venv` once so `../../.venv/bin/python` and `make` resolve from `apps/api/`.
- Wave 3 needs `apps/api/.env` copied from the main checkout (gitignored, never committed) and Docker `api-db-1` up. The copied `.env` breaks `monkeypatch.delenv` tests and dashboard basic-auth tests — set those vars empty when running suites outside `tests/eval`.
- Every schema change is additive; `Report` shape untouched. Golden ids unchanged.
- The paid full run (≈ 84 agent turns + ~105 judge calls) is a single task (3.1) and starts only after the user says go in that session.
- Stage and commit as separate commands; no tooling trailers in commit messages.
- Harness scripts: from the worktree root `../../../.claude/scripts/<script>.py`; from `apps/api/` `../../../../../.claude/scripts/<script>.py`.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|------|-------------------------|-----------------------|------------|
| SC-1 | A booking golden without `hitl` still yields an empty reply and records the interrupt in `meta.interrupts` | `cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_langgraph_runner.py -q -k "interrupt and not approve and not reject"` | exit 0 |
| SC-2 | A golden with `hitl: approve` resumes and the trace carries the post-approval reply | `cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_langgraph_runner.py -q -k "hitl_approve"` | exit 0 |
| SC-3 | A golden with `hitl: reject` captures the cancellation path | `cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_langgraph_runner.py -q -k "hitl_reject"` | exit 0 |
| SC-4 | `Golden.hitl` accepts approve/reject and rejects a typo at load | `cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_datasets.py -q -k hitl` | exit 0 |
| SC-5 | Twelve goldens carry `hitl: approve`, no other golden carries `hitl` | `cd apps/api && ../../.venv/bin/python -c "import json,glob;h=[g['id'] for f in glob.glob('eval/datasets/*.json') for g in json.load(open(f)) if g.get('hitl')];assert len(h)==12 and all(g.get('hitl')=='approve' for f in glob.glob('eval/datasets/*.json') for g in json.load(open(f)) if g.get('hitl')),h"` | exit 0 |
| SC-6 | The full-suite dry-run still lists 84 goldens keyless | `cd apps/api && OPENAI_API_KEY= ../../.venv/bin/python -m eval --suite full --dry-run` | exit 0 |
| SC-7 | The baseline was regenerated after the change from a full k=3 run | `cd apps/api && ../../.venv/bin/python -c "import json;r=json.load(open('eval/baselines/main.json'));m=r['run_meta'];assert m['suite']=='full' and m['repeat']==3 and m['summary']['total_cases']==84,m;b=[c for c in r['per_case'] if c['golden_id']=='booking-happy-en-01'][0];assert any(k['name']=='non_empty_reply' and k['passed'] for k in b['checks']),b"` | exit 0 — the resumed booking golden has a non-empty reply in the baseline |
| SC-8 | The gate accepts the regenerated baseline | `cd apps/api && mkdir -p eval/reports && cp eval/baselines/main.json eval/reports/latest.json && make eval-compare` | exit 0 |
| SC-9 | README documents `hitl` and `meta.interrupts` | `grep -c -e "hitl" -e "meta.interrupts" apps/api/eval/README.md` | exit 0 |

`tests/eval` as a whole and the full BE suite run at `finishing-a-development-branch`, not in a task Verify.

## 4. Tasks

### Task 1.1 — `Golden.hitl` field and dataset validation test (wave 1)

- **Files:** apps/api/evalkit/types.py, apps/api/tests/eval/test_datasets.py
- **Action:** Test first: add `test_hitl_accepts_approve_and_reject` (construct `Golden(..., hitl="approve")` and `"reject"`) and `test_hitl_rejects_unknown_value` (`JsonDatasetStore` over a tmp dir with `hitl: "aprove"` raises a validation error naming the file and case — follow `test_unknown_metric_raises_naming_file_case_and_metric`). Then add `hitl: Literal["approve", "reject"] | None = None` to `Golden` after `expected_tasks`, with a one-line comment: opt-in resume of the plan-approval interrupt; the adapter owns the mechanics.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_datasets.py tests/eval/test_boundary.py tests/eval/test_types.py -q`
- **Done:** New tests pass; `test_boundary.py` passes (no `app.*` import in `evalkit/`); `ruff check evalkit` reports 0 findings.
- **Criteria:** SC-4
- **Interfaces:** Consumes the existing Golden model and JsonDatasetStore validation (unchanged). Produces `evalkit/types.py` (Golden.hitl), `tests/eval/test_datasets.py` (hitl tests).

### Task 1.2 — Runner resumes the interrupt and records it in `Trace.meta` (wave 1)

- **Files:** apps/api/eval/adapters/langgraph_runner.py, apps/api/tests/eval/test_langgraph_runner.py
- **Action:** Test first, copying the FakeLLM recipe of `tests/agents/test_hitl_plan.py` into `_build_runner(target="booking", answer="Hotel booked!")`: (a) `test_booking_interrupt_is_recorded_without_hitl` — golden without `hitl`: `trace.reply == ""`, `trace.meta["interrupts"] == [{"type": "plan_approval", "draft": <input>, "turn": 0}]`; (b) `test_hitl_approve_resumes_and_captures_reply` — `hitl="approve"`: `"Hotel booked" in trace.reply` and `meta["interrupts"]` still holds the one recorded interrupt; (c) `test_hitl_reject_captures_cancellation` — `hitl="reject"`: `"cancelled" in trace.reply.lower()` and no `"Hotel booked"`. Then in `LangGraphRunner.run`, after each `graph.invoke`: `pending = [i.value for i in out.get("__interrupt__", ()) if isinstance(getattr(i, "value", None), dict) and i.value.get("type") == "plan_approval"]`; for the first pending value append `{"type", "draft", "turn": i}` to a local `interrupts` list; if `golden.hitl` is set, `out = self._graph.invoke(Command(resume={"approved": golden.hitl == "approve"}), cfg, context=self._context)` (import `Command` from `langgraph.types`); at most one resume per turn. Add `"interrupts": interrupts` to `meta` (always present, `[]` when none). Read `__interrupt__` from the invoke output — the same key `app/routers/agent.py:440` reads — never `get_state`.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_langgraph_runner.py -q -k "interrupt or hitl"`
- **Done:** Tests (a)(b)(c) pass; the existing runner tests still pass (`-k "not interrupt and not hitl"` also exit 0); `ruff check eval tests/eval/test_langgraph_runner.py` reports 0 new findings (the file has a pre-existing I001/F811 import finding — leave it).
- **Criteria:** SC-1, SC-2, SC-3
- **Interfaces:** Consumes `evalkit/types.py` from Task 1.1 (Golden.hitl), the graph output key __interrupt__ (langgraph 1.2.6 Interrupt.value), and the plan node's resume contract {approved: bool} at app/agents/nodes.py line 275 (unchanged). Produces `eval/adapters/langgraph_runner.py` (resume + meta.interrupts), `tests/eval/test_langgraph_runner.py`.

### Task 1.3 — README: `hitl` and `meta.interrupts` (wave 1)

- **Files:** apps/api/eval/README.md
- **Action:** In the golden-fields list add `hitl` (`approve` | `reject`, optional; when the graph stops at the plan-approval interrupt the runner resumes with that decision, exactly like the chat API; without it the trace keeps the empty reply so `non_empty_reply` reports the interrupt honestly). Add a short section after "`expected_tasks` and the `tasks_expected` metric" describing `Trace.meta["interrupts"]` (`type`, `draft`, `turn`) and which goldens opt in and why the ambiguous ones do not (their pass condition is a clarifying reply). Note that changing `hitl` on a golden requires a baseline refresh.
- **Verify:** `grep -c -e "hitl" -e "meta.interrupts" apps/api/eval/README.md`
- **Done:** grep count ≥ 3; the README mentions `booking-ambiguous` as intentionally opted out.
- **Criteria:** SC-9
- **Interfaces:** Consumes the field/meta names fixed by Tasks 1.1 and 1.2 (documented, not imported). Produces `apps/api/eval/README.md`.

### Task 2.1 — Annotate the twelve goldens with `hitl: approve` (wave 2)

- **Files:** apps/api/eval/datasets/booking.json, apps/api/eval/datasets/dates.json, apps/api/eval/datasets/errors.json, apps/api/eval/datasets/routing.json, apps/api/eval/datasets/suggestions.json
- **Action:** Add `"hitl": "approve"` (key placed after `expected_flow`) to exactly: `booking-happy-vi-01`, `booking-happy-en-01`, `booking-happy-en-02`, `booking-multi_turn-vi-01`, `booking-multi_turn-en-01`, `booking-tool_failure-vi-01`, `errors-tool_failure-vi-01`, `dates-multi_turn-vi-01`, `dates-multi_turn-en-01`, `routing-ambiguous-en-01`, `suggestions-happy-vi-04`, `suggestions-happy-en-04` — 12 ids (the design's component 4 list, including the two `booking-multi_turn-*` goldens added at spec review). Leave `booking-ambiguous-vi-01`, `booking-ambiguous-en-01`, `errors-ambiguous-en-01`, `routing-multi_turn-*` untouched. Append to each annotated golden's `notes`: "hitl: approve — the runner resumes the plan-approval interrupt (gh-153)". Keep the files' inline-list JSON style (scalar lists on one line, `turns` multi-line, `params` inline) — re-serialise with the same helper used in review-b7 or edit by hand.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_datasets.py -q`
- **Done:** SC-5 exits 0; `OPENAI_API_KEY= ../../.venv/bin/python -m eval --suite full --dry-run` lists 84 goldens and exits 0; `git diff --stat` shows only added `hitl`/`notes` lines in the five files.
- **Criteria:** SC-5, SC-6
- **Interfaces:** Consumes `evalkit/types.py` from Task 1.1 (the store validates the hitl field at load). Produces `eval/datasets/booking.json`, `eval/datasets/dates.json`, `eval/datasets/errors.json`, `eval/datasets/routing.json`, `eval/datasets/suggestions.json`.

### Task 3.1 — Paid full run, triage of flipped goldens, regenerated baseline (wave 3)

- **Files:** apps/api/eval/baselines/main.json, apps/api/eval/datasets/booking.json, apps/api/eval/datasets/errors.json, apps/api/eval/datasets/dates.json, apps/api/eval/datasets/routing.json, apps/api/eval/datasets/suggestions.json, specs/gh-153-eval-hitl-auto-approve/SUMMARY.md, specs/gh-153-eval-hitl-auto-approve/TRIAGE.md
- **Action:** Gate: ask the user to authorise the spend before running. Then `cp ../../../../apps/api/.env .env` (if absent), confirm `docker ps` shows `api-db-1`, run `make eval-full` (writes `eval/reports/latest.json`; make exits 2 while capabilities sit below threshold — the report is still written). Write `TRIAGE.md`: one row per `hitl` golden — previous result (from the committed baseline), new result, failing checks, class (`agent-defect` → GitHub issue reference in `notes`; `stale-golden` → edit `expected_tools`/`metrics` with the reason in `notes`; `eval-defect` → stop and escalate, no code edits in this task). Re-run `make eval-full` at most once after golden edits. Then `make eval-baseline`, and record in `SUMMARY.md ### Verify` the run commands, exit codes, pass counts before/after, plus SC-7/SC-8 rows; fill `### Rollback` (`git revert <sha>` of the baseline commit) and `### Not auto-verified` (judge variance; goldens that still fail with their issue numbers).
- **Verify:** `cd apps/api && ../../.venv/bin/python -c "import json;r=json.load(open('eval/baselines/main.json'));m=r['run_meta'];assert m['suite']=='full' and m['repeat']==3 and m['summary']['total_cases']==84,m;b=[c for c in r['per_case'] if c['golden_id']=='booking-happy-en-01'][0];assert any(k['name']=='non_empty_reply' and k['passed'] for k in b['checks']),b"`
- **Done:** `eval/baselines/main.json` is regenerated from a run made after Tasks 1.x/2.1 (booking-happy-en-01's `non_empty_reply` passes — the interrupt was resumed); `make eval-compare` against it exits 0; `TRIAGE.md` classifies every `hitl` golden; SUMMARY Verify rows carry exit codes.
- **Criteria:** SC-7, SC-8
- **Interfaces:** Consumes `eval/datasets/booking.json` and siblings from Task 2.1, `eval/adapters/langgraph_runner.py` from Task 1.2, and the make eval-full / make eval-baseline targets (unchanged). Produces `apps/api/eval/baselines/main.json`, `specs/gh-153-eval-hitl-auto-approve/TRIAGE.md`, completed `specs/gh-153-eval-hitl-auto-approve/SUMMARY.md`.

## 5. Risks

- **Paid run outcome unknown**: the booking sub-agent's behaviour after approval is unmeasured; failures are triaged into issues, never hidden by editing expectations to match.
- **Plain HumanMessage on a parked thread** (multi-turn goldens): the runner resumes immediately after the interrupting turn, before the next turn, so no turn is ever sent to a parked thread when `hitl` is set; without `hitl` the recorded interrupt documents the stop.
- **Judge variance**: the baseline changes for reasons unrelated to this fix; the TRIAGE table separates `hitl` goldens from the rest.
- **Branch base**: cut from PR #157's branch; if #157 merges first, rebase onto `main` before opening the PR.

## 6. Status Log

- 2026-09-07 — plan written (writing-plans) from the approved design and Standard research brief; not yet executed.
- 2026-09-07 — design approved (spec reviewer ✅), research-brief Standard, PLAN reviewed ✅ (independent pass); not yet executed
- 2026-09-07 — tasks 1.1, 1.2, 1.3, 2.1 complete; commits bab3557, 4eff7fe, 076f3ac, af27f9b (1.x reviews pass/approved; 2.1 review pending); README tweak 7df9785
