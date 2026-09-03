# agent-turn-metrics — Summary

Lane: high-risk
Confidence: high
Reason: two block-mode hard gates fire — `data-loss/migration` (new `agent_runs` table + Alembic revision) and `public-contract` (new fields on the client-visible `done` SSE event and a new dashboard page) — plus flags data model, existing behavior (`streaming=True` chat models start requesting usage; the SSE/`ainvoke` paths gain a callback), multi-domain (clients/agents/streaming/db/routers/dashboard/tests) and weak proof (must prove token counts are non-zero on the streaming path with FakeLLM and that per-node latency sums plausibly). The where-to-record fork (DB vs log-only vs Langfuse-only) and the prompt-cache scope were resolved by the human at intake, so confidence is high.
Flags: data model, public contract, existing behavior, multi-domain, weak proof
Affects: apps/api/app/clients/llm.py (stream_usage), app/agents/metrics.py (new in-house usage/latency callback; observability.py untouched), app/routers/agent.py (`_config` callbacks + run row), app/streaming/{events,mapper,persistence}.py (`done` payload), app/db/models/agent_run.py + alembic (new table), app/repositories/agent_run.py, app/routers/dashboard*.py + templates (metrics page), tests/{agents,api/agent,streaming}
Input-type: change request
Route: high-risk — design.md (reviewed), research-brief.md (Deep, 4 design corrections applied), PLAN.md (reviewed, contract check passes) all in this dir → in-place branch `feat/agent-turn-metrics` off main → subagent-driven-development
Escalate: no (fork resolved at intake: record in DB table `agent_runs`; prompt-cache/prefix stabilisation deferred to its own spec)

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> run /feature-intake cho "Chi phí & độ trễ mỗi turn không được đo" theo artifact
> https://claude.ai/code/artifact/e31c4a78-8e78-4b47-9ec7-4e9c5d0d2ac1?via=auto_preview
>
> (deep review 2026-09-02 §3.B item 6, docs/reviews/2026-09-02-deep-review.md) **Chi phí & độ trễ
> mỗi turn không được đo.** Turn đơn tối thiểu = supervisor + assistant + reflection + extraction
> nền = 4 LLM call (+1 mỗi vòng tool, +summarize, +N dịch panel). Multi-intent = 2 vòng sub-agent +
> synthesize + reflection. Prefix system prompt ~3.3k token (communication_style 1,345 từ + planner
> 1,193 từ), không prompt caching. `grep usage_metadata|token_usage|cost` trong
> agents/routers/streaming → 0. → Ghi usage_metadata + latency per node vào Langfuse/DB trước; ổn
> định prefix để hit cache (OpenAI tự động, Anthropic `cache_control`); cân nhắc gộp supervisor +
> slot extraction với sub-agent đầu cho intent đơn.
>
> (human, intake fork 1 — nơi ghi) "Bảng agent_runs trong DB": callback handler nội bộ gom
> usage_metadata + latency per node cho cả /agent/chat và /agent/stream; ghi 1 row/turn vào bảng
> mới `agent_runs` (tương thích design user-feedback-v1); cost tính từ bảng giá tĩnh; thêm
> tokens/latency vào `done` event + trang dashboard.
>
> (human, intake fork 2 — prompt cache) "Không, spec riêng sau khi có số đo": spec này chỉ đo;
> ổn định prefix / cache-hit là spec riêng sau khi `cached_tokens` đã có trong usage_metadata.

## What changed

Added per-turn token/cost/latency instrumentation across three waves:

- **Wave 1 (leaf units):** `stream_usage=True` for the OpenAI SDK profile + FakeLLM emitting
  `usage_metadata` (so no OpenAI call is usage-less and the offline suite exercises the path);
  `app/agents/metrics.py` `TurnMetricsHandler` (per-model token aggregation, LLM call/error
  counts, per-node wall-clock deduped on `langgraph_checkpoint_ns`, thread-safe, never raises);
  `app/core/pricing.py` static price table (12 catalogue models verified 2026-09-03) +
  `estimate_cost` (None when any model is unpriced); the `agent_runs` table + additive Alembic
  revision `e3b7c5d9a1f4` + `AgentRunRepository`; `TurnUsage` on `ChatResponse` and a `usage`
  key on the `done` SSE event (additive; no FE change).
- **Wave 2 (consumers):** `record_agent_run` stream pass-through closing the row with the
  status derived from interrupt/error events (failed on cancel), and `done.usage` filled in the
  mapper; background memory-extraction metrics into `background_*` columns (recorded after the
  memory writes, own isolated try); the read-only `/dashboard/agent-runs` page behind the HTTP
  Basic guard (404 in prod) with 24h/7d totals and p50/p95 latency.
- **Wave 3 (wiring + docs):** `/agent/chat` and `/agent/stream` mint a `run_id`, attach the
  handler through the graph config, start the row and finish it with the turn's status/cost/
  latency; WORKFLOW.md + apps/api/README.md document it; no new env var.

Ten tasks, each with a per-task spec+quality review (all pass, zero Critical/Important). Two
review rounds produced fixes: a task-2.2 Minor (`1a6fad7`, metrics recording moved after the
memory writes) and the final correctness round (`1a494e9`) which closed four metric-accuracy
defects — a failed stream turn persisted NULL latency/cost and so dropped out of the dashboard
rollups; `estimate_cost({})` reported a confident $0.0000 instead of unknown; the
checkpoint-namespace dedupe swallowed a node retry's timing; and the mapper's metrics block was
unguarded inside the stream's own try.

### Intake findings (corrected premises)

The review's "no instrumentation" is half right. What actually exists and what is missing:

- **Langfuse tracing already exists** (`app/agents/observability.py`, specs/travel-agent Task
  7.1): `callbacks()` + `trace_metadata()` are wired into `_config` in `app/routers/agent.py`
  for both `/agent/chat` and `/agent/stream`. It is opt-in (`langfuse_enabled=False`) and needs an
  external account, so nothing in-repo records tokens.
- **No OpenAI call returns `usage_metadata` today, even with Langfuse on.** `_build_chat_model`
  passes `streaming=True` and langchain-openai 0.3.34 defaults `stream_usage=False`; with
  `streaming=True` even `invoke()` goes through `_stream` (`generate_from_stream`), so every
  AIMessage from every node is usage-less. Fixing this (`stream_usage=True`) is the prerequisite
  for any option and is a one-line change in `app/clients/llm.py`.
- **Latency:** only HTTP-level per-request timing exists (`app/core/middleware.py`
  `_log_requests`); nothing per node / per LLM call.
- **Storage:** `messages` has `tool_calls` JSON only; there is no run/turn table. The untracked
  Codex design `specs/user-feedback-v1/DESIGN.md` §3.1 already proposes an `agent_runs` table
  (`id` minted before graph invocation, `user_id`, `conversation_id`, status lifecycle) — this spec
  creates that table with the metrics columns so feedback-v1 can attach `agent_run_id` later
  instead of inventing a second table.
- **Eval:** `apps/api/eval/` records neither latency nor tokens; a per-turn metrics row is the
  missing input for the "reflection by numbers" and "cost per tier" follow-ups in the review.

### Scope

In:
- `stream_usage=True` for the OpenAI profile (Anthropic/Google already stream usage).
- An in-house LangChain callback handler (`on_chat_model_start/end`, `on_chain_start/end` for
  graph nodes) accumulating per-call `usage_metadata` (input/output/total, `cache_read` if
  present), model name, per-node wall-clock, plus turn-level wall-clock and LLM-call count.
  Registered next to the Langfuse handler in `callbacks()`; works identically for `ainvoke` and
  `astream` (the mapper does not need to parse token chunks).
- `agent_runs` table + Alembic revision (additive): id, conversation_id, user_id, thread_id,
  trip_id, status, started_at, finished_at, latency_ms, llm_calls, input_tokens, output_tokens,
  cached_tokens, cost_usd (nullable), per-node breakdown JSON, model set JSON.
- Static USD-per-1M-token price table (config/py dict, unknown model → `cost_usd=NULL`).
- `done` SSE event + `ChatResponse` gain a `usage` object (tokens, cost, latency_ms); FE untouched
  beyond tolerating the extra field.
- Dashboard page listing recent runs with totals (reuses the HTTP Basic guard from #129).
- Tests: FakeLLM emits `usage_metadata`; handler unit tests; stream/ainvoke integration tests
  assert non-zero tokens and a persisted row; model/migration tests updated.

Out (deferred, own specs): prompt-prefix stabilisation / cache-hit measurement; merging supervisor
+ slot extraction; feedback-v1 attachment; Langfuse cost dashboards; OTel GenAI semconv.

### Rationale

Every downstream decision the review recommends (reflection keep/replace, model-per-tier
benchmark, prompt caching, free-tier limits) needs a queryable per-turn cost/latency baseline
that the eval harness and dashboard can read offline; a log line or an external SaaS trace
cannot feed those. The callback route is chosen over parsing the SSE token stream because it
covers `/agent/chat` (non-streaming) and background sub-graphs with one code path and is how
the existing Langfuse handler already attaches.

### Alternatives considered

- Structured log + `done` event only (no table, normal lane): rejected at intake — no aggregate
  queries, no baseline for eval or per-tier cost.
- Enable Langfuse only (tiny lane): rejected at intake — external account, data outside the
  repo, still needs the `stream_usage` fix.
- JSON `usage` column on `messages` instead of a new table: rejected — a turn is not one message
  (multi-intent, tool turns, revisions), and feedback-v1 already wants a run entity.

### Deviations

- Rule 1 (impl 2.1): `record_agent_run`/mapper use `time.monotonic()` (brief said `perf_counter`)
  to match `TurnMetricsHandler.close()`; mixing clocks would corrupt `latency_ms`.
- Rule 2 (impl 1.1): `response_metadata` merged (`{**existing, ...}`) rather than reassigned.
- Rule 3 (controller): task-2.2 Minor fixed in `1a6fad7` — metrics recording moved after the
  memory writes into its own try so a metrics-DB failure cannot skip memory persistence.

Carry-over Minor findings (non-blocking, recorded for future tidy):
- 1.2 `metrics.py`: `_llm_starts` per-call start recorded but per-call latency never surfaced
  (only turn-level `latency_ms` exposed) — harmless dead in-flight state.
- Anthropic `cache_creation` (cache-write) tokens are not priced and Gemini 2.5 Pro uses its
  <=200k tier — both documented in `app/core/pricing.py`; revisit when prompt caching lands.
- 1.4 repo: `totals()` compares `created_at >= since.isoformat()` lexically (correct while both
  are tz-aware ISO); `list_recent` newest-first relies on distinct-microsecond `created_at`.
- 2.3 `agent_runs.html`: dead `or run.created_at` fallback; empty-window totals cost renders
  `$0.0000` (sum, never None). Cosmetic.
- 3.1 `agent.py`: imports the private `_utc_now_iso` from `app.db.base` (mirrors `rate_limit.py`).

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| llm stream_usage + FakeLLM usage | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/sc1.db ../../.venv/bin/python -m pytest tests/clients/test_llm_stream_usage.py -q` | 0 | openai-only guard; FakeLLM emits usage | SC-1 |
| TurnMetricsHandler | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/sc2.db ../../.venv/bin/python -m pytest tests/agents/test_turn_metrics.py -q` | 0 | aggregation, error count, ns dedupe, swallow | SC-2 |
| pricing formula | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/sc3.db ../../.venv/bin/python -m pytest tests/core/test_pricing.py -q` | 0 | cost=None on unpriced; snapshot normalise | SC-3 |
| agent_runs model+migration+repo | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/sc4.db ../../.venv/bin/python -m pytest tests/test_db_models.py tests/db/test_agent_runs_migration.py tests/repositories/test_agent_run_repo.py -q` | 0 | column set + up/downgrade round trip | SC-4 |
| /agent/chat records a run | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/sc5.db ../../.venv/bin/python -m pytest tests/api/agent/test_agent_runs.py -q` | 0 | usage on reply; completed/interrupted/failed rows | SC-5 |
| stream done.usage + recorder | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/sc6.db ../../.venv/bin/python -m pytest tests/streaming/test_record_agent_run.py tests/api/agent/test_stream_events.py -q` | 0 | status from events; event order unchanged | SC-6 |
| background extraction metrics | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/sc7.db ../../.venv/bin/python -m pytest tests/memory/test_extraction_metrics.py -q` | 0 | background_* set; turn totals untouched | SC-7 |
| dashboard page + guard | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/sc8.db ../../.venv/bin/python -m pytest tests/api/agent_config/test_agent_runs_dashboard.py -q` | 0 | 200 in dev, 404 in prod | SC-8 |
| failed turn keeps latency/cost | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/fx1.db ../../.venv/bin/python -m pytest tests/streaming/test_record_agent_run.py -q` | 0 | crashed stream row has non-null latency; explicit close not overwritten | SC-6 |
| node retry timed, nested still deduped | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/fx2.db ../../.venv/bin/python -m pytest tests/agents/test_turn_metrics.py -q` | 0 | same-ns retry counts twice; nested run ignored | SC-2 |
| unknown cost is None, not zero | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/fx3.db ../../.venv/bin/python -m pytest tests/core/test_pricing.py -q` | 0 | empty by_model -> None | SC-3 |

### Not auto-verified

- Real-provider token/cost accuracy (live OpenAI/Anthropic/Gemini usage_metadata → cost) — reached
  provenance (price table verified against provider pages 2026-09-03; formula unit-tested with a
  fake price); not re-run against a live provider (offline suite uses FakeLLM's fixed usage).
- Postgres path for the migration and the dashboard — reached traceability (SQLite round trip +
  model/migration column-set agreement verified); the Postgres run happens in CI, not re-run here.
- Per-turn wall-clock realism — reached traceability (monotonic delta, one clock); not benchmarked.

### Rollback

- Revert the branch: `git revert e84ec35..569ed7f` (code) plus the earlier feature commits, or
  drop the branch before merge. The one destructive-capable step is the schema: after deploy,
  `cd apps/api && ../../.venv/bin/alembic downgrade c7f1a9d4e6b2` drops the additive `agent_runs`
  table (no other table is touched; no data in existing tables is altered).

### Harness-Delta

- none
