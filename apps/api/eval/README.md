# Agent eval (`eval/`) — travel-pi workflow

The capability × scenario eval suite for the Travel Assistant agent, built on the portable
`evalkit/` engine (see `../evalkit/README.md` for the engine's own contract — port protocols,
data model, metric registry). This document is the **travel-pi-specific** half: the dataset
matrix, how to add a golden/metric/capability, how to run it, and the gotchas that are real in
this codebase today (not aspirational — everything below was read from the current code).

## Structure

```
eval/
├─ __main__.py            # wires JsonDatasetStore + LangGraphRunner + DbOracle + TAXONOMY -> evalkit.cli
├─ adapters/
│  ├─ config.py            # TAXONOMY: the 10 capabilities, 5 scenarios, per-capability thresholds
│  ├─ langgraph_runner.py  # AgentRunner: drives the compiled travel graph, captures a full Trace
│  ├─ db_oracle.py         # Oracle: recomputes flight/hotel/fx/budget truth via the real services
│  └─ extractor.py         # llm_extract: the production Extractor for oracle_fact_check
├─ datasets/*.json          # goldens — one file per capability
├─ baselines/                # committed baseline Report JSON (main.json) — created by `make eval-baseline`
└─ reports/                  # gitignored — `make eval-full`'s output, regenerated per run
```

## The capability × scenario matrix (actual counts, read from `eval/datasets/*.json`)

84 goldens total, 18 tagged `suite=smoke` / 66 `suite=full`, 44 `vi` / 40 `en`:

| capability | happy | ambiguous | multi_turn | tool_failure | adversarial | total |
|---|---|---|---|---|---|---|
| booking | 3 | 2 | 2 | 1 | 0 | 8 |
| budget | 2 | 4 | 2 | 0 | 0 | 8 |
| dates | 2 | 2 | 2 | 0 | 0 | 6 |
| errors | 2 | 2 | 2 | 1 | 1 | 8 |
| flight_search | 2 | 4 | 2 | 0 | 0 | 8 |
| hotels | 4 | 2 | 2 | 0 | 0 | 8 |
| journal | 2 | 2 | 2 | 0 | 0 | 6 |
| language | 5 | 2 | 2 | 0 | 0 | 9 |
| memory | 2 | 2 | 8 | 0 | 0 | 12 |
| routing | 6 | 3 | 2 | 0 | 0 | 11 |

`tool_failure`/`adversarial` are thin (2 and 1 cases total, both in `errors`) — the visible,
countable gaps this schema was built to surface (`specs/agent-eval-pipeline/PLAN.md` §4); they
are the backlog for a future golden-generation pass, not a bug in this README.

Every capability's threshold is `0.7` (`eval/adapters/config.py::DEFAULT_THRESHOLD`) — a
capability's aggregate pass rate below that fails `make eval-compare`/the CI gate.

## Add a golden

Append a JSON object to the right `eval/datasets/<capability>.json` file (create the file if
the capability is new — see "add a capability" below). Required fields (`evalkit.types.Golden`):

```json
{
  "id": "hotels-happy-vi-02",
  "capability": "hotels",
  "scenario": "happy",
  "language": "vi",
  "suite": "full",
  "input": "Tìm khách sạn ở Đà Lạt cuối tuần này",
  "expected_flow": "concierge",
  "expected_tools": ["search_hotels"],
  "metrics": ["flow_match", "tools_expected", "reply_language"]
}
```

- `id` must be globally unique across every file in `eval/datasets/` (checked at load time —
  `evalkit.dataset.JsonDatasetStore`, a duplicate raises loud naming both files).
- Exactly one of `input` (single-turn) or `turns: [...]` (multi-turn, replayed sequentially on
  one thread) — never both, never neither.
- `metrics` is the explicit list this golden is scored on. There is no implicit "run
  everything" — a golden that omits `metrics` falls back to its capability's default (empty for
  every capability today, see `eval/__main__.py::DEFAULT_METRICS_BY_CAPABILITY`), then to
  `evalkit.runner.DEFAULT_METRIC_NAMES` (`flow_match`, `tools_expected`, `non_empty_reply`,
  `reply_language`) if that's also empty.
- Only put a golden in `suite=smoke` if every metric it declares is keyless (deterministic or
  trajectory) — `tests/eval/test_datasets.py::test_smoke_suite_never_declares_a_judged_metric`
  enforces this; a smoke golden that opts into a G-Eval rubric would silently need a real key.
- `oracle_checks` (flight/hotel/fx/budget goldens only) — see `evalkit/metrics/oracle.py`'s
  module docstring for the `{"kind": ..., "params": {...}}` shape; `kind` must be one
  `eval/adapters/db_oracle.py::DbOracle` actually supports (`flight_offers`,
  `hotel_availability`, `fx_rate`, `trip_budget`).

## Add a metric

**Deterministic / trajectory / judged / oracle** — pick the right layer in `evalkit/metrics/`
(see `../evalkit/README.md`'s metric-family table), write a class with `name: str` and
`evaluate(golden, trace, oracle) -> CheckResult`, and `register_metric(YourMetric())` at
import time. If it's travel-pi-specific (not something another project would want), it can
live in a new file under `eval/adapters/` instead and be registered from `eval/__main__.py`.
Reference every rubric a golden can request in its `metrics` list — a name with nothing
registered raises `KeyError` at run time (`evalkit.registry.get_metric`), not a silent skip.

> **Known gap, as of this writing:** `eval/datasets/memory.json` and `eval/datasets/booking.json`
> declare `metrics: [..., "memory_recall", ...]` / `[..., "suggestion_relevance", ...]`
> respectively, but neither name is registered anywhere (`evalkit/metrics/judged.py`'s `RUBRICS`
> dict only has `response_language`, `search_vs_booking`, `no_hallucination`,
> `format_quality`). `tests/eval/test_datasets.py` treats both as judged-metric names (so they're
> correctly excluded from `suite=smoke`), but an actual `--suite full` run will raise
> `KeyError: no metric registered under 'memory_recall'` the moment it reaches one of those
> goldens. Closing this means adding two more rubrics (or deterministic checks) to
> `evalkit/metrics/judged.py::RUBRICS` (or a travel-pi-specific registration in
> `eval/__main__.py`) before `make eval-full` can run clean end to end — flagged here rather
> than silently worked around.

## Add a capability

1. Add the name to `CAPABILITIES` in `eval/adapters/config.py` (and a threshold to
   `TAXONOMY.thresholds` if it shouldn't use the `0.7` default).
2. Create `eval/datasets/<capability>.json` — a JSON list of goldens (see "add a golden").
   `JsonDatasetStore` picks up every `*.json` file in the directory automatically; no registry
   to update.
3. If the capability needs fact-checking against a computable ground truth, add a `kind` to
   `eval/adapters/db_oracle.py::DbOracle` (a new `_KINDS` entry + a `_<kind>()` method calling
   the same service/repository the agent's own tool uses — never re-derive the seed math) and
   a matching claim schema to `eval/adapters/extractor.py::_SCHEMAS`.

## Running

All commands from `apps/api/`, via the root delegating `Makefile` or directly:

```bash
make eval-smoke      # keyless: python -m eval --suite smoke — deterministic + trajectory only
make eval-full        # judged: python -m eval --suite full --repeat 3 --out eval/reports/latest.json
make eval-baseline    # cp eval/reports/latest.json -> eval/baselines/main.json (commit this)
make eval-compare     # diff eval/reports/latest.json against eval/baselines/main.json; exit 1 on regression
```

`--dry-run` (e.g. `../../.venv/bin/python -m eval --suite smoke --dry-run`) lists the selected
goldens and their resolved metric names without invoking the agent at all — the fastest way to
check a new golden lands where you expect.

**Local:** point `DATABASE_URL` (in `.env` or the shell) at a reachable, already-seeded DB —
see the gotchas below, this is not optional. **Docker:** `docker compose up -d` from
`apps/api/`, then `docker compose exec api sh` and run the same `make eval-smoke`/`eval-full`
from inside the container, against the compose Postgres (already migrated + seeded by the
app's own lifespan on container start).

## Gotchas (real, read from the code — not aspirational)

- **The eval harness bypasses `AgentConfigCache` and needs a reachable model key.**
  `LangGraphRunner` (`eval/adapters/langgraph_runner.py`) calls `app.agents.graph.build_graph`
  directly, never through a FastAPI request — so the request-scoped `AgentConfigCache` that
  normally resolves each agent's configured model is never populated. Every node falls back to
  `get_agent_llm`'s env-configured model (`gpt-5`/`gpt-5-mini` by default) and needs a real
  provider key *at invocation time*, or you get a 403 the moment the graph actually calls the
  LLM. Tests always inject `FakeLLM` via `LangGraphRunner(llm=..., fast_llm=...)` to stay
  network-free; a real `make eval-smoke`/`eval-full` run needs a working `OPENAI_API_KEY` (or
  whatever `LLM_PROVIDER` is configured) regardless of whether any metric on the run is judged.

- **The DB must already exist, with its schema created and seeded, before you run eval at
  all.** `LangGraphRunner`/`build_eval_graph` only sets up an in-memory checkpointer/store
  (`MemorySaver`, `InMemoryStore`) — it never runs `Base.metadata.create_all` or `seed_all`
  (those are FastAPI-lifespan-only, `app/core/lifespan.py`). Tools resolve their own DB session
  via `session_scope()` (`app/tools/_base.py`), not through any request-scoped dependency the
  harness could intercept. Concretely: `search_flights` needs a seeded `Airline` table
  (`FlightService.generate_flights` picks one via `rng.choice`, an empty table raises
  `IndexError`); `search_hotels`/`browse_hotels` need seeded `Hotel` rows. On a fresh checkout,
  run `make migrate && make seed` (or just `make dev` once, which seeds on startup) against
  the same `DATABASE_URL` before `make eval-smoke`/`eval-full` — otherwise you get "no such
  table" or an empty/wrong result instead of a real check.

- **Judged metrics need a real judge key; the smoke suite is designed to never need one.**
  `eval/__main__.py::_judge_available()` treats `OPENAI_API_KEY` unset or one of
  `{"", "test", "changeme", "placeholder"}` (case-insensitive — this repo's own `.env` ships a
  fake `OPENAI_API_KEY=test`) as "no judge" and skips every metric exposing a `k` attribute
  (`evalkit.runner.run_eval`'s `judge_available=False` path), logging which ones were skipped
  into the report's `run_meta["skipped_judged_metrics"]` rather than silently omitting them.
  `oracle_fact_check`'s real `llm_extract` extractor (`eval/adapters/extractor.py`) is wired in
  the same way: only when a real key is present, otherwise the no-op default stays registered
  and reports `not_applicable` for every oracle check.

- **`--dry-run` still evaluates judge-availability (but never calls the extractor).**
  `eval/__main__.py::main()` decides whether to wire the real `llm_extract` *before* `cli.main`
  even parses `--dry-run` — so a dry run with a real key present logs `oracle_fact_check: wired
  with llm_extract (judge key present)` even though nothing is ever invoked (dry-run returns
  before the agent or any metric runs). Harmless, but don't read that log line as "a real
  extraction call happened."

- **Only `test_extractor` (`eval/adapters/extractor.py`), `test_db_oracle`, and the runner/CLI
  tests exercise the oracle path offline** — they inject a hand-written stub extractor, never a
  real LLM call, so `tests/eval` stays network-free even though production wiring uses a real
  one.

## Baselines and the regression gate

`make eval-baseline` copies the latest `eval/reports/latest.json` (gitignored — regenerated
per run) to `eval/baselines/main.json`, which **is** committed — it's the thing regressions are
measured against. `make eval-compare` (`evalkit.baseline.compare`) diffs the two reports and
fails (non-zero exit) on either: a capability's pass rate dropping more than the tolerance
(default `0.05`) below its baseline, or a specific case flipping pass→fail inside a capability
whose rate also dropped by any amount (catches a regression an unrelated same-run fix would
otherwise cancel out in the aggregate). A capability with no entry in the baseline yet (a
newly added one) is reported but never fails the gate — there's nothing to regress against on
its first run.

There is no CI workflow wired up for this suite yet (`.github/workflows/ci.yml` only runs
`pytest tests/`) — a keyless PR gate + a nightly judged run with baseline comparison is a
separate, not-yet-landed task (`specs/agent-eval-pipeline/PLAN.md` task 4.2).
