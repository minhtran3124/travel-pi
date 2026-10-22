# evalkit — portable capability × scenario agent-eval engine

`evalkit/` is the **framework-free core** of the eval pipeline: goldens, ports, a metric
registry, a runner, and a Report/baseline contract. It has zero dependency on this repo, on
FastAPI, SQLAlchemy, LangGraph, or LangChain — the only hard runtime dependency is `pydantic`.
It is designed to be pulled out into its own package (or an MCP server) and adopted by a
different agent project without a rewrite.

`eval/` (the sibling directory, one level up) is the **travel-pi binding** — the only place
that is allowed to import `app.*`. If you are looking for travel-pi's own datasets, adapters,
and workflow docs, see `../eval/README.md` instead. This document is about the engine itself.

## The one rule

> **`evalkit/` must never import `app.*`, `fastapi`, `sqlalchemy`, `langgraph`, or `langchain`.**

This is not a convention, it's a test: `tests/eval/test_boundary.py` walks every `.py` file
under `evalkit/` with `ast` (no import execution) and fails loud, naming the file and the
banned import, if anyone breaks it. `evalkit/metrics/trajectory.py` imports `agentevals` and
`evalkit/metrics/judged.py` imports `deepeval` — that's fine, those are optional third-party
*libraries*, not this host app. `agentevals` itself pulls in `langchain_core` as its own
dependency; the boundary test only bans `evalkit/` modules *themselves* doing that import.

## Adopting evalkit in another project (~20 lines)

Everything project-specific enters through a `typing.Protocol` — implement these against your
own agent, register any metrics your project needs, point at a dataset directory, and call
`evalkit.cli.main()`:

```python
# your_project/eval/adapters/my_runner.py
from evalkit.ports import AgentRunner
from evalkit.types import Golden, Trace

class MyAgentRunner:
    def run(self, golden: Golden) -> Trace:
        reply, tool_calls, flow, messages = my_agent.invoke(golden.input)
        return Trace(reply=reply, tool_calls=tool_calls, flow=flow, messages=messages)

# your_project/eval/__main__.py
import sys
import evalkit.metrics  # registers the deterministic (+ trajectory/judged, if installed) metrics
from evalkit import cli
from evalkit.dataset import JsonDatasetStore
from evalkit.registry import Taxonomy

TAXONOMY = Taxonomy(
    capabilities=["refund_policy", "order_status"],   # YOUR domain vocabulary
    scenarios=["happy", "ambiguous"],
    thresholds={"refund_policy": 0.9},                # per-capability pass-rate gate
)

if __name__ == "__main__":
    sys.exit(cli.main(
        sys.argv[1:],
        dataset_store=JsonDatasetStore("eval/datasets", TAXONOMY),
        agent_runner=MyAgentRunner(),
        metrics={},               # per-capability default metric-NAME overrides, if any
        taxonomy=TAXONOMY,
    ))
```

That's it: `python -m your_project.eval --suite smoke --dry-run` lists the goldens; drop
`--dry-run` to actually run the agent and score it. `capability`/`scenario` are plain strings
validated against *your* `Taxonomy` — core never hardcodes a travel/support/whatever-domain
enum (see "Why capabilities are data", below).

## The ports (the whole contract)

Every seam a host project implements is a `typing.Protocol` in `evalkit/ports.py`:

| Port | Signature | Who implements it |
|---|---|---|
| `AgentRunner` | `run(self, golden: Golden) -> Trace` | Your project — drives your agent for one golden, captures what happened |
| `Oracle` | `lookup(self, kind: str, params: dict) -> Any`<br>`supports(self, kind: str) -> bool` | Your project, optional — recomputes ground truth from your own DB/services (DB-as-Oracle) |
| `Metric` | `name: str`<br>`evaluate(self, golden: Golden, trace: Trace, oracle: Oracle \| None) -> CheckResult` | Core ships deterministic/trajectory/judged/oracle metrics; register your own via `@register_metric` |
| `DatasetStore` | `load(self, **filters) -> list[Golden]`<br>`save(self, goldens: list[Golden]) -> None` | Core ships `JsonDatasetStore` (`evalkit/dataset.py`) — one JSON file per capability |
| `BaselineStore` | `save(self, report: Report, path: str) -> None`<br>`load(self, path: str) -> Report` | Core ships `JsonBaselineStore` (`evalkit/baseline.py`) |

Adopting evalkit = implement `AgentRunner` (+ optionally `Oracle`), supply a `Taxonomy` and a
dataset directory, register any bespoke metrics. Nothing else is required.

## Data model (`evalkit/types.py`)

**Golden** — one eval case: a capability/scenario-tagged input plus expectations.

```python
class Golden(BaseModel):
    id: str
    capability: str          # a string, validated against your Taxonomy — never a core enum
    scenario: str             # ditto
    language: str
    suite: str                 # e.g. "smoke" | "full" — your own suite vocabulary
    input: str | None = None          # exactly one of input/turns must be set
    turns: list[str] | None = None    # multi-turn: replayed sequentially on one thread
    expected_flow: str | None = None
    expected_tools: list[str] | None = None
    expected_trajectory: list[str] | None = None   # ordered tool NAMES, no args
    oracle_checks: list[dict] | None = None        # [{"kind": ..., "params": {...}}, ...]
    metrics: list[str] | None = None               # explicit metric-name override for this case
    notes: str | None = None
```

**Trace** — what the agent actually did for one golden run: `reply: str`, `tool_calls:
list[ToolCall]` (`name`, `args`, `output`), `flow: str | None`, `messages: list[dict]`
(framework-free serialization, for trajectory metrics), `meta: dict`.

**CheckResult** → **CaseResult** → **Report**: one metric's outcome (`name`, `passed`,
`score?`, `detail?`) rolls up into one golden's overall pass/fail (`CaseResult`), which rolls
up into the versioned **Report** — the stable contract every consumer (CI, baseline diff, a
future MCP server) reads:

```python
class Report(BaseModel):
    schema_version: str
    run_meta: dict[str, Any]                      # suite/capability/language filters, repeat,
                                                    # judge_available, skipped_judged_metrics, summary
    per_case: list[CaseResult]
    per_capability: dict[str, dict[str, Any]]      # {passed, total, pass_rate, threshold, meets_threshold}
```

`per_capability`'s `pass_rate` is a **binary** rate — the fraction of cases where every
applicable check passed (`CaseResult.passed`), never a mean of individual check scores. Change
the Report shape additively only (new optional keys); a rename or removal breaks every
consumer of the contract at once.

## Metrics: registered by name, resolved by the runner

Metrics register themselves at import time via `@register_metric` (`evalkit/registry.py`) so
`evalkit.runner.run_eval` can look one up by plain string name — from a golden's own
`metrics` field, or a project-supplied per-capability default — without ever importing a
concrete metric module itself. Four families ship in `evalkit/metrics/`:

- **`deterministic.py`** (pydantic only): `flow_match`, `tools_expected` / `tools_expected_exact`,
  `reply_language`, `non_empty_reply`, `tool_args_shape`. No network, no LLM.
- **`trajectory.py`** (needs the `trajectory` extra, `agentevals`): `trajectory_match` /
  `_strict` / `_unordered` — deterministic tool-call-order checking, no judge.
- **`judged.py`** (needs the `judged` extra, `deepeval`): G-Eval rubrics as **data** (a
  `dict[name, {criteria, evaluation_params, threshold}]`) — temp-0, k-repeat averaged. Swap
  rubrics by passing a different dict, never by editing the module.
- **`oracle.py`** (pydantic only, but useless without a project `Oracle`): `oracle_fact_check`
  — an injected extractor pulls a claimed value out of the reply (parsing only), and this
  module's own comparison code — never the extractor — decides agreement against
  `oracle.lookup()`. See `docs/solutions/agent/llm-parses-code-computes.md` for why the split
  matters: an LLM that both extracts *and* judges correctness can rationalize its own mistake.

A registered metric with a mutable `k` attribute is the *entire* signal the runner uses to
know "this is a judged metric" (`hasattr(metric, "k")`) — deterministic/trajectory metrics
never define one. This is how `run_eval`'s `repeat=k` and `judge_available=False` skip logic
stay agnostic to which extras are even installed.

`evalkit/metrics/__init__.py` imports each family in its own `try/except ImportError`: the
judge-free layer (`deterministic`) always registers; `trajectory`/`judged`/`oracle` degrade
gracefully (a logged warning, metrics simply absent from the registry) when their extra isn't
installed — the engine still runs, it just can't score what it wasn't given the tools for. The
package is imported in-repo, not installed standalone; extras (`agentevals`, `deepeval`) are
pinned in `apps/api/requirements-ai.txt`.

## The runner (`evalkit/runner.py`, `evalkit/cli.py`)

`run_eval(goldens, agent_runner, metrics, taxonomy, oracle=None, repeat=1,
judge_available=True, run_meta=None) -> Report` is the one function every entrypoint calls:
per golden, run the agent (a raised exception becomes a failed `agent_run` check, never a
crash and never a silently dropped case), resolve applicable metric names (golden's own
`metrics` wins; else the caller's per-capability default; else a domain-agnostic fallback),
apply each metric (`k=repeat` for judged metrics, skipped with a loud log when
`judge_available=False`), aggregate to a `Report`.

`evalkit/cli.py`'s `main(argv, *, dataset_store, agent_runner, metrics, taxonomy, oracle=None,
judge_available=True)` is a thin, framework-free argparse wrapper (`--suite smoke|full
--capability X --language vi|en --repeat k --out report.json --dry-run`) — every dependency is
injected by the caller, so this module never imports anything host-specific either. A project
wires its own bindings into a thin `__main__.py` (see the 20-line example above, or
`../eval/__main__.py` for the travel-pi wiring) and calls `cli.main()`.

## Why capabilities/scenarios are data, not enums in core

A travel bot has `flight_search`; a support bot has `refund_policy`. `Golden.capability`/
`scenario` are plain strings, validated against a project-supplied `Taxonomy`
(`evalkit/registry.py`) — never a core enum. Hardcoding travel-specific values into `evalkit/`
would be the single easiest way to make it non-portable, which is why `evalkit/dataset.py`'s
`JsonDatasetStore` takes a `Taxonomy` as a constructor argument rather than importing one.

## Path to MCP (not built yet)

The MCP server is a planned **transport**, not a rewrite — `evalkit/runner`/`baseline`/`report`
are already framework-free functions returning typed pydantic objects, so `evalkit/mcp/`
(not yet created) would only need to be a thin serialization shell:

| Planned MCP tool | Backed by |
|---|---|
| `eval_list_capabilities` | `DatasetStore` + `Taxonomy` |
| `eval_run_suite(suite, capability, repeat)` | `runner.run_eval()` |
| `eval_get_report(run_id)` | `report.load_report()` |
| `eval_compare_baseline(report, baseline)` | `baseline.compare()` |
| `eval_propose_goldens(capability, scenario)` | a future golden-generation agent — writes a PR, never the dataset directly |

This is deliberately **not** built yet: there's nothing worth exposing until the engine and
the Report contract have run for a while and proven stable (`specs/agent-eval-pipeline/
design-portability.md`). When it lands, adopting projects get an MCP surface over the exact
same ports described above with no additional integration work.
