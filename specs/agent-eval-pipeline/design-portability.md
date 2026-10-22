# Design — Portable eval engine (evalkit) → future MCP / standalone tool

Status: accepted direction 2026-07-13. Constrains PLAN.md from task 1.1 onward.

## Requirement

Build the evaluation system so it can later be extracted as a standalone package / MCP server
and adopted by other projects — without a rewrite. The travel-pi agent is the first *consumer*,
not the substrate.

## The one rule that makes this real

> **`evalkit/` (core) must never import `app.*`.**

Everything project-specific enters through a **port** (a `typing.Protocol`) implemented by an
**adapter** in `eval/` (the travel-pi binding). This is enforced mechanically by a boundary test
(`tests/eval/test_boundary.py`) that fails if any module under `evalkit/` imports the host app.
A rule nobody can silently break is worth more than a doc saying "keep it decoupled".

## Layout

```
apps/api/
  evalkit/                    # PORTABLE core — zero app.* imports, own pyproject.toml
    types.py                  # Golden, Trace, ToolCall, CheckResult, CaseResult, Report
    ports.py                  # Protocols: AgentRunner, Oracle, DatasetStore, Metric, BaselineStore
    registry.py               # name -> Metric registration (decorator), capability/scenario enums are DATA
    metrics/
      deterministic.py        # flow match, tool-set match, language detect, non-empty, shape
      trajectory.py           # agentevals wrappers (strict/unordered/subset)
      judged.py               # G-Eval adapters (DeepEval), temp-0 + k-repeat averaging
      oracle.py               # OracleFactCheck — code computes, LLM only extracts
    runner.py                 # suite/capability filtering, repeat, aggregation -> Report
    baseline.py               # save / compare, per-capability pass-rate diff, exit codes
    report.py                 # Report JSON schema (the stable contract for CI + MCP)
    cli.py                    # `python -m evalkit ...` — thin, framework-free
    mcp/                      # (phase 3) MCP server exposing the SAME ports
  eval/                       # travel-pi BINDING — the only place that knows about `app.`
    adapters/
      langgraph_runner.py     # AgentRunner impl: builds graph, invokes, captures Trace
      db_oracle.py            # Oracle impl: recomputes truth via repositories/services
      config.py               # capabilities, scenarios, thresholds, dataset paths
    datasets/*.json           # goldens (project data)
    baselines/*.json          # committed baselines
    __main__.py               # wires adapters -> evalkit.cli
```

`evalkit` is installable on its own (`pip install -e apps/api/evalkit`) and depends only on
pydantic + deepeval + agentevals — **not** on FastAPI, SQLAlchemy, LangGraph, or this repo.

## Ports (the whole contract)

```python
class AgentRunner(Protocol):
    def run(self, golden: Golden) -> Trace: ...          # reply, tool_calls, flow, messages, meta

class Oracle(Protocol):                                   # ground truth, project-computed
    def lookup(self, kind: str, params: dict) -> Any: ...
    def supports(self, kind: str) -> bool: ...

class Metric(Protocol):
    name: str
    def evaluate(self, golden: Golden, trace: Trace, oracle: Oracle | None) -> CheckResult: ...

class DatasetStore(Protocol):
    def load(self, **filters) -> list[Golden]: ...
    def save(self, goldens: list[Golden]) -> None: ...
```

Adopting evalkit in another project = implement `AgentRunner` (+ optionally `Oracle`), point at a
dataset dir, register any bespoke metrics. Nothing else.

## Why capabilities/scenarios are data, not enums in core

A travel bot has `flight_search`; a support bot has `refund_policy`. Core treats capability and
scenario as **strings validated against a project-supplied taxonomy** (`eval/adapters/config.py`).
Hardcoding travel enums into core would be the single easiest way to make it non-portable.

## Path to MCP (phase 3, no rewrite)

The MCP server is a *transport* over the same ports — a thin `evalkit/mcp/server.py` exposing:

| MCP tool | Backed by |
|---|---|
| `eval_list_capabilities` | DatasetStore + taxonomy |
| `eval_run_suite(suite, capability, repeat)` | `runner.run()` |
| `eval_get_report(run_id)` | `report.load()` |
| `eval_compare_baseline(report, baseline)` | `baseline.compare()` |
| `eval_propose_goldens(capability, scenario)` | golden-generation agent (writes PR, never dataset) |

Because `runner`/`baseline`/`report` are already framework-free functions returning typed
objects, the MCP layer is a serialization shell. That is the payoff of the port boundary — and
the reason MCP is deliberately **not** built in phase 1 (nothing to expose until the engine and
the report contract are stable).

## Report JSON = the stable contract

CI, baseline diffing, the failure-mining agent, and the future MCP all consume one schema
(`evalkit/report.py`, versioned `schema_version`). Change it additively.

## Consequences for the phase-1 plan

- Tasks build `evalkit/*` (portable) and `eval/adapters/*` (binding) as separate files from day one
  — no "refactor to extract it later" step, which never happens.
- A boundary test ships in wave 1, before there is anything to leak.
- The DB-as-Oracle idea (design-agentic-evolution.md) lands as an `Oracle` port impl — the most
  project-specific part of the vision, cleanly quarantined.
