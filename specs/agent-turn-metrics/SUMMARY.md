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

<not started — intake only. Fill at ship.>

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

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| intake evidence | `python3 .claude/scripts/verify_summary.py --lane agent-turn-metrics` | 0 | lane/confidence/reason + rollback present | |

### Not auto-verified

- none yet — intake only; every claim above is a code-reading finding, not a re-run behaviour.

### Rollback

- Intake only: `git rm -r specs/agent-turn-metrics`. Implementation rollback (fill at ship): `alembic downgrade -1` from apps/api + `git revert <sha>`.

### Harness-Delta

- none
