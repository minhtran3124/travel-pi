---
slug: agent-eval-pipeline
status: proposed
owner: minhtran
created: 2026-07-13
---

# Agent Eval Pipeline — portable engine (evalkit) + travel-pi binding

## 1. Motivation

The chatbot agent has an offline DeepEval harness (MIN-58): 24 cases, 4 G-Eval rubrics, run by hand. Production needs a capability × scenario golden matrix, judge-free deterministic checks, trajectory verification, judge-variance control, baseline regression gating, and CI.

Two accepted design constraints shape it:
- **Portability** (`design-portability.md`): the engine must be extractable as a standalone package / MCP server for other projects. Core (`evalkit/`) never imports `app.*`; everything project-specific enters via a port.
- **DB-as-Oracle** (`design-agentic-evolution.md`): this backend is deterministic (MD5-seeded flights/hotels, DB-backed trips/budget/FX), so eval can *compute* ground truth instead of asking a judge. Oracle beats rubric wherever a fact is computable.

Research: `research-brief.md`.

## 2. Non-goals

- MCP server (phase 3 — nothing to expose until the report contract is stable).
- Production tracing / online eval / Langfuse (phase 2 — new external service, Rule-4 gate).
- Golden-generation and failure-mining agents (phase 2.5 — they need the report schema as their action space).
- Changing agent behavior or prompts. This initiative only measures.

## 3. Success Criteria

1. `evalkit/` imports zero `app.*` — enforced by a boundary test, not by convention.
2. `make eval-smoke` runs keyless (deterministic + trajectory + FakeLLM routing) in <5 min, exit 1 on failure.
3. `make eval-full` runs the judged matrix (temp-0, k=3 repeats) and writes a versioned Report JSON with per-capability pass rates.
4. `make eval-compare` exits 1 when a capability's pass rate drops below baseline − tolerance.
5. ≥60 schema-validated, tagged goldens across the 9-capability × 5-scenario matrix (VN + EN).
6. Oracle fact-checking works for at least flights, hotels, and trip budget — `no_hallucination` becomes a computation, not an opinion.
7. CI: PR job keyless; nightly judged job skips cleanly when the API-key secret is absent.
8. `evalkit/README.md` documents the port contract (how to adopt in another project); `eval/README.md` documents add-a-golden / add-a-metric / add-a-capability.

## 4. Matrix (dataset target)

Capabilities: `flight_search`, `hotels`, `booking`, `budget`, `journal`, `memory_personalization`, `language_vi_en`, `date_resolution`, `error_handling`.
Scenarios: `happy`, `ambiguous`, `multi_turn`, `tool_failure`, `adversarial`.
3–5 goldens per populated cell; empty cells are allowed and *visible* (the schema makes gaps countable) — they become the golden-generation agent's backlog in phase 2.5.

## 5. Tasks

### Task 1.1 — evalkit core: types, ports, registry, boundary test

```xml
<task id="1.1" wave="1">
  <files>apps/api/evalkit/__init__.py, apps/api/evalkit/types.py, apps/api/evalkit/ports.py, apps/api/evalkit/registry.py, apps/api/evalkit/pyproject.toml, apps/api/tests/eval/test_boundary.py, apps/api/tests/eval/test_types.py</files>
  <action>Create the portable core skeleton per specs/agent-eval-pipeline/design-portability.md. types.py: pydantic models Golden (id, capability:str, scenario:str, language, suite, input|turns, expected_flow?, expected_tools?, expected_trajectory?, oracle_checks?, metrics?, notes?), ToolCall(name,args,output), Trace(reply, tool_calls, flow, messages, meta), CheckResult(name,passed,score?,detail), CaseResult, Report(schema_version, run_meta, per_case, per_capability). ports.py: Protocols AgentRunner, Oracle, Metric, DatasetStore, BaselineStore. registry.py: decorator-based metric registry; capability/scenario are validated STRINGS against a project-supplied taxonomy, never core enums. pyproject.toml declares evalkit as its own installable package (deps: pydantic only at this stage). test_boundary.py: walk every module under evalkit/ with ast, assert no import of `app.` / fastapi / sqlalchemy / langgraph — this is the portability gate.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_boundary.py tests/eval/test_types.py -x -q</verify>
  <done>Core types+ports importable standalone; boundary test green and would FAIL on an app.* import.</done>
</task>
```

### Task 1.2 — Deterministic metrics (judge-free layer)

```xml
<task id="1.2" wave="1">
  <files>apps/api/evalkit/metrics/__init__.py, apps/api/evalkit/metrics/deterministic.py, apps/api/tests/eval/test_metrics_deterministic.py</files>
  <action>Registered Metric impls operating on (Golden, Trace): flow_match, tools_expected (exact/subset modes), reply_language (vi/en heuristic — self-contained in evalkit, no app.core.text import), non_empty_reply, tool_args_shape (validate each ToolCall.args against a caller-supplied JSON schema on the golden). All return CheckResult. Pure functions, no network, no LLM. Unit-test with fabricated Traces including the failing cases.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_metrics_deterministic.py -x -q</verify>
  <done>5 deterministic metrics registered and unit-tested offline.</done>
</task>
```

### Task 1.3 — Report + baseline (regression gate, pure JSON)

```xml
<task id="1.3" wave="1">
  <files>apps/api/evalkit/report.py, apps/api/evalkit/baseline.py, apps/api/tests/eval/test_baseline.py</files>
  <action>report.py: build a Report from CaseResults (per-capability BINARY pass rates, not mean scores — see research-brief §5), save/load JSON with schema_version. baseline.py: save(report, path) and compare(report, baseline, tolerance=0.05) -> Diff (per-capability rate deltas, per-case pass→fail flips), rendering a table and returning a non-zero exit code on regression beyond tolerance. Pure JSON in/out — no LLM, no agent, fully unit-testable.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_baseline.py -x -q</verify>
  <done>Fabricated regression exits 1; improvement/no-change exits 0; Report JSON round-trips.</done>
</task>
```

### Task 2.1 — travel-pi adapters: LangGraph runner + config taxonomy

```xml
<task id="2.1" wave="2">
  <files>apps/api/eval/adapters/__init__.py, apps/api/eval/adapters/langgraph_runner.py, apps/api/eval/adapters/config.py, apps/api/tests/eval/test_langgraph_runner.py</files>
  <action>langgraph_runner.py: AgentRunner port impl — port the logic of the existing eval/harness.py (build_eval_graph, invoke, extract final AIMessage / tools_called / current_flow) but ALSO capture every ToolMessage content into Trace.tool_calls[].output and the ordered message list into Trace.messages. Multi-turn goldens (turns) replay on one thread_id. config.py: the project taxonomy — the 9 capabilities, 5 scenarios, per-capability thresholds, dataset/baseline paths. Test with FakeLLM (no network), asserting the Trace shape incl. tool outputs. Leave the legacy eval/harness.py in place for now (removed in task 4.1) to keep tests/eval green.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_langgraph_runner.py -x -q</verify>
  <done>Runner returns a fully-populated Trace (reply + tool_calls with outputs + messages + flow) under FakeLLM.</done>
</task>
```

### Task 2.2 — Trajectory metrics (agentevals)

```xml
<task id="2.2" wave="2">
  <files>apps/api/evalkit/metrics/trajectory.py, apps/api/requirements-ai.txt, apps/api/tests/eval/test_trajectory.py</files>
  <action>Add pinned agentevals (langchain-ai, MIT) to requirements-ai.txt. trajectory.py: registered Metric wrapping its deterministic graph-trajectory match over Trace.messages against golden.expected_trajectory, modes strict|unordered|subset (default subset). No LLM-judge trajectory in phase 1. Returns CheckResult. Note: evalkit may depend on agentevals (a library), never on this repo's app — the boundary test must still pass.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_trajectory.py tests/eval/test_boundary.py -x -q</verify>
  <done>Deterministic tool-call-order checking usable per golden; boundary intact.</done>
</task>
```

### Task 2.3 — Judged metrics (G-Eval, temp-0, k-repeat)

```xml
<task id="2.3" wave="2">
  <files>apps/api/evalkit/metrics/judged.py, apps/api/tests/eval/test_metrics_judged.py</files>
  <action>Port the 4 G-Eval rubrics (response_language, search_vs_booking, format_quality, no_hallucination) into evalkit/metrics/judged.py as registered Metrics built on DeepEval, with judge temperature 0 and k-repeat averaging (k from the runner). no_hallucination now receives retrieval_context assembled from Trace.tool_calls[].output. Rubrics are DATA (a dict of name -> criteria/steps) so another project can swap them without touching code. Tests: rubric registration + averaging logic with a stubbed judge; no network in CI.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_metrics_judged.py -x -q</verify>
  <done>Judged metrics registered, temp-0, k-averaged, and grounded by tool-output retrieval_context.</done>
</task>
```

### Task 2.4 — Dataset matrix + validated store

```xml
<task id="2.4" wave="2">
  <files>apps/api/evalkit/dataset.py, apps/api/eval/datasets/, apps/api/tests/eval/test_datasets.py</files>
  <action>evalkit/dataset.py: JsonDatasetStore (DatasetStore port) — loads a dataset dir, validates every case against Golden + the project taxonomy, fails loud with file+id, filters by suite/capability/scenario, asserts unique ids. Restructure eval/datasets/ one file per capability (flight_search, hotels, booking, budget, journal, memory, language, dates, errors, routing). Migrate the existing 24 cases into the new schema with tags; port MIN-65 memory/suggestion cases from specs/min-65-chatbot-intelligence/ if present; author new goldens to reach ≥60 covering happy/ambiguous/multi_turn for every capability, VN + EN. Mark 15–20 representative cases suite=smoke. Add oracle_checks to flight/hotel/budget goldens (kind + params) for task 3.2.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_datasets.py -x -q</verify>
  <done>≥60 schema-valid tagged goldens across 9 capability files; smoke subset marked; store filters work.</done>
</task>
```

### Task 3.1 — Runner + CLI

```xml
<task id="3.1" wave="3">
  <files>apps/api/evalkit/runner.py, apps/api/evalkit/cli.py, apps/api/eval/__main__.py, apps/api/tests/eval/test_runner.py</files>
  <action>runner.py: run(goldens, runner: AgentRunner, metrics, oracle=None, repeat=1) -> Report. Per golden: AgentRunner.run -> apply each applicable metric (per-case `metrics` filter, else the capability default) -> CaseResult; judged metrics repeat k times and average; aggregate to per-capability binary pass rates; threshold per capability from the taxonomy; overall exit code. cli.py: framework-free argparse — `--suite smoke|full --capability X --repeat k --out report.json --dry-run`, deps injected by the caller. eval/__main__.py: the travel-pi wiring (LangGraphRunner + DbOracle + JsonDatasetStore + config) so `python -m eval --suite smoke` works. Judged metrics are skipped with a loud log when no judge key is present (keyless smoke must stay green).</action>
  <verify>cd apps/api && ../../.venv/bin/python -m eval --suite smoke --dry-run && ../../.venv/bin/python -m pytest tests/eval/test_runner.py -x -q</verify>
  <done>One entrypoint; keyless smoke runs deterministic+trajectory; judged adds on when keyed; Report JSON written; thresholded exit code.</done>
</task>
```

### Task 3.2 — DB-as-Oracle + OracleFactCheck metric

```xml
<task id="3.2" wave="3">
  <files>apps/api/eval/adapters/db_oracle.py, apps/api/evalkit/metrics/oracle.py, apps/api/tests/eval/test_db_oracle.py</files>
  <action>db_oracle.py: Oracle port impl for travel-pi — recomputes ground truth through the SAME services/repositories the agent's tools use (NOT through the agent): kinds `flight_offers` (cheapest/price range for a seeded route+date), `hotel_availability`, `trip_budget` (total_spent, gaps), `fx_rate`. evalkit/metrics/oracle.py: OracleFactCheck — for each golden.oracle_checks entry, an LLM EXTRACTS the claimed value from the reply (extraction only) and CODE compares it against oracle.lookup() with a tolerance; disagreement = fail with both values in detail. Follow docs/solutions/agent/llm-parses-code-computes.md: the LLM never decides correctness. Extraction is stubbable so tests run offline against a seeded temp DB.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_db_oracle.py -x -q</verify>
  <done>Oracle recomputes flight/hotel/budget truth from the DB; fact-check fails on a fabricated wrong price and passes on the right one.</done>
</task>
```

### Task 4.1 — Make targets, legacy cleanup, READMEs

```xml
<task id="4.1" wave="4">
  <files>apps/api/Makefile, apps/api/evalkit/README.md, apps/api/eval/README.md, apps/api/eval/harness.py, apps/api/eval/run_deepeval.py, apps/api/eval/run_eval.py, apps/api/eval/loader.py, apps/api/eval/metrics.py, apps/api/eval/metrics_geval.py</files>
  <action>Make targets: eval-smoke (python -m eval --suite smoke, keyless), eval-full (--suite full --repeat 3), eval-baseline (save), eval-compare (compare vs eval/baselines/main.json). Remove the legacy modules now fully superseded (harness.py, run_deepeval.py, run_eval.py, loader.py, metrics.py, metrics_geval.py) and delete/retarget their orphaned tests — ONLY after 3.1 covers their behavior; keep routing-accuracy coverage by porting routing.json into the matrix as its own capability. evalkit/README.md: the port contract — how to adopt evalkit in another project (implement AgentRunner, optionally Oracle, supply a taxonomy + dataset dir) and the future MCP surface. eval/README.md: add-a-golden / add-a-metric / add-a-capability, local vs docker run (document the AgentConfigCache bypass gotcha + required env), baselines and CI gating.</action>
  <verify>cd apps/api && make -n eval-smoke eval-full eval-baseline eval-compare && ../../.venv/bin/python -m pytest tests/eval -q</verify>
  <done>Four make targets; no dead legacy eval modules; both READMEs document their contract; full tests/eval suite green.</done>
</task>
```

### Task 4.2 — CI wiring

```xml
<task id="4.2" wave="4">
  <files>.github/workflows/eval.yml</files>
  <action>New workflow, two jobs, do NOT touch ci.yml. (a) eval-smoke on pull_request touching apps/api/app/agents/**, app/prompts/**, app/tools/**, apps/api/eval/**, apps/api/evalkit/**: keyless — boundary test, dataset validation, deterministic + trajectory suite. (b) eval-nightly on schedule + workflow_dispatch: full judged run with secrets.OPENAI_API_KEY, then baseline compare vs eval/baselines/main.json, upload the Report JSON artifact; when the secret is absent, log loudly and exit neutral rather than fail.</action>
  <verify>../../.venv/bin/python -c "import yaml; yaml.safe_load(open('.github/workflows/eval.yml')); print('yaml OK')"</verify>
  <done>PR keyless gate + nightly judged run with regression compare; secret-optional.</done>
</task>
```

## 6. Waves

| Wave | Tasks | Parallel | Files disjoint |
|---|---|---|---|
| 1 | 1.1 core types/ports/boundary · 1.2 deterministic metrics · 1.3 report/baseline | 3 | yes (1.2/1.3 depend on 1.1's types — 1.1 lands first within the wave; see note) |
| 2 | 2.1 langgraph adapter · 2.2 trajectory · 2.3 judged · 2.4 datasets/store | 4 | yes |
| 3 | 3.1 runner/CLI · 3.2 oracle | 2 | yes |
| 4 | 4.1 make/cleanup/READMEs · 4.2 CI | 2 | yes |

> Wave-1 note: 1.2 and 1.3 consume `evalkit/types.py`. To keep the zero-overlap invariant, task 1.1 is executed first (single task), then 1.2 and 1.3 run in parallel — i.e. wave 1 splits into 1a (1.1) and 1b (1.2, 1.3). This is the `wave-shared-file-partition` failure mode from docs/solutions and is being avoided deliberately.

## 7. Risks

- **Portability erosion** — mitigated by the ast boundary test shipping in the first task, before there is anything to leak.
- **Judge cost/variance** — temp-0 + k-repeat + binary per-capability gates; judged runs nightly, never per-PR.
- **Oracle drift** — the oracle depends on the deterministic seed algorithm (CLAUDE.md already forbids changing it); if seeds change, oracle expectations must be regenerated.
- **Legacy removal (4.1)** — deletes modules other tests import; gated behind 3.1 covering their behavior and a full `pytest tests/eval` run. Rollback = `git revert`.
- **Graph-invocation gotchas** — eval bypasses DB agent config (env-model fallback → 403) and needs DB up for tools; smoke suite stays keyless/FakeLLM to avoid both, documented in 4.1.
- **agentevals API drift** — version pinned.

## 8. Status Log

- 2026-07-13 — plan proposed (research: `research-brief.md`; design: `design-portability.md`, `design-agentic-evolution.md`).
