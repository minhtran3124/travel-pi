---
slug: agent-turn-metrics
status: shipped
owner: Minh Tran
created: 2026-09-03
---

# agent-turn-metrics — Per-turn token / cost / latency instrumentation

**Base:** `main` (`1aee549`). **Branch:** `feat/agent-turn-metrics`.
Decisions in `design.md` (reviewed); evidence and version facts in `research-brief.md`.

## Global Constraints

- Every `Verify` / SC check is one pipe-free command under 60s run from `apps/api` with the env
  guard `env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/<x>.db ../../.venv/bin/python
  -m pytest … -q`; never the whole suite (it runs at `finishing-a-development-branch` and in CI
  on Postgres).
- Same-wave tasks share no files. Waves are dependency-ordered: wave 1 builds the leaf units
  (LLM flag, handler, pricing, table + repo, contract), wave 2 the stream / memory / dashboard
  consumers of those units, wave 3 the router wiring that ties them together.
- Metric collection and persistence are best-effort: no code path added here may raise into the
  reply path; failures log and continue (same posture as `persist_assistant_turn`).
- Additive schema only: one new table `agent_runs`, one Alembic revision with
  `down_revision = "c7f1a9d4e6b2"`, `downgrade` drops the table. No change to existing tables.
- Public contract changes are additive only: `ChatResponse.usage` (optional) and a `usage` key on
  the `done` SSE event. No FE change (`parseSSE.ts` maps known fields; extras are ignored).
- `stream_usage=True` goes only to the OpenAI SDK profile; other SDKs must not receive the kwarg.
- No new dependency. No message text, tool args or PII in `agent_runs`.
- Do not "fix" the loose `llm_calls ≥ 1` assertions: `FakeLLM.with_structured_output` returns a
  `RunnableLambda`, so structured supervisor / reflection calls never fire `on_llm_end` offline.
- Stage and commit as separate commands; no Claude attribution trailers; parallel implementers
  are implement-only, the controller commits.

## 1. Motivation

See `design.md` §1 and SUMMARY "Intake findings": nothing records tokens, cost or latency per
turn, and because `_build_chat_model` uses `streaming=True` while langchain-openai 0.3.34
defaults `stream_usage=False`, no OpenAI call even returns `usage_metadata` — Langfuse, when
enabled, sees zero tokens too.

## 2. Non-goals

Prompt prefix stabilisation / cache-hit optimisation; merging supervisor + slot extraction;
feedback-v1 columns (`assistant_message_id`, `prompt_versions`, …); Langfuse cost views; OTel
GenAI semconv; SQL percentiles; FE rendering of usage.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|------|-------------------------|-----------------------|------------|
| SC-1 | An OpenAI-profile chat model is built with `stream_usage=True`; a non-OpenAI profile receives no such kwarg; every FakeLLM reply carries `usage_metadata` and `response_metadata.model_name` | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/sc1.db ../../.venv/bin/python -m pytest tests/clients/test_llm_stream_usage.py -q` | exit 0 |
| SC-2 | The turn handler sums input / output / cached tokens per model across calls, counts calls and errors, times graph nodes keyed by namespace root, and swallows hook exceptions | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/sc2.db ../../.venv/bin/python -m pytest tests/agents/test_turn_metrics.py -q` | exit 0 |
| SC-3 | Cost = Σ((input − cached)·p_in + cached·p_cached + output·p_out)/1e6 for priced models; any unpriced model makes the turn cost `None`; dated snapshot suffixes resolve to the base price | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/sc3.db ../../.venv/bin/python -m pytest tests/core/test_pricing.py -q` | exit 0 |
| SC-4 | `agent_runs` is registered with the documented column set, the Alembic revision upgrades from empty and downgrades cleanly on SQLite, and the repository can start / finish / add-background / list a run | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/sc4.db ../../.venv/bin/python -m pytest tests/test_db_models.py tests/db/test_agent_runs_migration.py tests/repositories/test_agent_run_repo.py -q` | exit 0 |
| SC-5 | A `/agent/chat` turn returns `usage` with `llm_calls ≥ 1` and `input_tokens > 0` and leaves one `agent_runs` row whose status is `completed`, `interrupted` (HITL) or `failed` (graph error) with `by_node` containing `supervisor` | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/sc5.db ../../.venv/bin/python -m pytest tests/api/agent/test_agent_runs.py -q` | exit 0 |
| SC-6 | A `/agent/stream` turn's `done` event carries `usage`, the pass-through recorder closes the row with the status derived from `interrupt` / `error` events (and `failed` on cancellation), and existing event-order assertions still hold | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/sc6.db ../../.venv/bin/python -m pytest tests/streaming/test_record_agent_run.py tests/api/agent/test_stream_events.py -q` | exit 0 |
| SC-7 | Background memory extraction reports its own LLM calls / tokens / ms into `background_*` columns without touching the turn totals | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/sc7.db ../../.venv/bin/python -m pytest tests/memory/test_extraction_metrics.py -q` | exit 0 |
| SC-8 | `GET /dashboard/agent-runs` renders the recent runs and totals behind the dashboard guard (200 open in dev, 404 in production without credentials) | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/sc8.db ../../.venv/bin/python -m pytest tests/api/agent_config/test_agent_runs_dashboard.py -q` | exit 0 |

## 4. Tasks

### Task 1.1 — Request usage from OpenAI and make FakeLLM emit it (wave 1)

- **Files:** apps/api/app/clients/llm.py, apps/api/tests/clients/test_llm_stream_usage.py
- **Action:** In `_build_chat_model`, pass `stream_usage=True` to `init_chat_model` only when
  `profile.sdk == "openai"` (comment: `streaming=True` routes `invoke` through `_stream`, and
  langchain-openai 0.3.34 defaults `stream_usage=False`, so without this no call returns
  `usage_metadata`). In `FakeLLM._next`, when the produced `AIMessage` has no `usage_metadata`,
  set `usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}` and
  `response_metadata={"model_name": "fake-llm"}` (scripted `AIMessage` items that already carry
  usage are left as-is). New test module: build via the `openai` profile with a dummy key and
  assert `model.stream_usage is True`; monkeypatch `init_chat_model` to capture kwargs and
  assert the `anthropic` profile call carries no `stream_usage` key (ChatAnthropic declares its
  own default `True`; the guard exists to keep the kwarg OpenAI-scoped, not because others reject it); assert a FakeLLM `invoke` result carries the fixed
  usage and model name. Pre-scan at plan time found no test asserting `AIMessage` equality or
  `response_metadata` on FakeLLM output; if the Verify surfaces one anyway, report it as a
  blocker (it is outside this task's Files) instead of editing it.
- **Criteria:** SC-1
- **Interfaces:** Consumes: init_chat_model and the provider profile sdk field (existing code). Produces: `apps/api/app/clients/llm.py` (usage-emitting models), `apps/api/tests/clients/test_llm_stream_usage.py`.
- **Verify:** `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/t11.db ../../.venv/bin/python -m pytest tests/clients tests/agents/test_observability.py -q`
- **Done:** SC-1 test passes; `tests/clients` green; no other test module asserts FakeLLM message equality without usage.

### Task 1.2 — `TurnMetricsHandler` (wave 1)

- **Files:** apps/api/app/agents/metrics.py, apps/api/tests/agents/test_turn_metrics.py
- **Action:** New module with `class TurnMetricsHandler(BaseCallbackHandler)`: `run_inline =
  True`, `raise_error = False`, a `threading.Lock`, and the hooks in design.md §4.1:
  `on_chat_model_start` (start time per `run_id`, model name from
  `metadata.get("ls_model_name")`), `on_llm_end` (`llm_calls += 1` ALWAYS — `on_llm_end` receives no `metadata` kwarg, so the
  model name comes from the `run_id → model` map filled at start, preferring
  `response_metadata["model_name"]`; a call with neither name nor usage is counted but skipped
  for token aggregation; read `generations[0][0].message.usage_metadata`, aggregate with `langchain_core.messages.ai.add_usage`,
  cached = `input_token_details.cache_read`), `on_llm_error` (`llm_errors += 1`),
  `on_chain_start/end/error` (only when `metadata` has `langgraph_node` AND this
  `langgraph_checkpoint_ns` value is seen for the first time in the turn — nested runs inherit
  the task metadata, so later `run_id`s with the same namespace are ignored; key =
  `f"{ns_root}/{node}"` when the namespace has a parent segment else the bare node name;
  accumulate `ms` and `runs`). Every hook body is wrapped in `try/except Exception` → `logger.debug`.
  `snapshot() -> dict` and `public() -> dict` exactly as in design.md §4.1 (`cost_usd` filled by
  the owner via `pricing.estimate_cost`; the handler does not import pricing). `latency_ms` is
  set by `close(started: float)`. Tests: two models aggregated separately; cached tokens summed;
  error counted; node timing keyed by root; a nested chain run carrying the same
  `langgraph_checkpoint_ns` is not double-counted; a hook that raises (monkeypatched `add_usage`) leaves
  counters intact; `public()` keys are exactly the documented set.
- **Criteria:** SC-2
- **Interfaces:** Consumes: langchain-core 1.4.8 callback hooks and UsageMetadata (installed dependency). Produces: `apps/api/app/agents/metrics.py` (`TurnMetricsHandler.snapshot()/public()/close()`), `apps/api/tests/agents/test_turn_metrics.py`.
- **Verify:** `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/t12.db ../../.venv/bin/python -m pytest tests/agents/test_turn_metrics.py -q`
- **Done:** SC-2 passes; `ruff check app/agents/metrics.py` clean.

### Task 1.3 — Static price table + cost estimate (wave 1)

- **Files:** apps/api/app/core/pricing.py, apps/api/tests/core/test_pricing.py
- **Action:** New module: `ModelPrice(NamedTuple)` (`input`, `output`, `cached_input`, USD per
  1M tokens), `MODEL_PRICES_USD_PER_1M: dict[str, ModelPrice]` for every model listed in
  `LLM_PROVIDERS[*].models` plus `gpt-5` / `gpt-5-mini`, values copied from the pricing table in
  `research-brief.md` (Docs findings; all 12 catalogue models confirmed 2026-09-03 from the
  OpenAI, Anthropic and Google pricing pages) with a `# verified 2026-09-03 <url>` header per
  provider; Gemini 2.5 Pro uses the ≤200k-token tier and says so in a comment.
  `normalize_model(name)` strips a trailing `-YYYY-MM-DD` snapshot and a `models/` or
  `openai/` prefix (the `clinepass` gateway names models `openai/<model>`). Anthropic
  `cache_creation` tokens are not priced (no caching in scope) — say so in the header.
  `estimate_cost(by_model: dict[str, dict]) -> float | None` per design.md §4.2, returning
  `None` if any model is unpriced. Tests pin the formula with a fake price injected via
  monkeypatch (not the real numbers), the cached discount, `None` on unknown, and normalisation.
- **Criteria:** SC-3
- **Interfaces:** Consumes: the LLM_PROVIDERS model catalogue (existing code) and the pricing pages cited in research-brief.md. Produces: `apps/api/app/core/pricing.py` (`estimate_cost`, `normalize_model`), `apps/api/tests/core/test_pricing.py`.
- **Verify:** `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/t13.db ../../.venv/bin/python -m pytest tests/core/test_pricing.py -q`
- **Done:** SC-3 passes; every model in `LLM_PROVIDERS[*].models` has an entry in `MODEL_PRICES_USD_PER_1M`.

### Task 1.4 — `agent_runs` model, Alembic revision, repository (wave 1)

- **Files:** apps/api/app/db/models/agent_run.py, apps/api/app/db/models/__init__.py, apps/api/alembic/versions/e3b7c5d9a1f4_add_agent_runs.py, apps/api/app/repositories/agent_run.py, apps/api/tests/test_db_models.py, apps/api/tests/db/test_agent_runs_migration.py, apps/api/tests/repositories/test_agent_run_repo.py
- **Action:** `AgentRun(UUIDBase)` with the columns of design.md §4.4 (indexes on `user_id`,
  `conversation_id`, `status`; JSON for `by_model` / `by_node`; integer defaults 0). Register in
  `models/__init__.py` (`__all__` too). Alembic revision `e3b7c5d9a1f4` (`down_revision =
  "c7f1a9d4e6b2"`): `create_table` + the three indexes; `downgrade` drops them and the table.
  `AgentRunRepository` (constructor accepts a `Session` or a `sessionmaker`, mirroring
  `ConversationRepository`): `start(id, *, user_id, conversation_id, thread_id, trip_id, channel,
  kind, started_at)`, `finish(id, *, status, current_flow, finished_at, metrics: dict)` (maps
  the snapshot keys to columns; unknown keys ignored), `add_background(id, *, llm_calls,
  tokens, ms)` (increments), `list_recent(limit=100)`, `totals(since: datetime) -> dict`
  (turns, tokens, cost, latency list). `finish` on a missing id logs a warning and returns.
  Tests: add `agent_runs` to `test_all_tables_registered` and a column-set test; migration test
  copies the pattern of `tests/db/test_rate_limit_migration.py` (`_isolated_migration_url`,
  `alembic.command.upgrade(cfg, "head")` then `downgrade(cfg, "c7f1a9d4e6b2")`, inspector
  checks; SQLite locally, isolated schema on Postgres) and asserts the table and its three
  indexes appear then disappear; repo test covers
  start → finish → add_background → list_recent → totals on a tmp DB.
- **Criteria:** SC-4
- **Interfaces:** Consumes: UUIDBase, BaseRepository conventions and the Alembic env reading DATABASE_URL (existing code). Produces: `apps/api/app/db/models/agent_run.py`, `apps/api/alembic/versions/e3b7c5d9a1f4_add_agent_runs.py`, `apps/api/app/repositories/agent_run.py` (`AgentRunRepository`).
- **Verify:** `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/t14.db ../../.venv/bin/python -m pytest tests/test_db_models.py tests/db/test_agent_runs_migration.py tests/repositories/test_agent_run_repo.py -q`
- **Done:** SC-4 passes; `alembic heads` from apps/api prints exactly one head (`e3b7c5d9a1f4`).

### Task 1.5 — `TurnUsage` contract on `ChatResponse` and the `done` event (wave 1)

- **Files:** apps/api/app/schemas/agent.py, apps/api/app/streaming/events.py, apps/api/tests/api/agent/test_stream_events.py
- **Action:** Add `TurnUsage(AppBaseModel)` (`input_tokens`, `output_tokens`, `cached_tokens`,
  `total_tokens`, `llm_calls: int`; `latency_ms: int | None`; `cost_usd: float | None`;
  `models: list[str]`) and `ChatResponse.usage: TurnUsage | None = None` with a one-line field
  description. `events.done(...)` gains `usage: dict | None = None` and emits `"usage": usage` in
  the payload (always present, `null` when unknown). Update the `done` payload assertions in
  `test_stream_events.py` (the events-unit part only; mapper tests are touched in Task 2.1) to
  include `usage`, and add one case asserting the key is present and `None` by default.
- **Criteria:** SC-6
- **Interfaces:** Consumes: AppBaseModel and the events module _event helper (existing code). Produces: `apps/api/app/schemas/agent.py` (`TurnUsage`, `ChatResponse.usage`), `apps/api/app/streaming/events.py` (`done(usage=)`).
- **Verify:** `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/t15.db ../../.venv/bin/python -m pytest tests/api/agent/test_stream_events.py tests/streaming/test_events_language.py -q`
- **Done:** `done` payloads contain `usage`; `ChatResponse().model_dump()` contains `usage: None`; both test modules green.

### Task 2.1 — Stream recorder and `done.usage` in the mapper (wave 2)

- **Files:** apps/api/app/streaming/agent_run.py, apps/api/app/streaming/mapper.py, apps/api/tests/streaming/test_record_agent_run.py, apps/api/tests/api/agent/test_stream_events.py
- **Action:** `stream_agent_events` gains `metrics: TurnMetricsHandler | None = None`; before
  `events.done(...)` call `metrics.close(started)` (the mapper records `started =
  time.perf_counter()` at entry) and pass `usage=metrics.public()` (with `cost_usd` filled via
  `estimate_cost(metrics.snapshot()["by_model"])`); `usage=None` when `metrics` is None. New
  `record_agent_run(events_iter, *, run_id, metrics, session_factory)` in
  `app/streaming/agent_run.py`: async pass-through modelled on `persist_assistant_turn`; tracks
  `saw_interrupt` / `saw_error`, reads `current_flow` from the `done` payload, and in `finally`
  calls `AgentRunRepository(session_factory).finish(run_id, status=…, current_flow=…,
  finished_at=now, metrics=metrics.snapshot())` with status `interrupted` if an interrupt event
  was seen, `failed` on an error event or when the iterator exits by exception /
  `CancelledError` (re-raised), else `completed`; every repo error is logged, never raised.
  Tests: a scripted event iterator through the recorder → row status per scenario (completed /
  interrupted / error / cancelled via `aclose()`), events passed through unchanged; mapper test
  with a FakeLLM graph asserting the `done` event carries `usage.llm_calls ≥ 1`.
- **Criteria:** SC-6
- **Interfaces:** Consumes: `apps/api/app/agents/metrics.py` (1.2), `apps/api/app/core/pricing.py` (1.3), `apps/api/app/repositories/agent_run.py` (1.4), `apps/api/app/streaming/events.py` (1.5). Produces: `apps/api/app/streaming/agent_run.py` (`record_agent_run`), `apps/api/app/streaming/mapper.py` (`metrics=` parameter).
- **Verify:** `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/t21.db ../../.venv/bin/python -m pytest tests/streaming/test_record_agent_run.py tests/api/agent/test_stream_events.py -q`
- **Done:** SC-6 passes; event-name order lists in `test_stream_events.py` are unchanged.

### Task 2.2 — Background extraction metrics (wave 2)

- **Files:** apps/api/app/memory/extractor.py, apps/api/app/memory/extraction_runner.py, apps/api/tests/memory/test_extraction_metrics.py
- **Action:** `extract_memories(messages, llm, *, callbacks=None)` forwards
  `config={"callbacks": callbacks}` to `llm.invoke` when given. `run_memory_extraction` and
  `run_memory_extraction_from_stream` gain keyword-only `run_id: str | None = None` and
  `session_factory: sessionmaker | None = None`; when both are set, create a fresh
  `TurnMetricsHandler`, time the extraction with `perf_counter`, pass the handler as
  `callbacks`, and afterwards call `AgentRunRepository(session_factory).add_background(run_id,
  llm_calls=…, tokens=input+output, ms=…)` inside the existing best-effort `try`. Existing
  callers without the kwargs behave exactly as before. Tests: FakeLLM extraction with a tmp DB
  row → `background_llm_calls == 1`, `background_tokens == 15`, `background_ms ≥ 0`, turn
  columns untouched; no `run_id` → no DB access (spy on the repo).
- **Criteria:** SC-7
- **Interfaces:** Consumes: `apps/api/app/agents/metrics.py` (1.2), `apps/api/app/repositories/agent_run.py` (1.4). Produces: `apps/api/app/memory/extraction_runner.py` (`run_id=` / `session_factory=` kwargs), `apps/api/app/memory/extractor.py` (`callbacks=`).
- **Verify:** `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/t22.db ../../.venv/bin/python -m pytest tests/memory/test_extraction_metrics.py tests/memory/test_extraction_runner.py tests/memory/test_extractor.py -q`
- **Done:** SC-7 passes; existing memory tests green without modification.

### Task 2.3 — Dashboard page `/dashboard/agent-runs` (wave 2)

- **Files:** apps/api/app/routers/dashboard.py, apps/api/app/templates/agent_runs.html, apps/api/app/templates/base.html, apps/api/tests/api/agent_config/test_agent_runs_dashboard.py
- **Action:** Add `GET /dashboard/agent-runs` (same router / guard as the other pages,
  `response_class=HTMLResponse`): `AgentRunRepository(session).list_recent(100)` plus
  `totals(now − 24h)` and `totals(now − 7d)`; compute p50 / p95 of the latency list in Python
  (sorted index, no numpy). Template extends `base.html`: totals strip (turns, tokens in/out/
  cached, cost USD, p50 / p95 ms) and a table (started_at, user_id, channel/kind, status,
  current_flow, llm_calls, tokens, cost, latency); `status` rendered as a chip; a row with
  `status == running` older than 10 minutes labelled `abandoned`. Add the nav tab in
  `base.html` after `Weather`. Test: build the client the way `test_dashboard_auth.py` does,
  insert two runs via the repository, assert 200 + both ids in the body in dev, and 404 in
  production with no credentials.
- **Criteria:** SC-8
- **Interfaces:** Consumes: `apps/api/app/repositories/agent_run.py` (1.4) and the existing require_dashboard_access guard. Produces: `apps/api/app/templates/agent_runs.html`, `apps/api/app/routers/dashboard.py` (`agent_runs_page`).
- **Verify:** `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/t23.db ../../.venv/bin/python -m pytest tests/api/agent_config/test_agent_runs_dashboard.py tests/api/agent_config/test_dashboard_auth.py -q`
- **Done:** SC-8 passes; the existing guard tests stay green.

### Task 3.1 — Router wiring for `/agent/chat` and `/agent/stream` (wave 3)

- **Files:** apps/api/app/routers/agent.py, apps/api/tests/api/agent/test_agent_runs.py
- **Action:** `_config(thread_id, user_id, trip_id, *, run_id, metrics)` → adds `"run_id":
  uuid.UUID(run_id)` and `"callbacks": callbacks() + [metrics]`. In `agent_chat`: mint
  `run_id = str(uuid4())`, `metrics = TurnMetricsHandler()`, `started = perf_counter()`;
  `AgentRunRepository(session).start(run_id, …, channel="chat", kind="resume" if body.resume is
  not None else "turn")` inside a `try` that logs on failure (the existing `session.commit()`
  commits the row); after the run (all three outcomes: exception → `failed`, interrupt →
  `interrupted`, else `completed`) call `metrics.close(started)`, fill `cost_usd` via
  `estimate_cost`, `repo.finish(...)`, and set `ChatResponse.usage=TurnUsage(**metrics.public())`
  on both the normal and the fallback response. Pass `run_id=` and `session_factory=
  _isolated_factory(session)` to `run_memory_extraction`. In `agent_stream`: same minting and
  `start(..., channel="stream")` before `session.commit()`; wrap as
  `persist_assistant_turn(record_agent_run(stream_agent_events(..., metrics=metrics), run_id=…,
  metrics=…, session_factory=factory), …)`; pass `run_id=` / `session_factory=factory` to
  `run_memory_extraction_from_stream`. Tests (FakeLLM app client, as in the existing
  `tests/api/agent` modules): chat turn → response `usage.llm_calls ≥ 1`, `input_tokens > 0`,
  row `completed` with `by_node` containing `supervisor` and `kind == "turn"`; a scripted graph
  exception → 200 fallback reply + row `failed`; a HITL interrupt turn → row `interrupted`, the
  resume turn → a second row with `kind == "resume"`; stream turn → row `completed` and
  `channel == "stream"`; a failing `start` (monkeypatched to raise) still returns the reply.
- **Criteria:** SC-5
- **Interfaces:** Consumes: `apps/api/app/agents/metrics.py` (1.2), `apps/api/app/core/pricing.py` (1.3), `apps/api/app/repositories/agent_run.py` (1.4), `apps/api/app/schemas/agent.py` (1.5), `apps/api/app/streaming/agent_run.py` (2.1), `apps/api/app/memory/extraction_runner.py` (2.2). Produces: `apps/api/app/routers/agent.py` (`_config(run_id=, metrics=)`, wired endpoints), `apps/api/tests/api/agent/test_agent_runs.py`.
- **Verify:** `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/t31.db ../../.venv/bin/python -m pytest tests/api/agent/test_agent_runs.py tests/api/agent/test_stream_events.py -q`
- **Done:** SC-5 passes; `tests/api/agent` green.

### Task 3.2 — Docs and env example (wave 3)

- **Files:** WORKFLOW.md, apps/api/README.md, apps/api/.env.example
- **Action:** WORKFLOW.md: one short "Per-turn metrics" subsection (what is recorded, where,
  how `stream_usage` matters, the `done.usage` payload). apps/api/README.md: mention
  `/dashboard/agent-runs` next to the other dashboard pages and note that `cost_usd` is an
  estimate from `app/core/pricing.py`. `.env.example`: no new variable (state that explicitly
  in the task report); leave the file untouched if it needs no change.
- **Criteria:** SC-8
- **Interfaces:** Consumes: shipped behaviour of 2.3 / 3.1. Produces: `WORKFLOW.md` (metrics subsection), `apps/api/README.md`.
- **Verify:** `cd apps/api && grep -q "agent-runs" README.md && grep -q "Per-turn metrics" ../../WORKFLOW.md`
- **Done:** both grep hits present; no other doc claims the agent is un-instrumented.

## 5. Decisions taken from the research brief

- `agent_runs.trace_id` is **not** added now (brief follow-up Q1): Langfuse is opt-in and off by
  default; feedback-v1 adds the column with its own revision.
- Gemini 2.5 Pro is priced at its ≤200k-token tier (brief follow-up Q2), noted in the file header.
- `run_id` in the config is the LangChain root run id only; no Langfuse correlation is claimed.

## 6. Risks

- Provider usage shape: the app never sets Responses-only arguments, so gpt-5 runs on Chat
  Completions here and `cache_read` comes from `prompt_tokens_details.cached_tokens`
  (research-brief.md Docs findings); a future switch to the Responses API must re-check that
  `usage_metadata` still arrives through `generate_from_stream`.
- FakeLLM usage change may break exact-equality assertions elsewhere — Task 1.1 runs the wider
  suites and fixes them in place (Rule 1).
- SQLite write lock: `start` commits with the existing pre-run commit; `finish` uses the
  isolated factory on the stream path and the request session on the chat path (same as reply
  persistence today).

## 7. Status Log

- 2026-09-03 — intake complete (feature-intake); both forks resolved by the human (record in an
  `agent_runs` DB table; prompt-cache work deferred to its own spec). Design reviewed (one
  consistency fix: the router mints `run_id` and passes it to `start(id, …)`); xia2 Deep research
  brief corrected four design premises (Langfuse trace-id is not `run_id`; ChatAnthropic accepts
  `stream_usage`; gpt-5 runs on Chat Completions here; node timing must dedupe on
  `langgraph_checkpoint_ns`). Intake artifacts committed as 99ef433; PLAN held back until ship.

- 2026-09-03 — wave 1 complete: aff9b68 (1.1 stream_usage + FakeLLM usage), bc925af (1.2
  TurnMetricsHandler), 70ef3e8 (1.3 price table + estimate_cost), f65bca2 (1.4 agent_runs model +
  migration e3b7c5d9a1f4 + repository), b8cc8f5 (1.5 TurnUsage on ChatResponse and the done SSE
  event). Controller re-verify 94 passed, single alembic head, ruff clean. All five task reviews
  SPEC+QUALITY pass, zero Critical/Important. Load-bearing check confirmed: the ORM columns and
  the migration columns agree exactly (25), so SQLite `create_all` and Postgres Alembic produce
  identical schemas.

- 2026-09-03 — wave 2 complete: a4164e6 (2.1 stream recorder + done.usage), 69959e5 (2.2
  background extraction metrics), dc7fc5d (2.3 /dashboard/agent-runs). Controller re-verify 67
  passed, ruff clean. All three reviews pass. One Minor fixed in-flight (1a6fad7): `add_background`
  ran before the memory upserts in a shared best-effort try, so a metrics-DB failure could skip the
  primary memory writes — moved after the upserts into its own isolated try. Rule-1 deviation
  accepted in 2.1: `time.monotonic()` instead of the brief's `perf_counter`, to match
  `TurnMetricsHandler.close()`; mixing clocks would have corrupted `latency_ms`.

- 2026-09-03 — wave 3 complete: 569ed7f (3.1 router wiring for /agent/chat and /agent/stream),
  e84ec35 (3.2 docs). Controller re-verify 53 passed. Both reviews pass; the integration review
  cleared the failure-fallback, HITL interrupt/resume, and double-finish risks explicitly.

- 2026-09-03 — final chain. intent-review PASS (plan-blind: every promised piece lands, deferred
  scope verified absent, no overreach). correctness-review PASS with 2 Important + 2 Minor
  metric-accuracy findings, ALL FIXED in 1a494e9 and re-reviewed pass: a failed/cancelled stream
  turn persisted NULL latency and cost (so every failed turn dropped out of the dashboard
  rollups); `estimate_cost({})` returned a confident 0.0 instead of unknown; the checkpoint-
  namespace dedupe swallowed a node retry's timing; and the mapper's metrics block was unguarded
  inside the stream's own try. SHIPPED. verify_summary --check: SC-1..SC-8 all re-run green;
  receipt at .review-receipt.json (12 reviews, correctness + intent). Follow-ups in SUMMARY
  "Not auto-verified": live-provider cost accuracy, the Postgres migration path (CI), and prompt
  prefix stabilisation / cache-hit measurement as its own spec.
