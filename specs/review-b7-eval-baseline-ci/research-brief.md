# review-b7-eval-baseline-ci — Research Brief

Depth: **Deep** (intake lane high-risk → Deep; not reclassified). No waiver. External surface: **none** — no dependency added or upgraded, no new external system (a CI job is *removed*), and the only version-specific API touched (`deepeval` `GEval`/`SingleTurnParams.RETRIEVAL_CONTEXT`) is already in use on the branch at the pinned version. Official-docs search therefore not applicable; upstream search performed locally against the installed packages.

## Bottom Line

| Field | Value |
|---|---|
| **Recommendation** | **reuse existing** — every mechanism the design needs already exists on the branch (`Trace.meta`, `compare` + masked-flip gate, `make eval-baseline/compare`, metric registry, `not_applicable` convention); the work is wiring, data, and one deletion. |
| **Why this is the lightest credible path** | Only two genuinely new units (metric `tasks_expected`, capability `suggestions`) and both follow a pattern that already has 6 siblings. |
| **Confidence** | 85% |
| **Next step** | `writing-plans`: order tasks so the paid baseline run is last and gated by (a) the `synthesize` seed pre-flight and (b) re-derived multi-intent expectations from supervisor v10. |

## Repo Snapshot

| Field | Detected |
|---|---|
| Repo type | monorepo (FastAPI `apps/api`, Next.js `apps/web`); this spec touches `apps/api` + `.github` only |
| Primary language + runtime | Python 3.14 locally (`.venv`), 3.12 in CI (`ci.yml`, `eval.yml`) |
| Frameworks / platforms | LangGraph 1.x graph (`app/agents/graph.py`), DeepEval 4.0.7 (`requirements-ai.txt: deepeval>=4.0,<5`), agentevals 0.0.9 |
| Relevant packages | `apps/api/evalkit/` (portable engine), `apps/api/eval/` (travel-pi binding + goldens), `tests/eval/` (18 files) |
| Detectable versions | deepeval 4.0.7 installed; `GEval.__init__` accepts `evaluation_params: list[SingleTurnParams]` incl. `RETRIEVAL_CONTEXT` (verified by `inspect.signature`) |
| Important constraints | `.claude/rules/behavior.md` (surgical, no adjacent refactors); no `apps/api/app/**` edits (design); E002 no judged eval on CI; commit stage/commit separately; ruff-on-edit strips unused imports |

## Feature Understanding and Assumptions

- **Requested feature:** committed eval baseline + working regression gate on the merged evalkit branch; port main's 16 legacy cases; keyless dry-run; strip nightly from CI; drop standalone manifest (design.md, approved).
- **What success appears to mean:** SC-1..SC-5 in design.md — dry-run exits 0 with `OPENAI_API_KEY=`, `eval.yml` has no `schedule`/`secrets`, `eval/baselines/main.json` committed from a full k=3 run, `make eval-compare` exits 0 vs itself and 1 vs a degraded report, suites green.
- **Assumptions from the request:** tasks fan out in parallel so `expected_tasks` is set-equality; goldens are data and may be corrected; agent defects become issues.
- **Assumptions still needing confirmation:** (1) `GEval.measure` tolerates an empty `actual_output` (booking goldens interrupt at HITL and already declare `suggestion_relevance`; `judged.py:249` passes `trace.reply` unguarded; `deepeval/metrics/utils.py` shows no empty-`actual_output` check but this was not executed). (2) The dev DB row `synthesize` with NULL model resolves to a callable model — see Risks.

## Evidence Ledger

| Label | Evidence |
|---|---|
| `Local` | `evalkit/cli.py:96-98` — `--dry-run` prints goldens and returns **before** touching `agent_runner`; `eval/__main__.py:128-130` still constructs `LangGraphRunner(context=None)` for dry-run → `build_eval_graph` → `build_graph` → `pick()` → `get_agent_llm` → OpenAI client → `OpenAIError: Missing credentials` with an empty key (reproduced). Fix is confined to `eval/__main__.py`. |
| `Local` | `app/agents/supervisor.py:315-340` — `task_agents = [target]` then dedup'd follow-ons; `tasks = [AgentTask(agent=..., query=..., index=...).model_dump()]`. Single-intent turns populate `tasks` with exactly `[target]`, so `tasks_expected` grades single and multi turns uniformly. `AgentTask.agent` is the key to read (`app/agents/schemas.py:20`). |
| `Local` | `app/agents/nodes.py:197` — synthesize sets `current_flow = SYNTHESIZE_NODE ("synthesize")`; `flow_match` is therefore wrong for multi-task goldens (design already avoids it). |
| `Local` | `evalkit/types.py:57-64` — `Trace.meta: dict[str, Any]`; `eval/adapters/langgraph_runner.py:196-206` builds `meta={thread_id, model, elapsed_s, n_turns}` from `out` — `out` already carries `tasks` and `trip_facts` (graph output = full state). |
| `Local` | `app/agents/suggestions.py:135-141` — `suggestions_for_flow(current_flow, *, trip_facts=None, profile=None, preferences="") -> list[str]`; safe to call with only `current_flow` + `trip_facts`. |
| `Local` | `evalkit/metrics/judged.py:169-178, 250` — `build_retrieval_context(trace)` returns `None` when no tool calls else one line per tool call; consumed once at the `LLMTestCase(... retrieval_context=...)` site. Extending it with `trace.meta["suggestions"]` is a one-function change; the `suggestion_relevance` rubric (`judged.py:136-149`) already reads `RETRIEVAL_CONTEXT`. |
| `Local` | `evalkit/metrics/deterministic.py:1-16, 304-309` — metric = small class with `.name` + `evaluate(golden, trace, oracle=None) -> CheckResult`, registered via `register_metric(...)` at import; `not_applicable` = `passed=True, detail="not_applicable: ..."`. Pattern for `tasks_expected`. |
| `Local` | `evalkit/baseline.py` — `compare(report, baseline, tolerance=0.05)` + `Diff.exit_code()` (capability drop beyond tolerance OR masked pass→fail flip); `render_table`. `Makefile:61-65` — `eval-baseline` copies `latest.json` → `eval/baselines/main.json`; `eval-compare` calls `load_report(...)` unguarded → traceback when the file is missing. `.gitignore:61-63` already documents that `eval/baselines/` is committed. |
| `Local` | `.github/workflows/eval.yml` — `schedule:` at line 18; `secrets.OPENAI_API_KEY` at lines 74 (comment) and 85 (env); `eval-nightly` job lines 78-145; `eval-smoke` job (pytest `tests/eval` + dry-run) lines 45-70. |
| `Local` | `app/prompts/supervisor/v10.md:47-55` — "a chain inside ONE specialist's toolset routes to that specialist, `plan=[]`; planner owns flights, hotels, places, weather, routing; only a genuinely independent extra (local tips → concierge) adds a plan step". |
| `Local` | `main@4e032c7:apps/api/eval/datasets/multi_intent.json` — 6 cases: 4 expect `planner`+`[concierge]`, 2 have empty plans. `suggestions.json` — 10 cases (2 planner, 2 concierge, 2 journal, 2 booking, 2 budget), all `metrics=[suggestion_relevance]`, no ids. |
| `Local` | `tests/eval/test_datasets.py:52-65` — asserts `>= 60` total and `15 <= smoke <= 20`; new goldens go to suite `full`, so both stay green; `test_every_taxonomy_capability_has_at_least_one_case` will require ≥1 `suggestions` golden once the capability is added (it will have 10). |
| `Local` | `tests/eval/test_runner.py:223-240` — existing dry-run test uses a recording runner and asserts `runner.calls == []`; `tests/eval/test_langgraph_runner.py:39,122-124` — FakeLLM scripted with `SupervisorIntent(target_agent=...)`; `SupervisorIntent` has a `plan` field (used by `run_plan_eval` in the retired smoke) → a multi-intent trace can be scripted offline. |
| `Local` | Dev DB `agent_config` (Docker `api-db-1`): every node `gpt-5.4-mini` except `synthesize` = NULL model. `app/clients/llm.py:147-152` — row present with NULL model → `model = s.fast_llm_model if fast else s.llm_model`; `synthesize` ∉ `FAST_AGENTS` (`constants.py:53-61`) → `settings.llm_model` default `gpt-5` (`.env` has `LLM_MODEL` commented out). `docs/solutions/agent/new-agent-config-node-seeds-null-model.md` records that this exact fallback 403s on this account. |
| `Local` | `scripts/seed_agent_config.py` flags `--provider --model --base-url --temperature --max-tokens --nodes`; the solution note's exact command seeds one node without touching `app/**`. |
| `Local` | `.env`: `DATABASE_URL=postgresql+psycopg://…@127.0.0.1:5433/travel`, `LLM_PROVIDER=openai`, `EVAL_EXTRACTOR_MODEL=gpt-5.4-mini`, real `OPENAI_API_KEY` — the paid run can be executed from the worktree with `--env-file`/copied `.env` (worktree has no `.env`). |
| `Local` | `eval/reports/*.json` in the main checkout (07-20): smoke 17/18 with judge; `flight_search-happy-*` expect `planner` and pass; only `hotels-happy-en-01` fails (`browse_hotels` not called, reply language `vi`). Full suite never run. |
| `Upstream` | Installed `deepeval 4.0.7`: `SingleTurnParams` includes `RETRIEVAL_CONTEXT`; `LLMTestCaseParams` deprecated in favour of `SingleTurnParams` (already what `judged.py:70` uses). No API change needed. |
| `Inference` | Under v10 the legacy multi-intent expectations are stale: "flights + weather" (cases 1, 2) → planner alone (`plan=[]`); "spent so far + things to do next" (case 3) → `budget` + `concierge`; "plan everything … local tips" (case 6) → `planner` + `concierge`. Port with v10-derived `expected_tasks`, record the derivation in `notes`, and let the re-validation run confirm. |
| `Inference` | `evalkit/pyproject.toml` is referenced only by `evalkit/README.md` §"Optional extras" (line 152) — deletion + README section removal is complete; `test_boundary.py` does not read the manifest. |

## Local Findings

- **Relevant files:** `eval/__main__.py`, `evalkit/{types,cli,runner,baseline,report}.py`, `evalkit/metrics/{deterministic,judged}.py`, `eval/adapters/{langgraph_runner,config}.py`, `eval/datasets/*.json`, `Makefile` (eval targets), `.github/workflows/eval.yml`, `tests/eval/{test_runner,test_datasets,test_langgraph_runner,test_metrics_deterministic,test_metrics_judged,test_baseline}.py`, `evalkit/README.md`, `eval/README.md`.
- **Extension points:** `Trace.meta` (open dict), `register_metric`, `Taxonomy.capabilities`, `Golden` additive fields (pydantic `extra="ignore"`), `build_retrieval_context`.
- **Conventions:** `not_applicable:` detail prefix; goldens ids `<capability>-<scenario>-<lang>-NN`; one dataset file per capability named after it; judged metrics never in `smoke`; Report schema changes must be additive (`report.py` docstring).
- **Reusable as-is:** `compare`/`render_table`/`JsonBaselineStore`, `make eval-baseline`, dry-run listing, HTML report, FakeLLM scripting of `SupervisorIntent(plan=[...])`.
- **Missing locally:** a runner-free dry-run path in `eval/__main__.py`; `expected_tasks` + `tasks_expected`; `suggestions` capability + file; suggestion keys in retrieval context; guarded `eval-compare`; `eval-check`; the baseline file itself.

## Upstream Findings

- **Repositories inspected:** installed `deepeval` 4.0.7 and `agentevals` 0.0.9 in `.venv` (source), i.e. the exact pinned versions — no remote fetch needed.
- **Pattern present upstream:** DeepEval's `retrieval_context` is a free-form `list[str]`; nothing constrains its content to retrieved documents, so appending suggestion-key lines is within contract.
- **Match to this repo:** exact (same version).
- **Gaps:** whether `GEval` raises on an empty `actual_output` was not executed; treat as a re-validation finding, not a design blocker.

## Docs Findings

- none (local-only; no external surface). The only third-party API used is already pinned and exercised on the branch.

## Recommendation

- **Primary:** reuse existing — implement the 13 design components as thin additions; no new abstraction.
- **Why lightest:** every hard part (gate math, report contract, CLI, HTML, dataset validation) exists and is tested; the delta is ~6 small code edits, 2 data files, 1 workflow trim, 1 deletion, 1 paid run.
- **Why the alternative lost:** a dedicated `Trace.tasks` / `Trace.suggestions` schema field would be cleaner but forces a `Trace` model change and touches `report.py`'s additive-only contract; `meta` is the documented extension point and costs nothing.
- **What would flip it:** if `GEval` rejects empty `actual_output`, `suggestion_relevance` on booking goldens needs a guard in `judged.py` (skip → `not_applicable`) — still small, but becomes a required task rather than optional.

## Risks, Unknowns, and Follow-Up Questions

- **Technical risks:** (1) `synthesize` NULL model → 403 on every multi-intent golden during the paid run; mitigate with the seed command from the solution note **before** the run (data change only) and verify with a single `--capability routing` run first. (2) Multi-intent expectations must be re-derived from v10 (see Inference) or the ported goldens will be "stale on arrival". (3) k=3 only repeats judged metrics; deterministic flakiness (routing) is single-shot — accept, it is what the gate measures. (4) Running from the worktree: no `.env` there; either copy `.env` or run with `set -a; source ../../../../apps/api/.env`; the DB is the shared dev Postgres, so eval threads land in the dev checkpointer (thread ids are `eval-*`, isolated by id).
- **Evidence gaps:** GEval empty-output behaviour; whether `tests/eval/test_boundary.py` or any test imports `pyproject.toml` (grep says no).
- **Version uncertainties:** none.
- **Follow-up questions for the user:** none required; the plan can proceed.

## Source Pack

- **Local files read:** `evalkit/{cli,baseline,report,types,runner,registry,ports,dataset}.py`, `evalkit/metrics/{__init__,deterministic,judged,oracle}.py`, `evalkit/README.md`, `evalkit/pyproject.toml`, `eval/__main__.py`, `eval/adapters/{config,db_oracle,extractor,langgraph_runner}.py`, `eval/datasets/*.json`, `eval/README.md`, `Makefile`, `.github/workflows/eval.yml`, `.gitignore`, `app/agents/{supervisor,nodes,graph,constants,schemas,suggestions}.py`, `app/clients/llm.py`, `app/core/config.py`, `app/data/agent_config.py`, `app/prompts/supervisor/v10.md`, `scripts/seed_agent_config.py`, `tests/eval/{test_runner,test_datasets,test_langgraph_runner,test_db_oracle,test_extractor}.py`, `docs/solutions/agent/new-agent-config-node-seeds-null-model.md`, `docs/solutions/harness/verify-against-invented-rule.md`, `specs/agent-eval-pipeline/SUMMARY.md`, `specs/review-b7-eval-baseline-ci/{SUMMARY,ESCALATIONS,design}.md`, `main@4e032c7:apps/api/eval/datasets/{multi_intent,suggestions}.json`, `apps/api/.env` (key names only), dev DB `agent_config` table.
- **Upstream repositories or pages checked:** installed `deepeval==4.0.7` (`deepeval/test_case`, `deepeval/metrics/g_eval`, `deepeval/metrics/utils.py`), `agentevals==0.0.9` — local source inspection of the pinned versions.
- **Official docs domains or pages checked:** - none (local-only; no external surface)

## Evidence Boundary

> Confirmed from artifacts: dry-run key failure (reproduced), `tasks = [target] + …`, `Trace.meta`, `compare` semantics, Makefile targets, workflow line numbers, v10 routing rule, legacy case counts (6 + 10), `synthesize` NULL row, `get_agent_llm` fallback path, DeepEval `RETRIEVAL_CONTEXT` support.
> Inferred from patterns: v10-derived expectations for the 4 multi-intent legacy cases; that `pyproject.toml` deletion is otherwise inert.
> Not checked: GEval behaviour on empty `actual_output`; actual pass/fail of the full suite on the merged branch (never run).
