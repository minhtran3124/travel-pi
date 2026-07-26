# gh-112 eval baseline — reflection ON

Baseline for #112 (remove the reflection node), captured **before** any removal work.

## Run context

| Field | Value |
|---|---|
| Commit | `42ab13c` (branch `fix/gh-109-clarification-restream`) |
| Reflection | **ON** — harness passes `AgentContext()`: `allow_reflection=True`, `max_revisions=1` |
| DB | `postgresql+psycopg://travel:travel@127.0.0.1:5433/travel` (container `api-db-1`) |
| Model, every node | `gpt-5.4-mini` (from DB `agent_config` after `reload_from_db`) |
| Env defaults (NOT used) | `llm_model=gpt-5`, `fast_llm_model=gpt-5-mini` |
| Judge | `gpt-4o-mini`, `strict=False`, `async_mode=True`, threshold **0.70** |
| Datasets | intent(6) · language(5) · tools(4) · format(4) · memory(8) · suggestions(10) = 37 cases |
| Scored | 34 cases — 3 skipped (empty reply: HITL plan-approval interrupt) |
| Exit code | 0 |

## Results

| Metric | Average score | Pass rate | N |
|---|---|---|---|
| Response Language [GEval] | 1.00 | 100.00% | 10 |
| Search vs Booking Intent [GEval] | 0.89 | 80.00% | 5 |
| Format Quality [GEval] | 0.89 | 100.00% | 4 |
| Memory Recall [GEval] | 0.84 | 87.50% | 8 |
| Suggestion Relevance [GEval] | 0.64 | 50.00% | 8 |
| Tool Correctness | 1.00 | 100.00% | 4 |
| suggestion_relevance (deterministic) | — | 8/8 (100%) | 8 |
| no_hallucination [GEval] | skipped — no case declares this rubric | — | 0 |

### Failing cases (compare like-for-like after removal)

| Metric | Failing case input |
|---|---|
| Search vs Booking Intent | `Cho tôi xem các chuyến bay từ TP.HCM đi Tokyo` |
| Memory Recall | `Turn 1: Ngân sách của tôi khoảng 20 triệu cho…` (multi-turn) |
| Suggestion Relevance | `What's the weather like in Bangkok this weekend?` |
| Suggestion Relevance | `Add a note: I want to visit the beach on day 2` |
| Suggestion Relevance | `Chuyến đi Phú Quốc của mình còn bao nhiêu ngân…` |
| Suggestion Relevance | `Break down my Tokyo trip expenses so far` |

### Skipped cases (empty reply — HITL interrupt, expected)

- `Đặt phòng khách sạn đó giúp tôi`
- `Đặt khách sạn ở Hội An cho tôi`
- `Book the cheapest flight from SGN to Da Nang next Friday`

## Reading the numbers

- **Suggestion Relevance is the noise floor, not a signal.** Its GEval half scores 0.64 / 50% while
  the deterministic half is 8/8 — the same replies pass the mechanical check (non-empty +
  catalog-valid keys) and fail the judge. Pre-existing eval artifact, unrelated to reflection; do
  not read a post-removal delta on this rubric as a quality change.
- **`no_hallucination` produces nothing** — no dataset case declares it, so it contributes zero
  coverage either way.
- The rubrics with real signal for this change are **Response Language**, **Search vs Booking
  Intent**, **Format Quality**, **Memory Recall**, and **Tool Correctness**.

## Reproduce

From `apps/api/`:

```bash
export OPENAI_API_KEY="$(grep '^OPENAI_API_KEY=' .env | cut -d= -f2-)"
export PYTHONPATH="$PWD"
docker compose up -d db
../../.venv/bin/python <runner>     # see "Runner" below
```

Gotchas that make the difference between this run and a meaningless one:

1. **Do NOT `set -a; . .env`.** Exporting the whole file breaks `get_settings()` —
   `CORS_ORIGINS` is shell-literal, not JSON, and pydantic-settings raises
   `SettingsError: error parsing value for field "cors_origins"`. Export only
   `OPENAI_API_KEY`; pydantic reads `.env` itself for everything else.
2. **`PYTHONPATH` must include `apps/api`** when the runner lives outside the package dir.
3. **The eval harness never populates `AgentConfigCache`.** Without
   `AgentConfigCache.configure(...)` + `reload_from_db(...)` before `build_eval_graph()`, every node
   falls back to env `gpt-5` / `gpt-5-mini` instead of the DB's `gpt-5.4-mini`.
4. `eval/` invokes the graph directly, so DB `agent_config.enabled` has **no effect** — reflection
   is controlled by the `AgentContext` the harness passes, not by the DB. Note that `reflection` is
   `enabled=False` on this dev DB, yet still ran here because the harness hardcodes
   `AgentContext()`.

### Runner

```python
from app.core.agent_config_cache import AgentConfigCache, reload_from_db
from app.core.config import get_settings
from app.db.engine import get_session_factory
from eval.run_deepeval import main

settings = get_settings()
factory = get_session_factory(settings.database_url)
AgentConfigCache.configure(factory, settings.agent_config_poll_interval_seconds)
reload_from_db(factory)
raise SystemExit(main())
```

For the post-removal run, re-run this unchanged on the branch that removes the node.
