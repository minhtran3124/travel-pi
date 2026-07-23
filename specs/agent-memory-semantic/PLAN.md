---
slug: agent-memory-semantic
status: shipped
owner: Minh Tran
created: 2026-06-26
---

# Semantic memory index + tenant-safe user_id injection (REVIEW.md C3)

## 1. Motivation

`specs/travel-agent/REVIEW.md` **C3**: the long-term store was built with **no `index=`** config,
so `store.search(query=…)` silently ignored the query (degrading to recency), and the memory tools
took `user_id` as a **model-supplied** argument — a cross-user leakage risk since
`("users", user_id, "prefs")` is the isolation boundary.

## 2. Non-goals

- Migrating the store to async / `AsyncPostgresStore` — kept sync per the C1 decision.
- `ToolRuntime` injection (LangChain 1.x idiom, REVIEW.md L4).

## 3. Success criteria

- Both store backends carry a semantic `index` (embeddings); `query` search ranks by similarity.
- `user_id` comes from graph state (`InjectedState`), hidden from the model schema.
- `ruff` clean; SQLite + Postgres suites green; the indexed Postgres path positively verified.

## 4. Tasks (one wave; stacked on C1)

### Task 1.1 — Semantic index on the store

```xml
<task id="1.1">
  <files>app/memory/store.py, app/rag/embeddings.py</files>
  <action>Expose EMBED_DIM in embeddings.py. Add `_index_config()` (dims, embed=get_embeddings(), fields=["text"]) in store.py and pass `index=` to the PostgresStore and InMemoryStore (open_store both branches + get_store). Degrade to an indexed InMemoryStore when pgvector is absent.</action>
  <verify>.venv/bin/pytest tests/agents/test_memory.py -q</verify>
  <done>query search runs and stays namespace-isolated; degrade path still starts.</done>
</task>
```

### Task 1.2 — Inject user_id from state

```xml
<task id="1.2">
  <files>app/tools/memory_tools.py, tests/tools/test_tool_registry.py</files>
  <action>Inject user_id via Annotated[str, InjectedState("user_id")] (hidden from schema) instead of a model arg. Update the registry test to assert user_id is NOT in the model-visible args.</action>
  <verify>.venv/bin/pytest tests/tools/test_tool_registry.py tests/mcp/test_mcp_server.py -q</verify>
  <done>save_user_preference.args excludes store + user_id; MCP still skips the tool.</done>
</task>
```

### Task 1.3 — End-to-end injection + semantic tests

```xml
<task id="1.3">
  <files>tests/agents/test_memory.py</files>
  <action>Add a semantic-query test (query runs, isolation holds) and an end-to-end test: a journal sub-agent (fast LLM) calls save_user_preference with NO user_id in the tool args, and the pref lands under state["user_id"].</action>
  <verify>.venv/bin/pytest tests/agents/test_memory.py -q</verify>
  <done>Both pass; pref saved under state user_id, nothing leaks to another namespace.</done>
</task>
```

## 5. Risks

- pgvector absent on the stock Postgres test image → indexed `PostgresStore` setup fails. Mitigated:
  `open_store` catches it and degrades to an indexed `InMemoryStore`; the real pgvector path is
  verified separately against `pgvector/pgvector:pg17`.

## 6. Status Log

- 2026-06-26 — implemented + verified. ruff clean; `pytest -q` 846 passed (SQLite); `make test-docker`
  846 passed (Postgres/py3.12, degrade path); pgvector positive proof PASS. Branch
  `fix/agent-memory-semantic` **stacked on `fix/agent-graph-lifecycle` (C1 / PR #24)**.
