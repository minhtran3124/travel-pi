# Summary — conversation-persistence

- **Lane:** normal
- **Confidence:** high
- **Reason:** Root cause precisely located (FE uses only `/agent/stream`, which never persists;
  checkpointer degrades to ephemeral MemorySaver on non-Postgres; FE keeps `conversationId`
  only in-memory). Data model + repo methods already exist — this is wiring, no schema change,
  reversible. One hard gate: new public read endpoints (Task 2.1).

## Rationale

The fix is persistence wiring, **not** the LangGraph `Runtime`/`context` refactor from
`specs/travel-agent/RUNNABLE_CONFIG_RESEARCH.md`. That refactor is orthogonal and fixes none of
the three reported bugs. Chosen continuity approach: durable **Postgres checkpointer locally**
(user decision, verified against the official LangGraph checkpointers doc).

## Alternatives considered

- *Do the RunnableConfig/Runtime refactor* — rejected: does not address persistence; wide blast
  radius across `agents/` + `tools/` for no user-visible win.
- *SQLite checkpointer for local* — rejected by user in favour of local Postgres parity.
- *Force Postgres-only (drop MemorySaver fallback)* — rejected: keeps dev friction high.

## Verify

| Check | Command | Exit | Notes |
|-------|---------|------|-------|
| Stream persistence | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_stream_persistence.py -x` | — | not yet run (plan stage) |
| Checkpointer selection | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_checkpointer_selection.py -x` | — | not yet run |
| History endpoints | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_agent_history.py -x` | — | not yet run |
| FE typecheck | `cd apps/web && pnpm --filter web typecheck` (Node v24) | — | not yet run |

## Rollback

- Revert code: `git revert <sha>` per task (all reversible; no migration).
- Checkpointer: set `DATABASE_URL` back to `sqlite:///travel.db` to return to prior behaviour.

## Notes

- Commit authorization for Task 2.1: `RISK_WARN_CATEGORIES="public-contract"` (memory
  `public-contract-hard-gate`).
