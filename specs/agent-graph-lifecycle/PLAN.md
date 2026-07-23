---
slug: agent-graph-lifecycle
status: active
owner: Minh Tran
created: 2026-06-26
---

# Agent graph lifecycle — build once, Postgres-only async checkpoint (REVIEW.md C1)

## 1. Motivation

`specs/travel-agent/REVIEW.md` **C1**: the agent graph + checkpointer + store are rebuilt on
every `/agent/*` request (`get_travel_graph` calls `build_graph(get_checkpointer(), get_store())`),
leaking a DB connection / unentered context manager and re-running `.setup()` each call; the
`@lru_cache`'d `get_compiled_graph()` and the lifespan-built `app.state.agent_checkpointer` are
both dead. Per E001 the checkpointer is **Postgres-only** and migrates to the **async** saver.

## 2. Non-goals

- C3 (long-term-memory semantic index + `InjectedState` user_id) — separate follow-up. The store
  stays sync (`PostgresStore`) so the sync memory tools keep working; only its *lifecycle* is fixed.
- C2 / C4 / M2 / M4 / M5 and other review items — separate.
- Removing `langgraph-checkpoint-sqlite` from requirements (left installed; just unused).

## 3. Success criteria

- Graph + checkpointer + store built **once** at startup, shared via `app.state.travel_graph`.
- No per-request `.setup()` / connection open; no unentered `from_conn_string` context managers.
- Postgres path uses `AsyncPostgresSaver` (libpq DSN), entered with `async with` in `lifespan`,
  closed on shutdown; non-Postgres degrades to `MemorySaver` so local/test still start.
- `pytest -q` green on SQLite; `ruff check` clean. Postgres path verified via `make test-docker`.

## 4. Tasks (one wave — files are interdependent, executed sequentially)

### Task 1.1 — Checkpointer: Postgres-only, async, lifecycle-managed

```xml
<task id="1.1">
  <files>app/agents/checkpointer.py</files>
  <action>Replace the sync SQLite/Postgres selection with: `open_checkpointer(url)` (an @asynccontextmanager yielding AsyncPostgresSaver for postgres URLs — `_libpq_dsn` strips `+psycopg`, `await saver.setup()` — else MemorySaver, degrading on any failure). Keep `get_checkpointer(url)` as a sync helper returning MemorySaver (tests / non-Postgres degrade). Drop SqliteSaver + sqlite3 imports.</action>
  <verify>.venv/bin/pytest tests/agents/test_checkpointer.py -q</verify>
  <done>open_checkpointer degrades to MemorySaver off-Postgres; no SqliteSaver import remains.</done>
</task>
```

### Task 1.2 — Store: build-once lifecycle (sync PostgresStore kept)

```xml
<task id="1.2">
  <files>app/memory/store.py</files>
  <action>Add `open_store(url)` (@asynccontextmanager): postgres -> `with PostgresStore.from_conn_string(_libpq_dsn(url)) as s: s.setup(); yield s`; else `yield InMemoryStore()`. Simplify `get_store` to return InMemoryStore (tests/degrade) and drop the leaky `.__enter__()`. Leave upsert/search helpers unchanged.</action>
  <verify>.venv/bin/pytest tests/agents/test_memory.py -q</verify>
  <done>No `.__enter__()` without exit; in-memory tests pass.</done>
</task>
```

### Task 1.3 — Remove dead cached-graph builder

```xml
<task id="1.3">
  <files>app/agents/graph.py</files>
  <action>Delete the unused `@lru_cache get_compiled_graph()` and the `functools.lru_cache` import. Keep `build_graph(...)` as-is.</action>
  <verify>.venv/bin/python -c "import app.agents.graph"</verify>
  <done>graph.py imports clean; no get_compiled_graph symbol.</done>
</task>
```

### Task 1.4 — Build the graph once in lifespan

```xml
<task id="1.4">
  <files>app/core/lifespan.py</files>
  <action>Replace the `app.state.agent_checkpointer` block with `async with open_checkpointer(url) as cp, open_store(url) as store:` wrapping the existing `yield`; inside, `app.state.travel_graph = build_graph(checkpointer=cp, store=store)` guarded by try/except (-> None + log on failure). Lazy imports inside the function (matches existing pattern).</action>
  <verify>.venv/bin/pytest tests/api/agent/test_agent_chat.py -q</verify>
  <done>App starts; app.state.travel_graph set once; agent API tests pass.</done>
</task>
```

### Task 1.5 — Router resolves the shared graph

```xml
<task id="1.5">
  <files>app/routers/agent.py</files>
  <action>`get_travel_graph(request: Request)` returns `request.app.state.travel_graph`, raising `UpstreamError` when None. Remove the build_graph / get_checkpointer / get_store imports.</action>
  <verify>.venv/bin/pytest tests/api/agent/test_agent_chat.py -q</verify>
  <done>chat/stream/manifest pass via the dependency override; no per-request build.</done>
</task>
```

### Task 1.6 — Tests for the new contract

```xml
<task id="1.6">
  <files>tests/agents/test_checkpointer.py</files>
  <action>Replace the SqliteSaver assertion with the new contract: get_checkpointer returns MemorySaver; an async test that `open_checkpointer("sqlite://")` yields MemorySaver; keep the thread_id-persistence test (MemorySaver persists in-process). Add anyio/asyncio marker as the repo uses.</action>
  <verify>.venv/bin/pytest tests/agents -q</verify>
  <done>All agent unit tests green under Postgres-only design.</done>
</task>
```

## 5. Risks

- Real graph now builds at startup (lifespan) for every test booting the app — mitigated: `build_graph` constructs without network and is wrapped in try/except (-> `travel_graph=None`), and no test invokes the real graph over HTTP (agent API tests override the dep).
- Postgres async path is not exercised by the SQLite suite — verified separately via `make test-docker`.

## 6. Status Log

- 2026-06-26 — intake (normal lane, confidence high after E001); branch `fix/agent-graph-lifecycle`.
- 2026-06-26 — Tasks 1.1–1.6 implemented + verified. `ruff check app` clean; `pytest -q` 844 passed
  (SQLite); `make test-docker` 844 passed (Postgres/py3.12); positive Postgres proof PASS
  (AsyncPostgresSaver + PostgresStore engage, checkpoint persists 1→2, store round-trips). NOT yet
  committed (awaiting user). Note: an unrelated prompt-registry restructure (`app/prompts/*` renames
  + `registry.py` + `test_registry.py`) is present in the working tree and was left untouched.
