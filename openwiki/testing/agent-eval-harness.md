---
type: testing
title: Agent evaluation harness
description: How the agent's behaviour is measured — the framework-free evalkit engine (typed goldens, five ports, a metric registry with deterministic, trajectory, judged and oracle families, a k-repeat runner, JSON and HTML reports, and a baseline comparison that is the regression gate) and the travel-pi binding that drives the real LangGraph graph with production agent config, recomputes ground truth from the seeded database, groups goldens by capability and scenario, and the smoke, full, baseline, compare and check targets with the rule that the judged suite never runs on CI.
tags: [eval, evalkit, goldens, metrics, baseline, regression-gate, deepeval, agent-quality]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-18T04:47:06.927Z
sources:
  - id: openwiki-source-9ea7004cd60fc78ed888a032
    resource: repo://.github/workflows/eval.yml
  - id: openwiki-source-d0bca65c451a342754c00642
    resource: repo://apps/api/eval/__main__.py
  - id: openwiki-source-510ce0fb2893dfab9741b338
    resource: repo://apps/api/eval/adapters/config.py
  - id: openwiki-source-1392d3748f58e2a370e791cb
    resource: repo://apps/api/eval/adapters/db_oracle.py
  - id: openwiki-source-fe321bd429ab358b3a4ab229
    resource: repo://apps/api/eval/adapters/langgraph_runner.py
  - id: openwiki-source-5c0375d47426cdee9d78b236
    resource: repo://apps/api/eval/README.md
  - id: openwiki-source-3df8f9dd6c6775f4c5734fba
    resource: repo://apps/api/evalkit/baseline.py
  - id: openwiki-source-54675720b000626feb2c4a61
    resource: repo://apps/api/evalkit/ports.py
  - id: openwiki-source-33cd330cb333dbfac76bae0f
    resource: repo://apps/api/evalkit/README.md
  - id: openwiki-source-f5e1f3be457ef1385785f5fd
    resource: repo://apps/api/evalkit/runner.py
  - id: openwiki-source-74dac8f3a8700bf870db47a8
    resource: repo://apps/api/Makefile
  - id: openwiki-source-ed39d2ed0ae757d571868fda
    resource: repo://apps/api/tests/eval/test_baseline.py
  - id: openwiki-source-2f52e7c7b6bc1ae415f76f02
    resource: repo://apps/api/tests/eval/test_boundary.py
  - id: openwiki-source-22884d161b4e8e532d619b5c
    resource: repo://apps/api/tests/eval/test_datasets.py
generated: { by: "claude-code", at: "2026-09-18T04:47:06.927Z" }
---

# Agent evaluation harness

Unit tests prove the graph wires correctly with a `FakeLLM`; they cannot say whether the real agent answers well. That is the job of the eval harness under `apps/api/`, split into two directories with one hard boundary between them.

## `evalkit/`: the portable engine

`evalkit/` is a framework-free core whose only runtime dependency is `pydantic`. Its one rule is enforced by `tests/eval/test_boundary.py`, which walks every `.py` file under it with `ast` and fails naming the file if it imports `app.*`, `fastapi`, `sqlalchemy`, `langgraph` or `langchain` (optional metric libraries such as `agentevals` and `deepeval` are allowed). Everything project-specific enters through five `typing.Protocol` ports in `evalkit/ports.py`:

| Port | Role |
|---|---|
| `AgentRunner.run(golden) -> Trace` | Drives your agent for one golden and captures reply, tool calls, flow and messages |
| `Oracle.lookup(kind, params)` / `supports(kind)` | Optionally recomputes ground truth from your own data |
| `Metric.name` / `evaluate(golden, trace, oracle) -> CheckResult` | A scoring rule, registered by name |
| `DatasetStore.load(**filters)` / `save(goldens)` | Golden storage; `JsonDatasetStore` ships in core (one JSON file per capability) |
| `BaselineStore.save/load` | Report persistence; `JsonBaselineStore` ships in core |

A `Taxonomy` (capabilities, scenarios, per-capability thresholds) is plain data supplied by the host, never a core enum, so another project adopts the engine by implementing `AgentRunner`, supplying a taxonomy and a dataset directory, and calling `evalkit.cli.main()`.

**Metrics** live in `evalkit/metrics/` in four families: deterministic (`flow_match`, `tools_expected` in subset or exact mode, `tasks_expected` for multi-intent, `reply_language`, `non_empty_reply`), trajectory (via `agentevals`), judged (temperature-0 DeepEval G-Eval rubrics such as `response_language`, `search_vs_booking`, `no_hallucination`, `format_quality`, defined as data in a `RUBRICS` table) and oracle (`oracle_fact_check`, which extracts claimed values from the reply and compares them with the oracle's computed truth, never adjudicating on its own). Each golden declares the explicit `metrics` it is scored on; a golden with none falls back to its capability's default and then to the keyless `DEFAULT_METRIC_NAMES`, and `non_empty_reply` is **always on** because every reply-dependent metric reports "not applicable" on an empty reply, which would otherwise score all-green. A metric name with nothing registered fails at dataset load, not minutes into a paid run.

**Runner and reports.** `run_eval` executes goldens (single `input` or sequential `turns` on one thread), applies `repeat=k` only to metrics that expose a mutable repeat count (the judged ones), skips judged metrics when no judge key is available, and builds a `Report` with a binary pass rate per capability compared to its threshold. `report_exit_code` returns 2 while any capability sits below threshold, but the report is still written.

**Baseline comparison is the gate.** `evalkit.baseline.compare` diffs a report against the committed baseline and `Diff.exit_code()` is non-zero on either rule: a capability's pass rate dropping more than the tolerance (default 0.05) below its baseline, or a specific case flipping pass to fail inside a capability whose rate dropped by any amount, which catches a real regression that an unrelated fix in the same run would otherwise cancel out. A capability with no baseline entry never trips the gate. `tests/eval/test_baseline.py` covers regressed, improved, identical and within-tolerance runs.

## `eval/`: the travel-pi binding

`eval/__main__.py` is the only place allowed to import `app.*`. It wires `JsonDatasetStore` over `eval/datasets/` with the taxonomy from `eval/adapters/config.py` (eleven capabilities: flight search, hotels, booking, budget, journal, memory, language, dates, errors, routing, suggestions; five scenarios: happy, ambiguous, multi-turn, tool failure, adversarial; every threshold 0.7), registers the real `oracle_fact_check` extractor only when `OPENAI_API_KEY` holds a non-placeholder value (the checked-in `.env` ships `test`, which must never count as real), and hands `evalkit.cli.main` a `LangGraphRunner` plus a `DbOracle` on an isolated session.

- **`LangGraphRunner`** drives the compiled travel graph exactly as the chat endpoint would: it pairs every `ToolMessage` back to its tool call by id (never by position), serializes the message list to plain dicts, resumes a `plan_approval` interrupt with the golden's `hitl` decision, and runs post-turn memory extraction so memory goldens see real store writes. Before a real run, `_prod_agent_context` loads the DB agent config and builds a **premium, authenticated** context mirroring the router, because a free or anonymous context would route every booking golden into the tier gate and grade the gate instead of the agent, and an env-default model would grade an agent nobody ships.
- **`DbOracle`** recomputes truth through the same services the tools call (`flight_offers`, `hotel_availability`, `fx_rate`, `trip_budget`), never by re-deriving the seed math and never by asking the agent (see [Bookings, flights and hotels](../domain/bookings-flights-and-hotels.md)).
- **`--dry-run`** lists goldens with a stand-in runner and touches no agent, key or database, because constructing the real runner resolves models eagerly.
- **`EVAL_EXTRACTOR_MODEL`** configures the oracle extractor's model; it is eval infrastructure and deliberately not an `agent_config` row.

## Goldens

`eval/datasets/<capability>.json` holds the goldens (84 today: 18 tagged `suite=smoke`, 66 `full`; roughly half Vietnamese). Ids must be globally unique across files (a duplicate raises at load, naming both files), exactly one of `input` or `turns` is required, `oracle_checks` name a kind the oracle supports, and a golden may only be tagged `smoke` if every metric it declares is keyless; `tests/eval/test_datasets.py` enforces that, plus minimum case counts and that every capability has at least one case. **Read a golden's declared metrics, not its name or notes**: the notes describe intent, the metrics are what is scored. `eval/README.md` documents the matrix, the known thin scenarios and how to add a golden, metric or capability.

## Running it

From `apps/api/` with the root venv and the Docker database up (the runner reads `agent_config` and seed data from Postgres and needs `apps/api/.env`):

| Target | What it does | Cost |
|---|---|---|
| `python -m eval --suite smoke --dry-run` | Lists goldens, no agent | free |
| `make eval-smoke` | 18 smoke goldens through the real agent, deterministic and trajectory checks only | provider calls, no judge |
| `make eval-full` | 84 goldens, judged metrics with `--repeat 3`, JSON and HTML report under `eval/reports/` | paid, about ten to fifteen minutes |
| `make eval-compare` | Diff `reports/latest.json` against `eval/baselines/main.json`; exit 1 on regression | free |
| `make eval-check` | `eval-full` then `eval-compare`: the local gate before merging prompt, agent or tool changes | paid |
| `make eval-baseline` | Adopt the latest report as the committed baseline | free |

The judged suite **never runs on CI** by decision: `eval.yml` only runs the offline `tests/eval` suite and a dry-run on PRs touching agent code, so judge spend and judge variance stay bounded and human-gated (see [Local development, Docker and CI](../operations/local-dev-docker-and-ci.md)). After an intentional behaviour change, run `make eval-full`, inspect the report, then `make eval-baseline` and commit `eval/baselines/main.json` with the reason. Prompt changes in particular should be verified here rather than by prompt content tests alone (see [Prompt registry and versioning](../agent/prompt-registry.md)).
