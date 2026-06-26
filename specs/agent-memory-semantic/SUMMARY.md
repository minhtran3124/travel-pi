# agent-memory-semantic — Summary

Lane: normal
Confidence: high
Reason: Wires a semantic index into the long-term store + injects user_id from graph state (REVIEW.md C3); changes an existing tool signature (tested) but no skill-listed hard gate fires.
Flags: existing-behavior, weak-proof
Affects: app/memory/store.py, app/tools/memory_tools.py, app/rag/embeddings.py — long-term memory + journal tools
Input-type: change request

> `Lane` drives ceremony; `Confidence` drives interruption. No hard gate; direction
> unambiguous — PROCEED. Stacked on C1 (`fix/agent-graph-lifecycle`) since both touch `store.py`.

### Intent

> tiep tuc vs C3

Context: **C3** in `specs/travel-agent/REVIEW.md` — "Long-term memory: semantic search is
non-functional (store built with **no `index=`** config, so `store.search(query=...)` is silently
ignored), and `user_id` is **model-supplied** (`save_user_preference(user_id, …)`), a cross-user
leakage risk since the namespace `("users", user_id, "prefs")` is the isolation boundary."

## What changed

1. **Semantic index** — `app/memory/store.py` now builds both the `PostgresStore` and the
   `InMemoryStore` (and the degrade path) with an `index` config (`_index_config()`: `dims`,
   `embed=get_embeddings()`, `fields=["text"]`), so `store.search(ns, query=…)` ranks by embedding
   similarity instead of silently ignoring the query. `app/rag/embeddings.py` exposes `EMBED_DIM`.
2. **Tenant-safe `user_id`** — `app/tools/memory_tools.py` injects `user_id` from
   `TravelAgentState` via `Annotated[str, InjectedState("user_id")]` (hidden from the model schema,
   like the existing `InjectedStore`), so the LLM can no longer address another traveller's memory.

### Rationale

Smallest fix that makes the existing store/tools correct: reuse the RAG embeddings model for the
index; match the existing `InjectedStore` pattern with `InjectedState` (not the larger `ToolRuntime`
migration, REVIEW.md L4). The store stays **sync** per the C1 decision — only the index is added.

### Alternatives considered

- `ToolRuntime` for injection (LangChain 1.x idiom) — deferred (L4 modernization).
- Async store (`AsyncPostgresStore`) — deferred; would force async memory tools.

### Deviations

- Rule 1 — Updated `tests/tools/test_tool_registry.py` (`user_id` is now injected, not a model arg)
  and added C3 tests (semantic query + end-to-end injection). In-scope with the design.

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Lint (app) | `ruff check app` | 0 | clean |
| Full suite (SQLite) | `.venv/bin/pytest -q` | 0 | 846 passed |
| Cross-engine (Postgres, py3.12) | `make test-docker` | 0 | 846 passed; agent store degrades to indexed InMemoryStore (stock image has no pgvector — caught) |
| pgvector positive proof | `pgvector/pgvector:pg17` + `scratchpad/verify_pgvec_store.py` | 0 | indexed PostgresStore engages (not degrade); semantic query + namespace isolation OK |

### Rollback

- `git revert <sha>` (reversible — store config + tool-signature change; no schema migration)

### Harness-Delta

- none
