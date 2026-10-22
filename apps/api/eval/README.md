# Agent eval (`eval/`) — travel-pi workflow

The capability × scenario eval suite for the Travel Assistant agent, built on the portable
`evalkit/` engine (see `../evalkit/README.md` for the engine's own contract — port protocols,
data model, metric registry). This document is the **travel-pi-specific** half: the dataset
matrix, how to add a golden/metric/capability, how to run it, and the gotchas that are real in
this codebase today (not aspirational — everything below was read from the current code).

## Quick start (local)

From `apps/api/`, with the root `.venv` installed and Docker running:

```bash
docker compose up -d db            # eval reads agent_config + seed data from the dev Postgres
cp .env.example .env               # once; then set OPENAI_API_KEY (real) and EVAL_EXTRACTOR_MODEL=gpt-5.4-mini

OPENAI_API_KEY= ../../.venv/bin/python -m eval --suite smoke --dry-run   # list goldens, no key, no agent
make eval-smoke                    # 20 cases, real agent, no judge — a couple of minutes
make eval-full                     # 103 cases, judge k=3 — ~10–15 min, paid
make eval-compare                  # diff reports/latest.json vs baselines/main.json; exit 1 on regression
make eval-check                    # eval-full + eval-compare: run this before merging prompt/agent/tool changes
```

Open `eval/reports/latest.html` to see every case and check. `make eval-full` exits 2 while any
capability sits below its 70% threshold — the report is still written; only `eval-compare` is
the gate. To adopt a run as the new baseline: `make eval-baseline`, then commit
`eval/baselines/main.json`. Narrow a run with `--capability booking` or `--language vi`
(`../../.venv/bin/python -m eval --suite full --capability booking --out eval/reports/booking.json`).

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

123 goldens total, 20 tagged `suite=smoke` / 103 `suite=full`, 59 `vi` / 64 `en`:

| capability | happy | ambiguous | multi_turn | tool_failure | adversarial | total |
|---|---|---|---|---|---|---|
| booking | 3 | 2 | 2 | 1 | 0 | 8 |
| budget | 2 | 4 | 2 | 0 | 0 | 8 |
| dates | 2 | 5 | 2 | 0 | 0 | 9 |
| errors | 2 | 2 | 2 | 1 | 1 | 8 |
| flight_search | 2 | 4 | 2 | 0 | 0 | 8 |
| hotels | 4 | 2 | 2 | 0 | 0 | 8 |
| journal | 3 | 2 | 2 | 0 | 0 | 7 |
| language | 5 | 2 | 2 | 0 | 0 | 9 |
| memory | 3 | 2 | 8 | 0 | 4 | 17 |
| routing | 20 | 3 | 2 | 0 | 0 | 25 |
| suggestions | 10 | 0 | 0 | 0 | 0 | 10 |
| web_search | 3 | 3 | 0 | 0 | 0 | 6 |

`tool_failure`/`adversarial` are thin (2 cases in `booking` + `errors`, and 5 in `errors` + `memory`) — the visible,
countable gaps this schema was built to surface (`specs/agent-eval-pipeline/PLAN.md` §4); they
are the backlog for a future golden-generation pass, not a bug in this README.

Every capability's threshold is `0.7` (`eval/adapters/config.py::DEFAULT_THRESHOLD`) — a
capability's aggregate pass rate below that fails `make eval-compare`/the CI gate.

The `web_search` goldens (`eval/datasets/web_search.json`) need `WEB_SEARCH_ENABLED=true` plus
both provider keys (`TAVILY_API_KEY`, `SERPAPI_API_KEY`) and run under `make eval-check`; with
the flag off the live tools are unbound and the must-call goldens fail.

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
- `hitl` (`"approve"` | `"reject"`, optional) — when the graph stops at the `plan` node's
  `plan_approval` interrupt, the runner resumes the same thread with
  `Command(resume={"approved": hitl == "approve"})`, exactly like the chat API
  (`app/routers/agent.py`) does. Without `hitl` the trace keeps the empty reply the interrupt
  left behind, so `non_empty_reply` reports the interrupt honestly instead of masking it.
  Setting `hitl` on a golden that never interrupts is harmless — there's nothing to resume.
  Changing `hitl` on an existing golden changes what gets graded, so it requires a baseline
  refresh (`make eval-baseline`).

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
make eval-smoke       # deterministic + trajectory only; writes reports/latest.{json,html}
make eval-full        # judged: --suite full --repeat 3; writes reports/latest.{json,html}
make eval-html        # re-render latest.json as HTML — no agent, no LLM spend
make eval-baseline    # cp eval/reports/latest.json -> eval/baselines/main.json (commit this)
make eval-compare     # diff eval/reports/latest.json against eval/baselines/main.json; exit 1 on regression
```

`latest.html` is the one to open when something fails: totals and pass rate, each capability
against its threshold, and every case expandable to its per-check verdict and reason, failures
first. It is self-contained (no CDN/asset), so it also works as a CI artifact.

`--dry-run` (e.g. `../../.venv/bin/python -m eval --suite smoke --dry-run`) lists the selected
goldens and their resolved metric names without invoking the agent at all — the fastest way to
check a new golden lands where you expect.

**Local:** point `DATABASE_URL` (in `.env` or the shell) at a reachable, already-seeded DB —
see the gotchas below, this is not optional. **Docker:** `docker compose up -d` from
`apps/api/`, then `docker compose exec api sh` and run the same `make eval-smoke`/`eval-full`
from inside the container, against the compose Postgres (already migrated + seeded by the
app's own lifespan on container start).

## Gotchas (real, read from the code — not aspirational)

- **A real run grades the DB-configured agent, not the env-default one.** `eval/__main__.py`
  loads `AgentConfigCache` (`configure` + `reload_from_db`, mirroring `app/core/lifespan.py`)
  and builds the run's `AgentContext` the way `app/routers/agent.py` does, so nodes resolve the
  same per-agent models the API serves and reflection follows its DB toggle. Before that wiring
  existed, every node fell back to `get_agent_llm`'s env default (`gpt-5`/`gpt-5-mini`) — a 403
  on this repo's key, and otherwise a score for an agent nobody ships. Consequence: **the DB
  must be reachable and its `agent_config` rows populated** (`make seed`) for a real run; tests
  stay network-free by injecting `FakeLLM` via `LangGraphRunner(llm=..., fast_llm=...)`.

- **The oracle extractor has its OWN model knob, `EVAL_EXTRACTOR_MODEL`.** `llm_extract`
  (`eval/adapters/extractor.py`) is eval infrastructure, not a graph node, so it is deliberately
  NOT in the product's `agent_config` table/dashboard — set `EVAL_EXTRACTOR_MODEL` to a model
  your provider key can actually call (unset falls back to the env `FAST_LLM_MODEL`, which on
  this repo's key is a 403). If extraction cannot run it raises `ExtractionError` and the CLI
  aborts with `EVAL MISCONFIGURED` (exit 2), rather than reporting "extractor found no claimed
  value" and failing goldens the agent got right — a broken eval must never charge its own
  misconfiguration to the agent.

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
its first run. If `eval-compare` can't find a baseline file, it fails naming the fix directly:
run `make eval-baseline` first.

To refresh the baseline after an intentional agent/prompt/tool change: run `make eval-full`,
inspect `eval/reports/latest.html` to confirm the new numbers are trustworthy (not a silent
regression you're about to bless), then `make eval-baseline` and commit the updated
`eval/baselines/main.json` with the reason for the change in the commit message.

## `expected_tasks` and the `tasks_expected` metric

`Golden.expected_tasks` (`evalkit/types.py`) is an optional set of sub-agent names the
supervisor is expected to fan out to for that golden. The `tasks_expected` metric
(`evalkit/metrics/deterministic.py::TasksExpectedMetric`) compares that set against
`Trace.meta["tasks"]` — the sub-agents that actually ran — by set equality; a golden without
`expected_tasks` reports `not_applicable` and always passes. Multi-intent turns (the supervisor
fanning out to more than one sub-agent in one turn) end with `current_flow == "synthesize"`,
not the fanned-out sub-agent's own flow name, so `flow_match` does not apply to them — use
`tasks_expected` instead for those goldens.

`Trace.meta` (populated by `eval/adapters/langgraph_runner.py`) also carries `suggestions`: the
follow-up suggestion keys the reply offered (`app/agents/suggestions.py::suggestions_for_flow`).
The runner feeds these into the judge's retrieval context as one `"suggestion: <key>"` line per
item, which is what the `suggestion_relevance` rubric grades against. The `suggestions`
capability (`eval/datasets/suggestions.json`, 10 goldens) exercises this end to end.

## `meta.interrupts` and the `hitl` opt-in

`Trace.meta["interrupts"]` (`eval/adapters/langgraph_runner.py`) is always recorded — regardless
of `hitl` — as a list of `{"type", "draft", "turn"}` entries, one per turn that stopped at a `plan_approval` interrupt (the runner records the first pending interrupt of a turn and resumes at most once per turn)
the graph raised during the run (`turn` is the 0-based index of the turn that hit it). This is
what makes an interrupted golden's outcome legible in the report even when nothing was resumed.

A multi-turn golden whose earlier turn interrupts must set `hitl`: without it the next turn's plain message lands on a thread parked at the interrupt, LangGraph starts a fresh step and abandons the pending approval, and the trace would grade a post-abandon conversation.

Booking goldens that need the booking tools to actually run opt in with `hitl: "approve"`
(`booking-happy-*`, `booking-multi_turn-*`, `booking-tool_failure-*`, `errors-tool_failure-*`,
`dates-multi_turn-*`, `routing-ambiguous-en-01`, `suggestions-happy-*-04`). `booking-ambiguous-*`
and `errors-ambiguous-en-01` deliberately do **not** set `hitl`: their pass condition is a
clarifying reply, not an approved booking — resuming past the interrupt would grade the wrong
behaviour (see `specs/gh-153-eval-hitl-auto-approve/design.md`).

## Trip-research keyed smoke (`research_smoke.py`) — NOT in CI

`eval/research_smoke.py` is a standalone smoke for the trip-research deep agent
(`specs/trip-research-deep-agent`, design §9) — separate from the capability × scenario
suite above, and **never run on CI**. It seeds one deterministic trip
(`research-smoke-trip`, owner `research-smoke-user`) and drives one real research turn
against it.

```bash
# Keyless, CI-safe: lists the seeded trip and exits 0 — no key, no agent, no LLM spend.
DATABASE_URL=sqlite:///:memory: OPENAI_API_KEY= ../../.venv/bin/python -m eval.research_smoke --dry-run
make research-smoke ARGS='--dry-run'

# Real run: one research turn, then asserts dossier files exist, validate_proposal is
# valid, and the run's recorded cost is at or below --max-usd. Writes a report to
# eval/reports/research-smoke.json. Needs a real OPENAI_API_KEY and a seeded, reachable
# DB (Postgres via `docker compose up -d db` + `make seed`) so the agent's tools and
# validate_proposal resolve real place/flight/hotel ids.
make seed
OPENAI_API_KEY=sk-... make research-smoke ARGS='--max-usd 1.00'
```

Flags: `--dry-run` (keyless listing), `--max-usd` (cost ceiling, default `1.0`),
`--timeout` (hard bound in seconds; defaults to `settings.research_timeout_s`, so the run
can never hang), `--instruction` (override the default research prompt). The dry-run is the
gate the plan's SC-25 checks; the real run is a paid, manual check the branch owner runs
before shipping — **one live agent turn plus its grader, on the order of a few cents to a
dollar** depending on model and how many revision rounds the grader asks for (bounded by
`--max-usd`).

## CI: the local gate ritual

`.github/workflows/eval.yml` runs exactly one job, `eval-smoke` — keyless, no DB, no network:
`pytest tests/eval` (boundary + dataset + deterministic/trajectory metric tests, all offline)
followed by `python -m eval --suite smoke --dry-run` (dataset load + CLI wiring sanity, zero
agent invocation). It proves the pipeline is wired correctly; it does not prove the real agent
passes any golden.

The judged suite — G-Eval rubrics plus the DB-Oracle fact-check, real judge key required —
**never runs on CI** (decision E002, `specs/review-b7-eval-baseline-ci/ESCALATIONS.md`): no
`OPENAI_API_KEY` secret is provisioned, and no other workflow trigger runs it. The regression gate
is **local and manual**: run `make eval-check` (`eval-full` then `eval-compare`) yourself before
merging any change that touches `app/agents/`, `app/prompts/`, `app/tools/`, `eval/`, or
`evalkit/` — the same paths `eval.yml`'s `pull_request` trigger watches. One `eval-check` run is
103 agent turns plus their judge calls at k=3 (the full suite; the exact `--suite` filter in
`JsonDatasetStore.load` excludes the 20 smoke goldens, which are the keyless PR set, not part of
the baseline). Revisit the cadence decision if/when Langfuse/LangSmith online eval is chosen —
see E002 for the alternatives that were considered and declined.
