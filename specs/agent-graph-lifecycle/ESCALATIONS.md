# agent-graph-lifecycle — Escalations

Default: **deny-on-no-response**. No recorded decision → work stays blocked.

---

## E001

- raised_by: orchestrator
- date: 2026-06-26
- trigger: ambiguous-direction
- question: Does "use Postgres for the checkpoint, not SQLite" mean keep the DATABASE_URL engine-split (SQLite/memory local + tests, Postgres when configured) but fix the Postgres path to a once-built async saver — or make Postgres the checkpointer backend *always* and remove the SQLite path?
- context: C1 fix (build graph + checkpointer + store once in lifespan, share via app.state) — the backend scope determines whether the SQLite checkpointer path and zero-config tests stay or go.
- options:
  - A) Keep engine-split; Postgres path uses async `PostgresSaver` built once in lifespan; SQLite/memory stays for local + zero-config tests. (Design-consistent; smallest blast radius.)
  - B) Postgres-only checkpointer; remove the SQLite path. (Requires local Postgres; tests need a Postgres/memory fallback; larger blast radius.)
- default_if_no_response: BLOCK
- decision: **B (Postgres-only)** + migrate to **async** savers (AsyncPostgresSaver / AsyncPostgresStore). Remove the SQLite checkpointer path; keep a MemorySaver/InMemoryStore degrade so Postgres-less local/test runs still start (tests inject in-memory explicitly).
- decided_by: Minh Tran (user, via /feature-intake clarification)
- decided_at: 2026-06-26
