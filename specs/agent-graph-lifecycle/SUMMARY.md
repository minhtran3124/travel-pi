# agent-graph-lifecycle — Summary

Lane: normal
Confidence: high
Reason: Rewires the agent graph/checkpointer/store lifecycle (existing tested behavior); intent confirmed via E001 (Postgres-only + async savers), no skill-listed hard gate fires.
Flags: existing-behavior, weak-proof
Affects: app/agents (graph.py, checkpointer.py, store.py), app/core/lifespan.py, app/routers/agent.py — internal wiring of the /agent/* endpoints
Input-type: change request

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

<!-- User's request VERBATIM at intake — the oracle for /intent-review. -->

> check C1 from specs/travel-agent/REVIEW.md
> but cần update ở chỗ là dùng postgres cho checkpoint ko phải sqlite

Context for the oracle: **C1** in `specs/travel-agent/REVIEW.md` = "Graph + checkpointer +
store rebuilt on *every request* (the `lru_cache` is dead code)". The router's
`get_travel_graph` dependency calls `build_graph(checkpointer=get_checkpointer(),
store=get_store())` fresh per request, leaking a connection / unentered context manager and
re-running `.setup()` each call; the `@lru_cache`'d `get_compiled_graph()` and the
lifespan-built `app.state.agent_checkpointer` are both unused. The fix is to build the graph +
checkpointer (+ store) **once** at startup and share it. The added constraint: the checkpoint
must use **Postgres**, not SQLite.

## What changed

The agent graph + checkpointer + store are now built **once** in `lifespan` and shared via
`app.state.travel_graph`; `get_travel_graph(request)` returns it (was: rebuilt per request,
leaking a DB connection + re-running `.setup()` each call — REVIEW.md C1). The checkpointer is
Postgres-only and **async** (`AsyncPostgresSaver`, opened with `async with` + `await setup()`),
degrading to `MemorySaver` off-Postgres so local/test still start; the store's lifecycle is
likewise managed once (`PostgresStore` / `InMemoryStore`). Removed the dead `@lru_cache
get_compiled_graph`. (Store semantic index + `user_id` injection = REVIEW.md C3, deferred.)

### Rationale

C1 is a real resource leak (per-request `.setup()` + unclosed `from_conn_string` context
managers) and the smallest-diff, highest-value fix from the review. The Postgres-checkpointer
constraint intersects M3 (sync-saver-under-async) and the project's DATABASE_URL engine-split,
so the exact backend scope must be confirmed before implementing.

### Alternatives considered

<!-- The fork escalated in E001 — resolved by the user. -->

- A) Keep the DATABASE_URL engine-split; SQLite/memory stays for local + tests. **Rejected by user.**
- B) **CHOSEN** — Postgres-only checkpointer (remove the SQLite path) + migrate to **async**
  savers (AsyncPostgresSaver / AsyncPostgresStore), built once via `async with` in lifespan and
  shared via `app.state`. A MemorySaver/InMemoryStore degrade keeps Postgres-less local/test runs
  starting; tests inject the in-memory savers explicitly.

### Deviations

- Rule 1 — Rewrote `tests/agents/test_checkpointer.py`: the SQLite-saver assertion is gone
  (SQLite checkpointer path removed per E001); added async `open_checkpointer` degrade + `_libpq_dsn`
  tests. In-scope with the chosen design.
- Rule 2 — The sync `get_checkpointer`/`get_store` helpers now return only the in-memory savers;
  the durable Postgres backends are built via the new `open_*` context managers (lifecycle-managed).
  `langgraph-checkpoint-sqlite` is now unused but left installed (dep removal out of scope).

### Verify

<!-- Filled after implementation. -->

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Lint (app) | `ruff check app` | 0 | clean |
| Full suite (SQLite) | `.venv/bin/pytest -q` | 0 | 844 passed (was 843; +1 checkpointer test) |
| Cross-engine (Postgres, py3.12) | `make test-docker` | 0 | 844 passed |
| Postgres async path (positive) | `PYTHONPATH=. .venv/bin/python scratchpad/verify_pg_checkpointer.py` | 0 | AsyncPostgresSaver + PostgresStore engage (not degrade); checkpoint persists 1→2; store put/search round-trips |

### Rollback

- `git revert <sha>` (per-commit; reversible — config + wiring only, no data migration)

### Harness-Delta

- none
