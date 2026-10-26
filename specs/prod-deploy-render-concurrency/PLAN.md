---
slug: prod-deploy-render-concurrency
status: draft
owner: Minh Tran
created: 2026-10-26
lane: high-risk
---

# Production deploy on Render (Docker) with safe concurrent agent chats

**Goal:** Deploy `apps/api` to Render as Docker services so that **10 users can chat with the agent concurrently** (design target; ≥5 is the floor, scale beyond by adding instances) without exhausting Postgres connections, hitting LLM rate limits, corrupting a conversation's state, or losing background work on redeploy.

**Non-goals:** Moving the backend to Cloudflare (rejected: no Postgres/pgvector, native `psycopg`, long-lived SSE/research). Frontend hosting (Vercel or Cloudflare Pages, separate decision). Changing agent behaviour or prompts.

## Ambiguity (behavior.md #2)

"5 agents in parallel" has two readings:

- **A. 5 specialists inside one turn.** Already exists (`Send` fan-out to `synthesis_worker`, `agents/supervisor.py:397`). Only needs a concurrency cap (Task 3).
- **B. 5+ concurrent chats / replicas.** The main target of this plan.

Picked **B**, with A bounded by the same cap.

## Verified current state (from code, 2026-10-26)

| Area | Finding | Source |
|---|---|---|
| Server | Single `uvicorn` process; compose uses `--reload` + bind mount | `apps/api/Dockerfile`, `docker-compose.yml` |
| Migrations | `alembic upgrade head` runs in every container's entrypoint | `docker/entrypoint.sh` |
| SQLAlchemy pool | `create_engine` with default pool (5 + 10 overflow), no sizing | `app/db/engine.py` |
| Checkpointer / store | `AsyncPostgresSaver.from_conn_string` and `PostgresStore.from_conn_string`: one dedicated connection each per process | `agents/checkpointer.py`, `memory/store.py` |
| Chat route | Request `session` held across the whole `graph.ainvoke` | `routers/agent.py:199` |
| LLM concurrency | No semaphore / `max_concurrency` on graph config; `_config()` sets only recursion_limit, callbacks | `routers/agent.py:100` |
| LLM retry | `RetryPolicy` exists (`agents/retry.py`); SDK `max_retries=0` | `specs/agent-fault-tolerance` |
| Same-thread race | No guard against two concurrent turns on one `thread_id`. `db/locks.py` has `advisory_xact_lock` but chat does not use it | grep `advisory_xact_lock` |
| Process-local state | `ProgressBus` (research SSE), `_BACKGROUND_TASKS`, route/climate/web-search/injection caches, `AgentConfigCache` (DB-polled, safe) | `research/progress.py`, `research/launcher.py` |
| Background work | Research via `asyncio.create_task` in the web process; memory extraction via `BackgroundTasks` | `research/launcher.py`, `routers/agent.py` |
| Rate limit / quota | DB-backed, atomic increment, multi-worker safe | `core/rate_limit.py`, `services/quota_service.py` |
| Probes | `/healthz` (liveness), `/readyz` (readiness) exist | `routers/health.py` |
| Timeouts | `llm_timeout_seconds=120`, `research_timeout_s=600` | `core/config.py` |

## Target architecture

```
Render
 ├─ Web Service  api        Docker, gunicorn -k uvicorn.workers.UvicornWorker, N instances
 ├─ Background Worker       same image, Arq consumer: research + memory extraction
 ├─ Key Value (Redis)       Render managed: Arq queue + research progress pub/sub
 ├─ Pre-deploy job          alembic upgrade head (single run per deploy)
 └─ Postgres (pgvector)     PgBouncer not needed at the 10-user target
```

### Sizing for 10 concurrent users (decided)

- Web: **2 instances × 2 gunicorn workers = 4 processes**, so a single instance restart or deploy never takes the API down.
- Each in-flight turn holds 1 DB session; 10 users spread over 4 processes is about 3 per process.
- **Connection budget:** `processes × (pool_size + max_overflow + 2 [checkpointer, store]) + worker + migrate job ≤ 0.8 × max_connections`.
  With pool 5 + overflow 5: 4 × 12 = 48, plus worker (~12) = about 60. Needs `max_connections` ≥ ~75. **Verify the chosen Render Postgres plan's `max_connections` before purchase** (not confirmed here); if it is lower, drop to pool 3 + overflow 2 (4 × 7 = 28 + 7 = 35).
- **LLM cap:** per-process semaphore 6, so 24 concurrent model calls at most across 4 processes (10 turns × up to ~3 parallel specialist calls would otherwise reach 30+). Check that this stays within the provider account's RPM/TPM tier; lower the semaphore if not.

### Postgres suggestion

Start on a **paid Render Postgres tier with at least 1 GB RAM** (pgvector index + checkpoint writes grow with conversations; the free and smallest tiers are not suitable). 10 users does not need HA or PgBouncer. Revisit when concurrent users exceed ~30 or when `pg_stat_activity` in the load test exceeds 70% of `max_connections`. Enable daily backups. Confirm pgvector is available on the selected plan.

## Tasks

### Wave 1 (independent, disjoint files)

**Task 1 — Production image and process model**
- Files: `apps/api/Dockerfile`, `apps/api/requirements.txt` (add `gunicorn`), new `apps/api/docker/start-web.sh`, `docker/entrypoint.sh`
- Add gunicorn start (`-w ${WEB_CONCURRENCY:-2}`, `--graceful-timeout`, `--timeout` ≥ 150 s so a 120 s LLM call is not killed). Run as non-root. Dev compose keeps `--reload`; production path uses a separate command.
- Make migration opt-in in the entrypoint (`RUN_MIGRATIONS=1`); Render pre-deploy job sets it, web/worker do not.
- Verify: `docker build apps/api` succeeds; container answers `/healthz`; `docker run -e RUN_MIGRATIONS=0` does not call alembic.

**Task 2 — DB pool sizing**
- Files: `app/db/engine.py`, `app/core/config.py` (`db_pool_size`, `db_max_overflow`, `db_pool_timeout`, default 5/5/30)
- Apply only to non-SQLite URLs (SQLite pool args differ).
- Verify: unit test that `get_engine("postgresql+psycopg://...")` pool reports configured sizes; `make test` green.

### Wave 2 (depends on Wave 1 config style)

**Task 3 — LLM concurrency cap**
- Files: `app/routers/agent.py` (`_config`), `app/core/config.py` (`agent_max_concurrency`, `llm_global_concurrency`), `app/clients/llm.py` or a small `app/agents/limiter.py`
- Per-turn: set `max_concurrency` in the graph `RunnableConfig` to bound the `Send` fan-out (reading A).
- Per-process: an `asyncio.Semaphore(llm_global_concurrency)` around chat-model calls so N concurrent chats cannot exceed provider rate limits. Confirm `agents/retry.py` treats 429 as retryable; add if not.
- Verify: test with `FakeLLM` that 10 concurrent turns never exceed the semaphore limit (counter in the fake); 429 simulated and retried.

**Task 4 — Same-thread serialization**
- Files: `app/routers/agent.py`, `app/db/locks.py` (reuse)
- Prevent two simultaneous turns on one `thread_id`. Use a Postgres session-level advisory lock keyed on `thread_id` (`pg_try_advisory_lock`), returning `ConflictError` (409) if held. Must release on all exit paths. Note: `advisory_xact_lock` is transaction-scoped and `agent_chat` commits mid-turn, so the xact variant is not sufficient; a session-level lock on a dedicated connection is required.
- Verify: concurrent double-POST test on Postgres (`make test-docker`): one 200, one 409; lock released after failure.

**Task 5 — Move background work off the web process**
- Files: `app/research/launcher.py`, `app/memory/extraction_runner.py`, new `app/worker.py`, `render.yaml`
- Queue: **Arq on Redis** (decided; Render Key Value). Add `arq` and `redis` to `requirements.txt`, `REDIS_URL` to settings. The web process only enqueues; `app/worker.py` defines the Arq `WorkerSettings` with `run_research` and `run_memory_extraction` jobs. Jobs must be idempotent and keyed by `run_id`. `ResearchService.sweep_stale` stays as the safety net for jobs lost with Redis.
- Local/test: when `REDIS_URL` is unset, fall back to today's in-process behaviour so `make test` and SQLite dev stay zero-config.
- Verify: kill the web process mid-research in a docker-compose sim (add a `redis` service to `docker-compose.yml`); the worker finishes or marks the run failed, with no stuck `running` rows.

### Wave 3

**Task 6 — Cross-instance research progress**
- Files: `app/research/progress.py`, research SSE router
- Replace in-memory `ProgressBus` fan-out with **Redis pub/sub** (already present for Task 5) so an SSE client on any web instance sees progress from a run on the worker. Keep the existing DB-snapshot branch for finished runs. No sticky sessions needed.
- Verify: integration test with two app instances sharing one DB.

**Task 7 — Render config**
- Files: new `render.yaml` at repo root (web ×2 instances, worker, Key Value, pre-deploy migrate, env group), `docs/` runbook
- Health check path `/readyz`; env vars (secrets set in Render dashboard, never committed): `DATABASE_URL`, `REDIS_URL`, `ENVIRONMENT=production`, provider keys, pool and concurrency settings. Paid plans only (free tier sleeps).
- Ensure LB/proxy idle timeout is above the longest SSE/turn.
- Verify: Render Blueprint validate; staging deploy passes `/readyz`.

### Wave 4 — Proof

**Task 8 — Load and concurrency test**
- Files: `apps/api/scripts/loadtest_chat.py` (or k6), `docs/solutions/` note
- Scenarios: 5 → 10 → 20 concurrent chats with `FakeLLM`, then a short run with the real provider. Record p95 latency, Postgres `pg_stat_activity` count, 429 count, error rate.
- Acceptance: **10 concurrent chats** complete with 0 5xx, Postgres connections stay under 70% of `max_connections`, and no state cross-talk (each thread's history contains only its own messages). 20 concurrent is a headroom check, not a gate.
- Also add one concurrent case to the agent eval smoke (`make eval-smoke`).

## Risks

| Risk | Mitigation |
|---|---|
| Connection exhaustion at scale-out | Budget formula + PgBouncer; load test records `pg_stat_activity` |
| Provider 429 under bursts | Semaphore + `max_concurrency` + retry on 429 |
| Session-level advisory lock leaks | try/finally release; test failure paths; lock auto-releases when the connection closes |
| Deploy kills in-flight turns | gunicorn graceful timeout; Render shutdown delay; worker owns long jobs |
| Migration race across replicas | Single pre-deploy job; entrypoint opt-in |
| Redis outage or restart loses queued jobs and live progress | Jobs are idempotent by `run_id`; `sweep_stale` recovers; progress falls back to the DB snapshot; Redis is not a source of truth |
| New moving part (Redis) for a 10-user load | Accepted by owner; kept optional locally via the `REDIS_URL` fallback |
| Alembic migration on a live DB | No schema change planned except an optional job table (Task 5); additive only |

## Open questions

Decided 2026-10-26: Postgres paid tier ≥1 GB without PgBouncer; queue is Arq on Redis; target is 10 concurrent users.

1. Exact `max_connections` of the chosen Render Postgres plan, and that pgvector is available on it (verify in the Render dashboard/docs before purchase).
2. The LLM provider account's RPM/TPM limits, to confirm the semaphore of 6 per process.

## Done criteria (evidence)

- `make test` and `make test-docker` green.
- `docker build apps/api` and container smoke (`/healthz`, `/readyz`) pass.
- Load-test script re-runnable with recorded numbers meeting the acceptance line in Task 8.
- `SUMMARY.md` written in this folder at completion; `specs/STATE.md` updated.
