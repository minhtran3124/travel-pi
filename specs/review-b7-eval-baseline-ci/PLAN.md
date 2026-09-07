---
slug: review-b7-eval-baseline-ci
status: active
owner: Minh Tran
created: 2026-09-07
---

# Eval baseline + regression gate on the evalkit branch

## 1. Motivation

Deep-review item 7: the agent eval has no committed baseline and no gate, while prompts keep changing. `main` has been merged into `feat/agent-eval-pipeline` (commit `1092ccf`); the evalkit engine already holds the gate math (`evalkit.baseline.compare`, tolerance 0.05 + masked-flip rule) and the make targets, but nothing has ever produced the baseline, the "keyless" dry-run needs a key, the nightly CI job contradicts decision E002, and 16 legacy cases from `main` were dropped in the merge. Design: `design.md` (approved). Research: `research-brief.md` (Deep).

## 2. Non-goals

- No judged (paid) eval on GitHub Actions — no secret, no cron (E002).
- No edits under `apps/api/app/**`; an agent defect found by re-validation becomes a GitHub issue, the golden stays, the baseline records the failure.
- No Langfuse/LangSmith online eval, no evalkit extraction/MCP, no model-tier benchmarking, no changes to `evalkit/ports.py` or `tests/eval/test_boundary.py`.

## Global Constraints

- Work happens only in worktree `.claude/worktrees/feat-agent-eval-pipeline` on branch `feat/agent-eval-pipeline`. Run backend commands from `apps/api/` of that worktree.
- Interpreter: the worktree has no `.venv`; before wave 1, run `ln -s ../../../.venv .venv` at the worktree root once (the worktree sits two levels under the main checkout) so `../../.venv/bin/python` and `make` (`VENV ?= ../../.venv`) resolve. `.venv/` is gitignored.
- Wave-3+ real runs need `apps/api/.env` (gitignored, absent in the worktree): copy it from the main checkout (`cp ../../../../apps/api/.env .env` from `apps/api/`). Never commit it. Docker `api-db-1` must be up (`docker compose up -d db` from the main checkout's `apps/api/`).
- Every schema change is additive: `Golden` gains an optional field; `Trace` is unchanged (`meta` carries new keys); `Report` shape untouched.
- Golden ids follow `<capability>-<scenario>-<lang>-NN`; new goldens are suite `full` (smoke stays 18 and judge-free; `tests/eval/test_datasets.py` enforces both).
- Stage and commit as separate commands; commit messages carry no tooling trailers (`CLAUDE.local.md`).
- Harness scripts live in the main checkout, not the worktree: from the worktree root use `../../../.claude/scripts/<script>.py`, from `apps/api/` use `../../../../../.claude/scripts/<script>.py`.
- `make eval-full` writes `eval/reports/` (gitignored); create it once with `mkdir -p apps/api/eval/reports` before any SC-4/Task 3.x check.
- Suite semantics: `JsonDatasetStore.load(suite=...)` is an exact match (`evalkit/dataset.py:176`), so `--suite full` runs the 84 full-suite goldens and excludes the 18 smoke ones. The baseline therefore covers 84 cases; 102 is the store total (SC-9). Cost figure used everywhere in this spec: one `eval-full` run = 84 agent turns plus about 105 judge calls at k=3.
- Lane high-risk: per-task review stays on; Rule-4 STOP if any task would need an `app/**` edit.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|------|-------------------------|-----------------------|------------|
| SC-1 | Dry-run lists the smoke goldens with no provider key in the environment | `cd apps/api && OPENAI_API_KEY= ../../.venv/bin/python -m eval --suite smoke --dry-run` | exit 0 |
| SC-2 | The eval workflow has no scheduled run and no secret reference, comments included | `grep -n -e "schedule:" -e "secrets\." .github/workflows/eval.yml` | exit 1 — no match |
| SC-3 | A committed baseline exists from a full-suite k=3 run over all 84 full goldens | `cd apps/api && ../../.venv/bin/python -c "import json;r=json.load(open('eval/baselines/main.json'));m=r['run_meta'];assert m['suite']=='full' and m['repeat']==3 and m['summary']['total_cases']==84,m"` | exit 0 |
| SC-4 | The gate accepts a report identical to the baseline | `cd apps/api && mkdir -p eval/reports && cp eval/baselines/main.json eval/reports/latest.json && make eval-compare` | exit 0 |
| SC-5 | The gate rejects a report where one capability's pass rate drops by more than the tolerance | `cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_baseline.py -q -k "regressed_run or within_tolerance"` | exit 0 — the regression tests pass |
| SC-6 | `tasks_expected` grades set-equality of `Golden.expected_tasks` against `Trace.meta["tasks"]` and fails loudly when the trace has no tasks | `cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_metrics_deterministic.py -q -k tasks_expected` | exit 0 |
| SC-7 | The runner records `tasks` and `suggestions` in `Trace.meta` for a scripted multi-intent turn | `cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_langgraph_runner.py -q -k meta` | exit 0 |
| SC-8 | Suggestion keys reach the judge's retrieval context | `cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_metrics_judged.py -q -k suggestion` | exit 0 |
| SC-9 | The dataset store loads exactly 102 goldens including a non-empty `suggestions` capability | `cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_datasets.py -q` | exit 0 |
| SC-10 | The standalone manifest file is gone | `test ! -e apps/api/evalkit/pyproject.toml` | exit 0 |
| SC-11 | `make eval-check` resolves to a full run followed by the compare | `cd apps/api && make -n eval-check` | exit 0 |
| SC-12 | `eval-compare` with no baseline file fails with a message naming `make eval-baseline` | `cd apps/api && env BASELINE=eval/baselines/does-not-exist.json make eval-compare` | exit 2 — make reports the failed recipe |
| SC-13 | The evalkit README no longer documents a standalone install | `grep -n -i "Optional extras" apps/api/evalkit/README.md` | exit 1 — no match |

The full BE suite (`pytest tests/`, ~3 min) and `tests/eval` as a whole run at `finishing-a-development-branch`, not in any task Verify.

## 4. Tasks

### Task 1.1 — Keyless dry-run in the eval entrypoint (wave 1)

- **Files:** apps/api/eval/__main__.py, apps/api/tests/eval/test_main_dry_run.py
- **Action:** Test first: write `tests/eval/test_main_dry_run.py` that runs `[sys.executable, "-m", "eval", "--suite", "smoke", "--dry-run"]` via `subprocess.run` from `apps/api` with `env={**os.environ, "OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": "", "GOOGLE_API_KEY": ""}` (empty strings, never unset — dotenv refills an unset var) and asserts `returncode == 0` and `"routing-happy-en-01"` in stdout. Then in `eval/__main__.py::main`, detect `--dry-run` before any runner is built and pass a private `_DryRunRunner` whose `run()` raises `RuntimeError("--dry-run never invokes the agent")` instead of `LangGraphRunner(...)`; keep the existing `dry_run` variable and the DB-free session-factory behaviour. Update the module docstring sentence that claims constructing `LangGraphRunner()` is key-free (it is not: `build_graph` resolves `get_agent_llm` eagerly, brief §Evidence).
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_main_dry_run.py -q`
- **Done:** The new test passes; `OPENAI_API_KEY= ../../.venv/bin/python -m eval --suite smoke --dry-run` prints 18 golden lines and exits 0; `ruff check eval` reports 0 findings.
- **Criteria:** SC-1
- **Interfaces:** Consumes evalkit.cli.main, which returns before touching the agent runner on dry-run (evalkit/cli.py lines 99-100). Produces `eval/__main__.py` (dry-run path), `tests/eval/test_main_dry_run.py`.

### Task 1.2 — Strip the nightly judged job from CI (wave 1)

- **Files:** .github/workflows/eval.yml
- **Action:** Delete the `eval-nightly` job (lines 71-144 today, including its leading comment block that mentions `secrets.OPENAI_API_KEY`), the `schedule:` trigger, and rewrite the header comment so it states the E002 decision: the judged suite runs locally via `make eval-check`, never on CI. Keep `pull_request` path filters, `workflow_dispatch`, and the `eval-smoke` job unchanged.
- **Verify:** `! grep -q -e "schedule:" -e "secrets\." -e "eval-nightly" .github/workflows/eval.yml`
- **Done:** The grep finds no line; `python3 -c "import yaml;d=yaml.safe_load(open('.github/workflows/eval.yml'));assert set(d['jobs'])=={'eval-smoke'} and set(d[True])=={'pull_request','workflow_dispatch'}"` exits 0 (PyYAML parses the `on:` key as `True`).
- **Criteria:** SC-2
- **Interfaces:** Consumes the existing eval-smoke job (unchanged). Produces `.github/workflows/eval.yml` (single-job, keyless).

### Task 1.3 — `expected_tasks` field and `tasks_expected` metric (wave 1)

- **Files:** apps/api/evalkit/types.py, apps/api/evalkit/metrics/deterministic.py, apps/api/tests/eval/test_metrics_deterministic.py
- **Action:** Test first: add four tests named `test_tasks_expected_*` to `tests/eval/test_metrics_deterministic.py` — (a) `expected_tasks=["budget","concierge"]` vs `meta={"tasks":["concierge","budget"]}` passes (order-independent); (b) `["planner"]` vs `["planner","concierge"]` fails with detail containing `expected=` and `got=`; (c) `expected_tasks` set but `meta` has no `tasks` key fails with detail containing `no meta.tasks`; (d) `expected_tasks=None` returns `passed=True` with detail starting `not_applicable:`. Then add `expected_tasks: list[str] | None = None` to `Golden` (after `expected_tools`, with a one-line comment: agent names the supervisor fans out to; order-free because tasks run in parallel), and a `TasksExpectedMetric` class in `deterministic.py` following `FlowMatchMetric` (`name = "tasks_expected"`, set equality, the three detail strings above) registered via `register_metric(TasksExpectedMetric())` next to the other registrations.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_metrics_deterministic.py -q -k tasks_expected`
- **Done:** 4 new tests pass; `../../.venv/bin/python -c "from evalkit.registry import list_metrics;import evalkit.metrics;assert 'tasks_expected' in list_metrics()"` exits 0; `ruff check evalkit` reports 0 findings.
- **Criteria:** SC-6
- **Interfaces:** Consumes the Golden and Trace models and the register_metric hook (all pre-existing). Produces `evalkit/types.py` (Golden.expected_tasks), `evalkit/metrics/deterministic.py` (tasks_expected).

### Task 1.4 — Suggestion keys in the judge retrieval context (wave 1)

- **Files:** apps/api/evalkit/metrics/judged.py, apps/api/tests/eval/test_metrics_judged.py
- **Action:** Test first: add `test_build_retrieval_context_includes_suggestion_keys` (trace with no tool calls and `meta={"suggestions":["planner.checkWeather","planner.addPlace"]}` → returns a list whose entries are `"suggestion: planner.checkWeather"` and `"suggestion: planner.addPlace"`) and `test_build_retrieval_context_still_none_without_tools_or_suggestions`. Then extend `build_retrieval_context` to append one `f"suggestion: {key}"` line per entry of `trace.meta.get("suggestions") or []` after the tool-call lines, returning `None` only when both are empty. Replace the "Known gap" paragraph in the module docstring (lines 32-40) with one sentence stating the runner now supplies `meta["suggestions"]`.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_metrics_judged.py -q -k "retrieval_context or suggestion"`
- **Done:** New tests pass, existing `test_metrics_judged.py` tests still pass, the string `Known gap` no longer appears in `evalkit/metrics/judged.py`.
- **Criteria:** SC-8
- **Interfaces:** Consumes the trace meta key suggestions (written by Task 1.5; this function only reads a dict key, so the two tasks stay independent). Produces `evalkit/metrics/judged.py` (build_retrieval_context with suggestion lines).

### Task 1.5 — Runner records tasks and suggestions in `Trace.meta` (wave 1)

- **Files:** apps/api/eval/adapters/langgraph_runner.py, apps/api/tests/eval/test_langgraph_runner.py
- **Action:** Test first: add `test_run_meta_records_tasks_and_suggestions` scripting the supervisor with `SupervisorIntent(target_agent="budget", plan=["concierge"])` on a FakeLLM (see `test_run_captures_tool_call_output` for the `agent_db` fixture pattern) and asserting `trace.meta["tasks"] == ["budget", "concierge"]` and `trace.meta["suggestions"]` is a non-empty list of strings; and `test_run_meta_single_intent_has_one_task` asserting `meta["tasks"] == ["concierge"]` for a plain routing. Then in `LangGraphRunner.run`, after `graph.invoke`, add `"tasks": [t.get("agent") for t in out.get("tasks") or []]` and `"suggestions": suggestions_for_flow(out.get("current_flow"), trip_facts=out.get("trip_facts"))` to the `meta` dict, importing `suggestions_for_flow` from `app.agents.suggestions` (the adapter layer may import `app.*`; `evalkit/` may not).
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_langgraph_runner.py -q -k meta`
- **Done:** Both new tests pass; `tests/eval/test_boundary.py` still passes (no `app.*` import leaked into `evalkit/`).
- **Criteria:** SC-7
- **Interfaces:** Consumes graph output keys tasks (AgentTask.model_dump dicts, app/agents/supervisor.py lines 337-340), current_flow and trip_facts, and suggestions_for_flow from app/agents/suggestions.py line 135 (all pre-existing). Produces `eval/adapters/langgraph_runner.py` (Trace.meta.tasks, Trace.meta.suggestions).

### Task 1.6 — `make eval-check` and a guarded `eval-compare` (wave 1)

- **Files:** apps/api/Makefile
- **Action:** In the eval section: add a `BASELINE ?= eval/baselines/main.json` variable and use it in `eval-baseline` and `eval-compare`; make `eval-compare` first run `test -f $(BASELINE) || { echo "no baseline at $(BASELINE) — run 'make eval-baseline' after a trusted 'make eval-full'"; exit 1; }` before the existing python one-liner (unchanged except that its hardcoded baseline path becomes `$(BASELINE)`); add `eval-check: eval-full eval-compare  ## Local regression gate (E002: judged eval never runs on CI) — full judged run, then compare` as a target whose recipe is the two prerequisites in order (make runs prerequisites sequentially, so no recipe body is needed). Keep the `##` help-comment style of the neighbouring targets.
- **Verify:** `cd apps/api && make -n eval-check && ! env BASELINE=eval/baselines/does-not-exist.json make eval-compare`
- **Done:** `make -n eval-check` prints the `eval-full` command followed by the `eval-compare` command; `make eval-compare` with a missing baseline prints the line containing `make eval-baseline` and make exits 2 (a failed recipe).
- **Criteria:** SC-11, SC-12
- **Interfaces:** Consumes evalkit.baseline.compare and render_table (unchanged). Produces `apps/api/Makefile` (eval-check, BASELINE variable, guarded eval-compare).

### Task 1.7 — Drop the standalone manifest (wave 1)

- **Files:** apps/api/evalkit/pyproject.toml, apps/api/evalkit/README.md
- **Action:** `git rm apps/api/evalkit/pyproject.toml`. In `evalkit/README.md`, delete the `## Optional extras` section (heading at line 152 through the line before `## The runner`) and replace any remaining sentence that says evalkit is installable standalone with one sentence: the package is imported in-repo; extras (`agentevals`, `deepeval`) are pinned in `apps/api/requirements-ai.txt`.
- **Verify:** `test ! -e apps/api/evalkit/pyproject.toml && ! grep -q -i -e "optional extras" -e "pip install -e" apps/api/evalkit/README.md`
- **Done:** The manifest is absent from the tree and `git ls-files`; the README has no `Optional extras` heading and no `pip install -e` instruction; `tests/eval/test_boundary.py` passes.
- **Criteria:** SC-10, SC-13
- **Interfaces:** Consumes nothing. Produces `apps/api/evalkit/README.md` (manifest references removed).

### Task 2.1 — `suggestions` capability and the 16 ported goldens (wave 2)

- **Files:** apps/api/eval/adapters/config.py, apps/api/eval/datasets/routing.json, apps/api/eval/datasets/suggestions.json, apps/api/tests/eval/test_datasets.py
- **Action:** Test first: in `tests/eval/test_datasets.py` add `"suggestions"` to the test-local `CAPABILITIES` list, change `test_total_case_count_at_least_60` to assert `== 102`, and add `test_suggestions_capability_has_ten_full_suite_cases` (filter `capability="suggestions"` → 10 cases, all `suite == "full"`) and `test_multi_intent_goldens_declare_tasks_expected` (every routing golden whose id starts with `routing-multi-` has `expected_tasks` with ≥2 entries and `"tasks_expected"` in `metrics`, and no `expected_flow`). Then: append `"suggestions"` to `CAPABILITIES` in `eval/adapters/config.py`; recover the two legacy files with `git show 4e032c7:apps/api/eval/datasets/multi_intent.json` / `...suggestions.json`; write `eval/datasets/suggestions.json` with the 10 cases as ids `suggestions-happy-{vi,en}-01..05`, capability `suggestions`, scenario `happy`, language per case, suite `full`, `expected_flow` as in the legacy file, `metrics: ["flow_match", "suggestion_relevance"]`, `notes: "Ported from main@4e032c7 legacy suggestions.json"`; append to `routing.json` the 6 multi-intent cases with expectations re-derived from supervisor v10 (brief §Evidence, Inference row): "Find flights to Tokyo and tell me the weather there" and "Plan my Tokyo weekend: find flights, check the weather, then draft an itinerary" → `expected_flow: planner`, `metrics: [flow_match]` (planner owns flights and weather); "How much have we spent so far, and suggest a few things to do next?" → `expected_tasks: ["budget","concierge"]`, `metrics: ["tasks_expected"]`; "Plan everything for a Tokyo weekend: … local tips and a day-by-day plan" → `expected_tasks: ["planner","concierge"]`, `metrics: ["tasks_expected"]`; "What's the weather in Bali this week?" → `expected_flow: concierge`; "Move day 2 before day 3" → `expected_flow: planner`. Ids `routing-multi-en-01..04` for the four multi-domain phrasings (including the two that resolve to a single planner) and `routing-happy-en-06/07` for the two single-domain ones; `notes` on each multi case cites the v10 rule so a later prompt bump can re-derive them. All new cases: scenario `happy`, suite `full`, language `en`.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_datasets.py -q`
- **Done:** `test_datasets.py` passes with the 102 assertion; `OPENAI_API_KEY= ../../.venv/bin/python -m eval --suite full --dry-run` lists 84 goldens (68 existing full + 16 ported; 102 total with the 18 smoke) and exits 0; smoke count unchanged at 18. Record in SUMMARY `### Deviations` that two design-component-8 follow-on cases were ported as planner-only per the brief's v10 Inference row.
- **Criteria:** SC-9
- **Interfaces:** Consumes `evalkit/types.py` and `evalkit/metrics/deterministic.py` from Task 1.3 (the store validates metric names at load) and the pre-existing Taxonomy. Produces `eval/datasets/suggestions.json`, `eval/datasets/routing.json` (+6), `eval/adapters/config.py` (suggestions capability).

### Task 2.2 — Eval README: the local gate ritual (wave 2)

- **Files:** apps/api/eval/README.md
- **Action:** Replace the CI section with: the PR job is keyless (`pytest tests/eval` + dry-run); the judged suite never runs on CI (decision E002, `specs/review-b7-eval-baseline-ci/ESCALATIONS.md`); the gate is `make eval-check` run locally before merging an agent/prompt/tool change, costing 84 agent turns plus about 105 judge calls at k=3 (the full suite; smoke goldens are excluded by the exact suite filter); how to refresh the baseline (`make eval-full` → inspect → `make eval-baseline` → commit `eval/baselines/main.json` with the reason in the commit message); the `expected_tasks` golden field and `tasks_expected` metric (set-equality, multi-intent turns end in `current_flow == "synthesize"` so `flow_match` does not apply); that `Trace.meta` carries `tasks` and `suggestions`; the `suggestions` capability. Remove every sentence describing a nightly run.
- **Verify:** `! grep -q -i -e "nightly" -e "schedule" apps/api/eval/README.md`
- **Done:** README has zero matches for `nightly`/`schedule`, and contains the strings `make eval-check`, `expected_tasks`, `tasks_expected`, `E002`.
- **Criteria:** SC-11
- **Interfaces:** Consumes `apps/api/Makefile` from Task 1.6. Produces `apps/api/eval/README.md`.

### Task 3.1 — Pre-flight: seed `synthesize`, prove one real capability run (wave 3)

- **Files:** specs/review-b7-eval-baseline-ci/SUMMARY.md
- **Action:** Data-only preparation, no code. (1) Copy `.env` into the worktree's `apps/api/` (Global Constraints). (2) Seed the NULL-model row: from the main checkout, `docker exec -w /app -e PYTHONPATH=/app api-api-1 python scripts/seed_agent_config.py --provider openai --model gpt-5.4-mini --nodes synthesize`, then `docker exec api-api-1 touch app/main.py`; confirm with `docker exec api-db-1 sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "select model from agent_config where agent_name='"'"'synthesize'"'"'"'` printing `gpt-5.4-mini`. (3) Run one real, cheap capability: `../../.venv/bin/python -m eval --suite full --capability routing --out eval/reports/preflight.json` (17 goldens: 11 existing full-suite + 6 ported, incl. the two multi-task ones; the 2 smoke routing goldens are excluded by the suite filter; k=1). (4) Record in `SUMMARY.md` under `### Verify` the seed command, the run command, its exit code, and the per-case result for `routing-multi-en-*`. If any case's checks mention `403`, stop and escalate (in-flight hard gate: external provider).
- **Verify:** `cd apps/api && ../../.venv/bin/python -c "import json;r=json.load(open('eval/reports/preflight.json'));assert r['run_meta']['summary']['total_cases']==17;bad=[c['golden_id'] for c in r['per_case'] for k in c['checks'] if '403' in (k.get('detail') or '')];assert not bad,bad"`
- **Done:** `preflight.json` exists with 17 cases and no `403` in any check detail; the `synthesize` row shows `gpt-5.4-mini`; SUMMARY.md carries the rows.
- **Criteria:** SC-3
- **Interfaces:** Consumes the dev DB agent_config table, the copied .env, and scripts/seed_agent_config.py (all unchanged). Produces `eval/reports/preflight.json` (untracked, gitignored) and `specs/review-b7-eval-baseline-ci/SUMMARY.md` (pre-flight evidence rows).

### Task 3.2 — Re-validate: full k=3 run and golden triage (wave 4)

- **Files:** apps/api/eval/datasets/routing.json, apps/api/eval/datasets/flight_search.json, apps/api/eval/datasets/hotels.json, apps/api/eval/datasets/budget.json, apps/api/eval/datasets/booking.json, apps/api/eval/datasets/journal.json, apps/api/eval/datasets/memory.json, apps/api/eval/datasets/language.json, apps/api/eval/datasets/dates.json, apps/api/eval/datasets/errors.json, apps/api/eval/datasets/suggestions.json, apps/api/evalkit/metrics/judged.py, apps/api/tests/eval/test_metrics_judged.py, specs/review-b7-eval-baseline-ci/SUMMARY.md, specs/review-b7-eval-baseline-ci/TRIAGE.md
- **Action:** Run `make eval-full` (writes `eval/reports/latest.json` + `latest.html`; 84 agent turns, ~105 judge calls; if the run aborts with `EVAL MISCONFIGURED` exit 2, fix `EVAL_EXTRACTOR_MODEL` in `.env`, not code). Write `TRIAGE.md`: one row per failing case — `golden_id | failing checks | class (stale-golden / agent-defect / eval-defect) | action`. Class rules: **stale-golden** when the expectation contradicts supervisor v10 or a renamed tool (edit the golden's `expected_*`/`metrics`, cite the prompt line in `notes`); **agent-defect** when the golden matches the prompt's stated rule but the agent misbehaves (open a GitHub issue with `gh issue create --repo minhtran3124/travel-pi` titled `eval: <golden_id> …`, put the issue number in the golden's `notes`, keep the expectation); **eval-defect** when the harness is wrong (e.g. `GEval` rejects an empty `actual_output` on booking goldens — then add a guard in `evalkit/metrics/judged.py` returning `not_applicable`, with a unit test in `tests/eval/test_metrics_judged.py`, and record it as a Rule-1 deviation; `judged.py` and its test are listed in Files for exactly this contingency and stay untouched otherwise). After edits, re-run `make eval-full` once; loop at most twice. Record both run commands, exit codes, and pass counts in `SUMMARY.md`.
- **Verify:** `cd apps/api && ../../.venv/bin/python -c "import json;r=json.load(open('eval/reports/latest.json'));m=r['run_meta'];assert m['suite']=='full' and m['repeat']==3 and m['judge_available'] is True and m['summary']['total_cases']==84,m"`
- **Done:** `latest.json` is a judged full-suite k=3 run over 84 cases; `TRIAGE.md` classifies every failing case; every stale-golden row has a corresponding dataset edit and every agent-defect row an issue number; `tests/eval/test_datasets.py` still passes after edits.
- **Criteria:** SC-3
- **Interfaces:** Consumes `eval/reports/preflight.json` from Task 3.1 (proves the environment) and the make eval-full target. Produces `eval/reports/latest.json` (untracked), `specs/review-b7-eval-baseline-ci/TRIAGE.md`, corrected `eval/datasets/routing.json` and sibling dataset files.

### Task 3.3 — Commit the baseline and prove the gate (wave 5)

- **Files:** apps/api/eval/baselines/main.json, specs/review-b7-eval-baseline-ci/SUMMARY.md
- **Action:** `make eval-baseline` (copies the Task 3.2 `latest.json` to `eval/baselines/main.json`). Prove the gate both ways: `make eval-compare` against the identical report must exit 0; then write a degraded copy with a python one-liner that flips every `passed` to `false` for `capability == "routing"` in `eval/reports/latest.json` and rebuilds `per_capability["routing"]["pass_rate"]` to 0.0 — `make eval-compare` must fail (make exit 2) and its table must print `REGRESSED` on the `routing` row; restore `latest.json` from the baseline afterwards. Record both exit codes in `SUMMARY.md ### Verify` with `Criterion` SC-4/SC-5, fill `### Rollback` (`git revert <sha>` of the baseline commit), `### Not auto-verified` (judge variance beyond k=3; agent-defect goldens intentionally failing in the baseline — list their ids), and `### Rationale`/`### Alternatives`.
- **Verify:** `cd apps/api && cp eval/baselines/main.json eval/reports/latest.json && make eval-compare`
- **Done:** `eval/baselines/main.json` is tracked by git; the identical-report compare exits 0; the degraded-report compare makes `make` exit 2 with `REGRESSED` in its table; `python3 ../../../../../.claude/scripts/verify_summary.py --lane review-b7-eval-baseline-ci` exits 0.
- **Criteria:** SC-3, SC-4, SC-5
- **Interfaces:** Consumes `eval/reports/latest.json` from Task 3.2 and `apps/api/Makefile` from Task 1.6. Produces `apps/api/eval/baselines/main.json`, completed `specs/review-b7-eval-baseline-ci/SUMMARY.md`.

## 5. Risks

- **`synthesize` NULL model → 403** on every multi-task golden. Mitigated by Task 3.1 (seed + cheap real run before the paid full run). Data change only; no `app/**`.
- **Legacy multi-intent expectations are stale under supervisor v10** — ported with v10-derived expectations (Task 2.1) and confirmed by the real run (3.1/3.2). If v10 routes differently from its own stated rule, that is an agent-defect issue, not a golden edit.
- **`GEval` may reject an empty `actual_output`** (booking goldens interrupt at HITL and declare `suggestion_relevance`). Handled as eval-defect in Task 3.2 with a `not_applicable` guard; it is the only code edit allowed there.
- **Judge variance**: k=3 averages only judged metrics; routing is single-shot. The 0.05 tolerance plus the masked-flip rule is the accepted trade-off (E003). A flaky capability discovered in 3.2 gets a `notes` entry, not a threshold change.
- **Suite filter excludes smoke from the baseline**: the 18 smoke goldens are never part of `eval/baselines/main.json`; they remain the keyless PR set. Widening the filter is a separate evalkit decision, out of scope.
- **Shared dev Postgres**: eval threads are written to the dev checkpointer under `eval-*` thread ids and the `eval` user id; no cleanup task — same as the July real runs.
- **Worktree drift**: the main checkout is on another branch with a dirty tree; all commits land on `feat/agent-eval-pipeline` in the worktree, none on `main`.

## 6. Status Log

- 2026-09-07 — plan written (writing-plans) after design.md approval and Deep research brief; two reviewer passes fixed exit codes, run counts (84 full / 17 routing), script paths; not yet executed.
- 2026-09-07 — tasks 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7 complete; commits 04ec68e, de64ba4, 5d79fad, 3114808, 1ff23e4, c600a54, 873a487 (all reviews pass/approved; Minor findings in .harness-state/sdd/ledger.md)
