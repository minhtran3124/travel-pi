# review-b7-eval-baseline-ci — Summary

Lane: high-risk
Confidence: high
Reason: judgment hard gate `remove-functionality` (the evalkit branch retires six legacy `eval/` modules + their tests that `main` kept evolving) plus 3 flags (existing behavior — eval harness + Makefile + .gitignore change; weak proof — judged metrics are non-deterministic and the current CI smoke is tautological; multi-domain — eval package, tests, CI, docs, a 335-commit merge). The external-systems flag was retired by decision E002 (no judge key on CI). Direction ambiguity was resolved by the human at intake (ESCALATIONS.md E001–E003), so confidence is high.
Flags: remove-functionality (judgment gate), existing behavior, weak proof, multi-domain
Affects: apps/api/evalkit/**, apps/api/eval/** (adapters, datasets, reports/baseline), apps/api/tests/eval/**, apps/api/Makefile, .gitignore, .github/workflows/eval.yml (keyless PR job only — nightly judged job removed per E002), specs/agent-eval-pipeline/**
Input-type: change request
Route: high-risk — work happens ON the existing branch `feat/agent-eval-pipeline` (E001): step 0 = `git merge main` into it and resolve the 15-file conflict set (legacy modules deleted on the branch vs edited on main → keep the branch's retirement, port any main-side dataset/golden edits); then brainstorming (design.md sizing the refactor/update against the branch's plan + current code) → xia2 (Deep) → writing-plans → using-git-worktrees (verify isolation on that branch) → subagent-driven-development; `compound` for the FakeLLM-smoke premise.
Escalate: no (E001–E003 decided at intake by the human on 2026-09-07; see ESCALATIONS.md)

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> cho section "Eval không có baseline, không gate CI" dua theo link artifact https://claude.ai/code/artifact/e31c4a78-8e78-4b47-9ec7-4e9c5d0d2ac1?org=a991bacc-62b1-465c-9ceb-db8aa116b6b8

Item 7 of the Travel-Pi Deep Review (artifact above, §3.B "Kiến trúc agent"; same text in `docs/reviews/2026-09-02-deep-review.md`), quoted verbatim:

> **7 — Eval không có baseline, không gate CI.** 39 golden case, judged metrics không chạy trong CI, `eval/reports/latest.json` không commit, `no_hallucination` chưa dùng được vì tool output chưa wire thành retrieval_context. Nhánh evalkit (84 golden, DB-as-Oracle) dừng từ 07-13. Trong khi đó `active.yaml` sửa 32 lần.
>
> **Sửa:** merge hoặc đóng evalkit; commit baseline; chạy FakeLLM routing smoke trong CI với threshold; chạy judged eval nightly.

## What changed

**Step 0 done (2026-09-07): `main` merged into `feat/agent-eval-pipeline`** in worktree `.claude/worktrees/feat-agent-eval-pipeline`. 19 conflicts resolved:
- Legacy MIN-58 modules the branch retired (`eval/{harness,loader,metrics,metrics_geval,run_deepeval,run_eval}.py`, `datasets/tools.json`, `tests/eval/{test_eval_smoke,test_metrics_geval,test_run_deepeval}.py`) → deleted (branch side kept). Main-only legacy additions that import them or use the legacy case shape (`tests/eval/{test_harness_multiturn,test_metrics_registry}.py`, `datasets/{multi_intent,suggestions}.json`) → deleted too; **to port as goldens in the plan**: 6 multi-intent cases (primary + `expected_plan`) and 12 `suggestion_relevance` cases (recover from `main` at `4e032c7`).
- Prompts: main wins. Branch's supervisor v6 (money → budget rule) is superseded — main's v10 already carries the "Log that I paid 50 USD" → budget example; `active.yaml` = main's.
- `datasets/routing.json`, `memory.json`, `eval/README.md`, `tests/eval/test_datasets.py` → branch (Golden schema); ported main's two new routing cases as `routing-happy-en-05` / `routing-happy-vi-03`.
- `.gitignore` → union; `specs/STATE.md`, `test_prompt_registry_helpers.py` → main.
- Drift fix: `TripService` is owner-scoped since #118, so `DbOracle` builds it per `trip_budget` lookup from `params["user_id"]` (tests seed with `eval-oracle-owner`).

Known, pre-existing (not merge regressions): `python -m eval --dry-run` needs *some* `OPENAI_API_KEY` (even `test`) because `build_graph` resolves LLMs eagerly — the "keyless" claim in `eval/__main__.py` is false; ruff reports 10 pre-existing findings in `tests/` (F811 fixture re-import, I001) on both branch and main.

Intake itself made no implementation edits beyond the merge. The claims were corroborated against the working tree on `main`-derived branch `feat/agent-system-copy-i18n` (2026-09-07) and against `github/feat/agent-eval-pipeline`:

| Claim | Status | Evidence |
| --- | --- | --- |
| Judged metrics do not run in CI | **Confirmed** | `.github/workflows/ci.yml` api job runs only `pytest tests/ -q`; no eval workflow exists on main |
| No committed baseline | **Confirmed** | `git ls-files apps/api/eval` lists no `reports/`; local `apps/api/eval/reports/` (smoke.json, latest.json, h1–h3, …) is untracked and its schema (`per_capability`, `golden_id`) is the evalkit one, i.e. produced from the stale branch |
| "FakeLLM routing smoke in CI with threshold" is missing | **Premise correction** | `tests/eval/test_eval_smoke.py` already runs in CI and asserts `ROUTING_THRESHOLD=0.9` / `PLAN_THRESHOLD=0.8` — but the FakeLLM is scripted with each case's *expected* answer, so it proves the pipeline, not the agent. A FakeLLM cannot measure routing quality at all (routing is the LLM's decision); any real gate needs a keyed model. |
| evalkit branch stalled since 07-13 | **Confirmed, and drifted** | 8 commits ahead of fork `f8b3b72`; `main` has 335 commits since. `git merge-tree main github/feat/agent-eval-pipeline` → conflicts in 15+ files, incl. modify/delete on `eval/harness.py`, `loader.py`, `metrics.py`, `run_eval.py`, `datasets/tools.json` (branch deleted them; main kept editing). Branch touches no `apps/api/app/**`. |
| evalkit ships the requested pieces | **Partially** | Branch has `.github/workflows/eval.yml` (keyless PR job + nightly judged on cron, `workflow_dispatch`), `make eval-{smoke,full,baseline,compare}`, 84 goldens, Report/baseline regression gate. Its own workflow comment admits the PR job is `--dry-run` only (no FakeLLM injection in `eval/__main__.py`, DB-backed goldens need a live DB). |
| `no_hallucination` unusable (no retrieval_context) | **Not re-verified here** | Noted in memory `min-58-eval-calibration-shipped`; carried as a scope question, not a blocker |
| `active.yaml` edited 32 times | **Not re-verified** | Cosmetic to the decision; not needed |

### Rationale

The lane is high-risk because the chosen path retires the MIN-58 harness modules that `main` kept evolving (Rule-4 remove-functionality) across a 335-commit merge. The review left the load-bearing choice open ("merge **hoặc** đóng evalkit"), so intake escalated instead of guessing; the human decided (E001) to keep the evalkit branch, merge `main` into it first, and then plan the refactor/update sized by the state of the code — so the plan is written against the merged branch, not against `main`. E002 removes the paid-judge-in-CI surface for now (baseline + compare stay local/keyed), and E003 fixes the baseline as a committed JSON with a tolerance gate, which is what the branch's `evalkit` Report/baseline design already implements.

### Alternatives considered

- Treat as `normal` and just add a CI step around the existing `run_eval.py` — rejected: the existing keyless smoke is already in CI and is tautological; the only meaningful gate is keyed, which is the external-provider surface.
- Pick the evalkit merge silently because it already contains the requested workflow — rejected: it retires functionality on `main` (Rule 4 judgment gate) and the branch's own SUMMARY records that the PR gate does not actually run the agent.
- Close the branch and cherry-pick pieces onto the MIN-58 harness (the intake's recommended hybrid) — rejected by the human in E001 in favour of keeping the branch and merging `main` into it.
- Split into three child specs now (branch fate / baseline / nightly) — no longer needed: E002 drops the nightly job, so baseline + compare + keyless PR job fit one plan on the merged branch.

### Deviations

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| CI has no eval step | `grep -n -i eval .github/workflows/ci.yml` | 1 | no match | |
| Reports untracked | `git ls-files apps/api/eval/reports` | 0 | empty output; `git status --short apps/api/eval` shows `?? apps/api/eval/reports/` | |
| Existing smoke is scripted | `sed -n 8,25p apps/api/tests/eval/test_eval_smoke.py` | 0 | `FakeLLM(structured_responses=[SupervisorIntent(target_agent=item["expected"]) …])` | |
| evalkit drift | `git log --oneline f8b3b72..main \| wc -l` | 0 | 335 | |
| evalkit merge conflicts | `git merge-tree --write-tree --name-only main github/feat/agent-eval-pipeline` | 1 | CONFLICT lines for .gitignore, eval/README.md, datasets/{memory,routing,tools}.json, harness.py, loader.py, metrics.py, … | |
| Lane evidence | `python3 .claude/scripts/verify_summary.py --lane review-b7-eval-baseline-ci` | 0 | see intake run | |
| Merge: eval + prompt tests (post-resolution) | `cd apps/api && ../../.venv/bin/python -m pytest tests/eval tests/api/prompts -q` | 0 | 164 passed (pre-merge tip 77b1105: 140 passed) | |
| Merge: full BE suite on fresh SQLite | `cd apps/api && DATABASE_URL=sqlite:////tmp/x.db ../../.venv/bin/python -m pytest tests/ -q` | 0 | 2257 passed in 175s | |
| Merge: eval CLI wiring | `cd apps/api && OPENAI_API_KEY=test ../../.venv/bin/python -m eval --suite smoke --dry-run` | 0 | lists 18 smoke goldens; fails without any key (pre-existing) | |
| Merge: no conflict markers | `git diff --name-only --diff-filter=U` | 0 | empty | |

### Not auto-verified

- `no_hallucination` still lacks `retrieval_context` wiring — reached traceability (memory note only); not re-run because it does not change the lane or the escalation questions.
- "`active.yaml` sửa 32 lần" — not re-derived; cosmetic.

### Rollback

- Intake only: `rm -rf specs/review-b7-eval-baseline-ci/` (nothing else was touched).
- For the eventual implementation: `git revert <sha>` per commit; a merged evalkit is reverted with `git revert -m 1 <merge-sha>`; a GitHub secret is removed in repo settings; the nightly workflow is disabled by deleting `.github/workflows/eval.yml`.

### Harness-Delta

- backlog — the `feature-intake` skill routes "run the FakeLLM smoke in CI" as a plausible deliverable, but for an LLM-decided behavior a fake model can only test the harness. Worth a `docs/solutions/` note ("FakeLLM smoke proves plumbing, not quality") so future eval intakes do not inherit the premise.
