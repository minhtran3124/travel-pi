---
slug: llm-readiness
status: proposed
owner: Minh Tran
created: 2026-06-20
---

# LLM/Agent Readiness — structural prep (no LLM applied yet)

## 1. Motivation
Prepare the FastAPI backend to host an LLM/agent feature *later* without
restructuring. The codebase is already well-suited (clean layering, async path,
pydantic-settings, typed schemas, agent-aware error envelope); this plan fills
the specific gaps surfaced by the readiness review. **Scope is seams + fakes
only — no Anthropic SDK dependency, no prompts, no real model calls.** Each task
is verifiable without network or API keys.

Provider assumption when the feature lands: Anthropic SDK (`AsyncAnthropic`),
default model `claude-opus-4-8`, streaming for large outputs. Nothing here
imports it yet.

## 2. Non-goals
- Wiring a real LLM client, prompts, or tool schemas (that's the feature).
- Secrets manager, metrics/Prometheus, Celery, websockets, distributed cache —
  all violate the repo's "keep it minimal" rule and aren't needed to be *ready*.
- API contract changes to existing endpoints.

## 3. Success Criteria
- A single lifespan-managed async HTTP client exists; weather + routing borrow it
  (no behavior change, suite green).
- An SSE/streaming response helper exists with a demo endpoint, tested against a
  fake generator.
- A long-running-work execution model is chosen and a `Job` record scaffolded.
- Request-ID + a no-op usage-metering seam exist in the middleware/logging layer.
- A `FakeLLMClient`-style DI pattern is demonstrated (overridable in tests).
- `make test` stays green throughout; no new runtime dependency added.

## 4. Tasks

### Task 1.1 — Shared async HTTP client (lifespan-managed)

```xml
<task id="1.1" wave="1">
  <files>app/core/http.py, app/core/lifespan.py, tests/core/test_http_client.py</files>
  <action>Add a single lifespan-managed httpx.AsyncClient factory in app/core/http.py (pool + default timeout from settings; expose get_http_client()). Open it in lifespan startup, close on shutdown. Do NOT change weather/routing yet (that is 2.1). This is the seam a future app/clients/llm.py AsyncAnthropic singleton will mirror.</action>
  <verify>.venv/bin/python -m pytest tests/core/test_http_client.py -x</verify>
  <done>Client constructed once, reused, closed on shutdown; test asserts singleton identity + closed state.</done>
</task>
```

### Task 1.2 — SSE / streaming response helper + demo

```xml
<task id="1.2" wave="1">
  <files>app/core/streaming.py, app/routers/_stream_demo.py, tests/api/test_streaming.py</files>
  <action>Add an SSE StreamingResponse helper (text/event-stream, proper media type + headers) that consumes an async generator of str chunks. Add a demo router streaming a fake token generator (no LLM). This is the contract a future client.messages.stream() text_stream will feed.</action>
  <verify>.venv/bin/python -m pytest tests/api/test_streaming.py -x</verify>
  <done>Demo endpoint streams chunked SSE; test reads multiple events and a terminal event.</done>
</task>
```

### Task 2.1 — Migrate weather + routing onto the shared client

```xml
<task id="2.1" wave="2">
  <files>app/services/weather_service.py, app/services/routing_service.py</files>
  <action>Replace the per-request httpx.AsyncClient instantiation in each _fetch_json with the shared get_http_client() from 1.1. Preserve timeouts, UpstreamError mapping, and the routing in-process cache exactly. Pure refactor — no behavior change.</action>
  <verify>.venv/bin/python -m pytest tests/api/weather tests/api/routes -x</verify>
  <done>Weather/routing suites pass; no per-request client construction remains.</done>
</task>
```

### Task 2.2 — Request-ID middleware + usage-metering seam

```xml
<task id="2.2" wave="2">
  <files>app/main.py, app/core/logging.py, tests/infra/test_request_id.py</files>
  <action>Add a request-ID middleware (generate or honor X-Request-ID; attach to response header + log lines). Add a no-op record_usage(request_id, usage_dict) seam in logging.py for a future LLM path to call. Keep console logging minimal per CLAUDE.md.</action>
  <verify>.venv/bin/python -m pytest tests/infra/test_request_id.py -x</verify>
  <done>Every response carries a request id; record_usage is importable and a no-op.</done>
</task>
```

### Task 3.1 — Job record + long-running-work model decision

```xml
<task id="3.1" wave="3">
  <files>app/db/models/job.py, app/crud/job.py, alembic/versions/, tests/db/test_job.py</files>
  <action>Decide async model (recommend: BackgroundTasks + Job row + poll/SSE for status). Scaffold a Job ORM model (uuid id + timestamps via the mixins, status enum, result JSON, error text) and a JobRepository. Regenerate the single migration; reseed not required (jobs is runtime state). No agent loop yet.</action>
  <verify>rm -f travel.db && .venv/bin/alembic upgrade head && .venv/bin/alembic check && .venv/bin/python -m pytest tests/db/test_job.py -x</verify>
  <done>jobs table migrates clean (no drift); create/get/transition-status repo tests pass.</done>
</task>
```

### Task 3.2 — DI pattern + fake-client convention for future LLM I/O

```xml
<task id="3.2" wave="3">
  <files>app/core/deps.py, tests/conftest.py, tests/core/test_fake_client_pattern.py</files>
  <action>Demonstrate the FastAPI Depends + dependency_overrides pattern (mirroring booking_service) for an injected external client, with a FakeClient used in tests — establishing the convention a future get_llm_client() + FakeLLMClient will follow. Documents the chosen DI style; avoids the module-singleton/test-isolation footgun.</action>
  <verify>.venv/bin/python -m pytest tests/core/test_fake_client_pattern.py -x</verify>
  <done>A Depends-injected client is overridable in tests; pattern documented in the test/module docstring.</done>
</task>
```

## 5. Risks
- 2.1 touches live upstream paths (weather/routing) — pure refactor, guarded by
  their existing suites; any behavior drift fails verify.
- 3.1 is a schema change (Rule 4 territory): new `jobs` table. It's additive and
  in-spec here; regenerate the single migration and run `alembic check`.
- Over-scaffolding risk: keep each seam minimal + demo-only. If a task grows past
  its `<files>`, stop and re-scope.

## 6. Status Log
- 2026-06-20: plan drafted from the LLM-readiness review (proposed).
