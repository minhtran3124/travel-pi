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

**Implemented (waves 1–5, 12 tasks, branch `feat/agent-eval-pipeline`).** The eval now has a committed baseline and a working local regression gate:
- `--dry-run` is keyless (no runner built); the CI workflow keeps only the keyless `eval-smoke` job (E002).
- `Golden.expected_tasks` + `tasks_expected` metric; the runner records `tasks` and `suggestions` in `Trace.meta`; suggestion keys reach the judge's retrieval context.
- 16 legacy cases from `main` ported as goldens (6 multi-intent with v10-derived expectations, 10 `suggestions`); dataset total 102 (84 full + 18 smoke).
- `make eval-check` (full run → compare), guarded `eval-compare`, `BASELINE` override; standalone `pyproject.toml` dropped; README documents the ritual.
- The eval grades the agent at **premium + authenticated** (user decision at task 3.1; a free/anonymous context cannot reach booking or create trips).
- Re-validation: run 1 57/84 → 10 stale goldens fixed, 2 eval defects fixed (empty-reply guards), 11 GitHub issues (#146–#156) for agent defects and the HITL eval gap → run 2 65/84. The correctness review then found the empty-reply guards masking failures (fixed: `non_empty_reply` is always on, `12a9fe5`), so a user-authorised run 3 regenerated the baseline: **58/84**, committed as `apps/api/eval/baselines/main.json`; all 26 failures carry an issue reference (#146–#156). Full triage in `TRIAGE.md`.

**Step 0 done (2026-09-07): `main` merged into `feat/agent-eval-pipeline`** in worktree `.claude/worktrees/feat-agent-eval-pipeline`. 19 conflicts resolved:
- Legacy MIN-58 modules the branch retired (`eval/{harness,loader,metrics,metrics_geval,run_deepeval,run_eval}.py`, `datasets/tools.json`, `tests/eval/{test_eval_smoke,test_metrics_geval,test_run_deepeval}.py`) → deleted (branch side kept). Main-only legacy additions that import them or use the legacy case shape (`tests/eval/{test_harness_multiturn,test_metrics_registry}.py`, `datasets/{multi_intent,suggestions}.json`) → deleted too; **to port as goldens in the plan**: 6 multi-intent cases (primary + `expected_plan`) and 10 `suggestion_relevance` cases (recover from `main` at `4e032c7`).
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

- Design component 8 — two legacy multi-intent cases ("Find flights to Tokyo and tell me the weather there", "Plan my Tokyo weekend: find flights, check the weather, then draft an itinerary") were ported as planner-only `flow_match` goldens (`routing-multi-en-01/02`) instead of `expected_tasks` fan-outs, per research-brief.md's supervisor-v10 Inference row (planner owns flights + weather). Commit `4003892`.
- Rule 1 — Task 2.1: `test_multi_intent_goldens_declare_tasks_expected` accepts either shape for `routing-multi-*` ids (fan-out with `expected_tasks`, or single-flow with `expected_flow`) because PLAN.md's one-line test description contradicted its own Inference row. `apps/api/tests/eval/test_datasets.py`. Commit `4003892`.
- Rule 1 — Task 1.7: reworded one unrelated README line ("optional extras" → "extras") so the whole-file substring Verify passes. `apps/api/evalkit/README.md:150`. Commit `873a487`.
- Rule 1 — Task 3.2: `reply_language` returns `not_applicable` on an empty reply (`apps/api/evalkit/metrics/deterministic.py`) — same defect class as the planned `judged.py` guard, one file beyond the task's Files line (controller decision; blast-radius noted). Commit `6b66399`.
- User decision (task 3.1, AskUserQuestion) — the eval context is `resolve_agent_context(tier="premium", authenticated=True)` instead of the branch's `tier=None`; changes what the baseline measures, not app code. `apps/api/eval/__main__.py`. Commit `a51b28d`.
- Rule 3 — Task 3.1: `eval/__main__.py::_prod_agent_context` called `settings.agent_config_cache_ttl_seconds`, renamed on main to `agent_config_poll_interval_seconds` (`app/core/lifespan.py:52`); fixed in the eval entrypoint only. Blocking for every real run; untested path.
- Rule 1 — Task 1.5: the multi-intent runner test asserts `suggestions` is a list rather than non-empty, because a multi-intent turn ends at `current_flow == "synthesize"`, which has no static suggestion map. `apps/api/tests/eval/test_langgraph_runner.py`. Commit `1ff23e4`. Product gap noted for backlog: real multi-intent turns surface zero suggestion chips.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| CI has no eval step | `grep -n -i eval .github/workflows/ci.yml` | 1 | no match | |
| Reports untracked | `git ls-files apps/api/eval/reports` | 0 | empty output; `git status --short apps/api/eval` shows `?? apps/api/eval/reports/` | |
| Existing smoke is scripted (intake-era; file retired in merge 1092ccf) | `<not re-runnable: sed -n 8,25p apps/api/tests/eval/test_eval_smoke.py — file deleted by the merge>` | 0 | `FakeLLM(structured_responses=[SupervisorIntent(target_agent=item["expected"]) …])` | |
| evalkit drift | `git rev-list --count f8b3b72..main` | 0 | 335 | |
| evalkit merge conflicts | `git merge-tree --write-tree --name-only main github/feat/agent-eval-pipeline` | 1 | CONFLICT lines for .gitignore, eval/README.md, datasets/{memory,routing,tools}.json, harness.py, loader.py, metrics.py, … | |
| Lane evidence | `python3 ../../../.claude/scripts/verify_summary.py --lane specs/review-b7-eval-baseline-ci/SUMMARY.md` | 0 | see intake run | |
| Merge: eval + prompt tests (post-resolution) | `cd apps/api && DASHBOARD_BASIC_USER= DASHBOARD_BASIC_PASSWORD= ../../.venv/bin/python -m pytest tests/eval tests/api/prompts -q` | 0 | 164 passed at the merge (pre-merge tip 77b1105: 140); env override because the copied `.env` enables dashboard basic auth (401s) | |
| Merge: full BE suite on fresh SQLite | `<not re-run under --check (175s): cd apps/api && DATABASE_URL=sqlite:////tmp/x.db ../../.venv/bin/python -m pytest tests/ -q>` | 0 | 2257 passed in 175s | |
| Merge: eval CLI wiring | `cd apps/api && OPENAI_API_KEY=test ../../.venv/bin/python -m eval --suite smoke --dry-run` | 0 | lists 18 smoke goldens; fails without any key (pre-existing) | |
| Merge: no conflict markers | `git diff --name-only --diff-filter=U` | 0 | empty | |
| 3.1 seed synthesize model (data) | `<dev-DB write, not re-run under --check: docker exec -w /app -e PYTHONPATH=/app api-api-1 python scripts/seed_agent_config.py --provider openai --model gpt-5.4-mini --nodes synthesize>` | 0 | row now openai/gpt-5.4-mini; `docker exec api-api-1 touch app/main.py` to reload | SC-3 |
| 3.1 pre-flight real run (routing, k=1) | `<paid run, not re-run under --check: cd apps/api && ../../.venv/bin/python -m eval --suite full --capability routing --out eval/reports/preflight.json>` | 0 | 17 cases, 12 passed (70.6%); multi-task goldens routing-multi-en-03/04 PASS (parallel synthesize works); first attempt crashed on stale `settings.agent_config_cache_ttl_seconds` (Rule 3 fix below) | SC-3 |
| 3.1 Verify | `cd apps/api && ../../.venv/bin/python -c "import json;r=json.load(open('eval/reports/preflight.json'));assert r['run_meta']['summary']['total_cases']==17;bad=[c['golden_id'] for c in r['per_case'] for k in c['checks'] if '403' in (k.get('detail') or '')];assert not bad,bad"` | 0 | no 403 in any check | SC-3 |
| 3.2 run 1 (full, k=3, premium+auth) | `<paid run, not re-run under --check: cd apps/api && make eval-full>` | 2 | 57/84; make exits 2 because capabilities sit below threshold — report written; see TRIAGE.md | |
| 3.2 run 2 (after golden/eval fixes) | `<paid run, not re-run under --check: cd apps/api && make eval-full>` | 2 | 65/84; superseded as baseline by run 3 | |
| run 3 (after correctness fix 12a9fe5, always-on non_empty_reply) | `<paid run, not re-run under --check: cd apps/api && make eval-full>` | 2 | 58/84; this report is the committed baseline (paid run — not re-runnable under a 60s check) | SC-3 |
| 3.2 Verify | `cd apps/api && ../../.venv/bin/python -c "import json;r=json.load(open('eval/reports/latest.json'));m=r['run_meta'];assert m['suite']=='full' and m['repeat']==3 and m['judge_available'] is True and m['summary']['total_cases']==84,m"` | 0 | | SC-3 |
| 3.3 degraded compare rejects | `<mutates latest.json, not re-run under --check: cd apps/api && make eval-compare after flipping every routing case to failed>` | 2 | table prints `routing … -88.2% REGRESSED` + 15 pass→fail ids, `exit_code=1`, make Error 1; latest.json restored from the baseline afterwards | SC-5 |
| SC-1 keyless dry-run | `cd apps/api && OPENAI_API_KEY= ../../.venv/bin/python -m eval --suite smoke --dry-run` | 0 | 18 goldens listed | SC-1 |
| SC-2 no schedule/secrets | `grep -n -e "schedule:" -e "secrets\." .github/workflows/eval.yml` | 1 | no match | SC-2 |
| SC-3 baseline shape | `cd apps/api && ../../.venv/bin/python -c "import json;r=json.load(open('eval/baselines/main.json'));m=r['run_meta'];assert m['suite']=='full' and m['repeat']==3 and m['summary']['total_cases']==84,m"` | 0 | | SC-3 |
| SC-4 identical compare | `cd apps/api && mkdir -p eval/reports && cp eval/baselines/main.json eval/reports/latest.json && make eval-compare` | 0 | every capability +0.0% ok | SC-4 |
| SC-5 gate rejects regression (unit) | `cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_baseline.py -q -k "regressed_run or within_tolerance"` | 0 | | SC-5 |
| SC-6 tasks_expected | `cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_metrics_deterministic.py -q -k tasks_expected` | 0 | 4 passed | SC-6 |
| SC-7 runner meta | `cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_langgraph_runner.py -q -k meta` | 0 | 2 passed | SC-7 |
| SC-8 suggestions in retrieval context | `cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_metrics_judged.py -q -k suggestion` | 0 | | SC-8 |
| SC-9 datasets | `cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_datasets.py -q` | 0 | 22 passed, 102 goldens | SC-9 |
| SC-10 manifest gone | `test ! -e apps/api/evalkit/pyproject.toml` | 0 | | SC-10 |
| SC-11 eval-check resolves | `cd apps/api && make -n eval-check` | 0 | eval-full then eval-compare | SC-11 |
| SC-12 compare without baseline | `cd apps/api && env BASELINE=eval/baselines/does-not-exist.json make eval-compare` | 2 | message names `make eval-baseline` | SC-12 |
| SC-13 README cleaned | `grep -n -i "Optional extras" apps/api/evalkit/README.md` | 1 | no match | SC-13 |
| Full BE suite at finish (HEAD b4337a3, fresh SQLite, `.env` secrets neutralised) | `<not re-run under --check (183s): cd apps/api && DATABASE_URL=sqlite:////tmp/x.db OPENAI_API_KEY= ANTHROPIC_API_KEY= GOOGLE_API_KEY= ORS_API_KEY= DASHBOARD_BASIC_USER= DASHBOARD_BASIC_PASSWORD= LANGFUSE_ENABLED=false ../../.venv/bin/python -m pytest tests/ -q>` | 1 | 2268 passed, 3 failed — all three (`test_config_llm.py::test_llm_defaults_require_no_key`, `::test_langfuse_disabled_by_default`, `test_embeddings.py::test_get_embeddings_fake_without_key`) use `monkeypatch.delenv`, which loses to the copied `apps/api/.env` (memory: env-u-does-not-neutralize-dotenv-secrets); re-run with `.env` renamed → 15 passed. Code is green. | |
| tests/eval whole (cited, not a task Verify) | `cd apps/api && ../../.venv/bin/python -m pytest tests/eval -q` | 0 | 153 passed | |

### Not auto-verified

- The 26 baseline failures are agent defects or the HITL eval gap (issues #146–#156) — reached traceability (report + issue), not re-run beyond k=3; 4 goldens flipped pass/fail between run 1 and run 2 without any edit (language ×2, journal-multi_turn-vi-01, flight_search-ambiguous-en-01), so judged and routing variance is real and only the tolerance gate absorbs it.
- Full BE suite re-run at finish (2268 passed; the 3 `.env`-dependent failures pass with `.env` absent — see Verify) — the 3 are pre-existing dotenv-vs-monkeypatch tests, not touched by this branch.
- `no_hallucination` is wired (`build_retrieval_context`) but unused — no golden declares it, so the baseline has no such check; deferred (see Intent Findings).
- "`active.yaml` sửa 32 lần" — not re-derived; cosmetic.

### Advisory Findings

Correctness review (35b392e..edc3534, six FIND angles, independent scoring, threshold 75). One finding scored 75 and was fixed in `12a9fe5` (always-on `non_empty_reply`; baseline regenerated in run 3). Below threshold, recorded, not auto-fixed:

- score 25 — `apps/api/evalkit/metrics/deterministic.py:108` `tasks_expected` uses set equality, so a duplicated agent in `expected_tasks` would be collapsed; the supervisor dedupes `tasks` and no golden repeats an agent, so there is no trigger today.
- score 25 — `apps/api/evalkit/metrics/deterministic.py:104-111` a `meta["tasks"]` value that is present but not an iterable of hashables would raise inside the metric and abort the run; the only producer always writes a list of strings.
- score 25 — `apps/api/Makefile:68` `eval-compare` guards only for a missing baseline; a corrupt committed baseline surfaces as a `load_report` traceback rather than the friendly message.
- score 0 — `apps/api/eval/adapters/langgraph_runner.py:207` `t.get("agent")` on a non-dict task item; every writer of `state["tasks"]` stores dicts (`AgentTask.model_dump()`), production does the same `.get`.
- score 25 — `apps/api/eval/adapters/langgraph_runner.py:207` on a resume/interrupt turn `state["tasks"]` is not reset, so `meta["tasks"]` could describe the previous turn; latent — the runner never resumes an interrupt and no golden combines `turns` with `expected_tasks`.
- Per-task Minor findings (ledger `.harness-state/sdd/ledger.md`): `_DryRunRunner.run` unannotated; `eval-baseline` hardcodes `mkdir -p eval/baselines`; either/or test shape for `routing-multi-*`; legacy `expected` key on 11 older routing goldens now disagrees with `expected_flow` on `routing-ambiguous-en-02` (inert, no consumer); README wording (suggestion lines are built in `judged.py`, `expected_tasks` is a list compared as a set); product gap — `synthesize` has no static suggestion map so real multi-intent turns surface zero chips.

### Intent Findings

Intent review (35b392e..75e8b0c, plan-blind, verbatim `### Intent` as oracle): 2 gaps, 0 drift, no untraceable excess.

- gap (decided) — "chạy FakeLLM routing smoke trong CI với threshold" is not delivered and the legacy scripted smoke was retired by the merge. Escalated as E004; the user ratified the intake premise correction (a scripted FakeLLM proves plumbing only). The keyless PR job stays `pytest tests/eval` + `--dry-run`.
- gap (deferred) — "`no_hallucination` chưa dùng được vì tool output chưa wire thành retrieval_context": the wiring exists (`build_retrieval_context` serialises tool outputs and now suggestion keys), but no golden names `no_hallucination`, so the baseline carries zero such checks. Deferred: adding `no_hallucination` to grounded goldens is a dataset change for a later eval pass.

### Rollback

- Intake only: `rm -rf specs/review-b7-eval-baseline-ci/` (nothing else was touched).
- Implementation: `git revert` the wave commits on `feat/agent-eval-pipeline` (04ec68e de64ba4 5d79fad 3114808 1ff23e4 c600a54 873a487 4003892 c17c44a 864d892 a51b28d 6b66399 + the 3.3 commit); the dev-DB seed is undone with `docker exec -w /app -e PYTHONPATH=/app api-api-1 python scripts/seed_agent_config.py --provider '' --model '' --nodes synthesize` (or leave it — it only fills a NULL row). Earlier draft: `git revert <sha>` per commit; a merged evalkit is reverted with `git revert -m 1 <merge-sha>`; a GitHub secret is removed in repo settings; the nightly workflow is disabled by deleting `.github/workflows/eval.yml`.

### Harness-Delta

- backlog — the `feature-intake` skill routes "run the FakeLLM smoke in CI" as a plausible deliverable, but for an LLM-decided behavior a fake model can only test the harness. Worth a `docs/solutions/` note ("FakeLLM smoke proves plumbing, not quality") so future eval intakes do not inherit the premise.
