---
slug: local-postgres-checkpointer
category: agent
module: agent/checkpointer
tags: checkpointer, langgraph, postgres, memory-saver, conversation-persistence, uvicorn-reload
type: knowledge
confidence: high
confirmed_at: 2026-06-27
---

# Local Postgres Checkpointer — Durable Agent Memory

## Problem

The agent loses all conversation context on every process restart. In local dev,
`uvicorn --reload` restarts the process on every file save, so the graph state is
wiped constantly. This means:

- The agent cannot remember anything said earlier in the same conversation after a reload.
- Any in-progress multi-turn flow (planner interrupt, booking confirmation) is lost.

## Root cause

`app/agents/checkpointer.py` selects the backend at startup:

- `DATABASE_URL` starts with `postgres` → `AsyncPostgresSaver` (durable, table-backed)
- Anything else (including the default `sqlite:///travel.db`) → `MemorySaver` (in-process, ephemeral)

The default config uses SQLite, so local dev silently degrades to the ephemeral path.

## Fix

Point `DATABASE_URL` at a local Postgres instance. The selection logic in
`open_checkpointer()` (`checkpointer.py:46`) handles the rest — it calls
`AsyncPostgresSaver.from_conn_string()` + `await saver.setup()` automatically.

In `apps/api/.env` (or override in shell):

```
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/travel?sslmode=disable
```

Bring up a local Postgres quickly with Docker:

```bash
docker run -d --name travel-pg \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=travel \
  -p 5432:5432 \
  postgres:16
```

Then run the Alembic migrations and seed:

```bash
cd apps/api
../../.venv/bin/alembic upgrade head
make seed
```

## Fallback behaviour (acceptable for stateless dev)

If no Postgres is available, the app starts fine with `MemorySaver`. All features
work within a single process run; conversation context is lost on restart. This is
documented in `.env.example`.

## Verification

```bash
cd apps/api
../../.venv/bin/python -m pytest tests/agents/test_checkpointer_selection.py -xvs
```

Three tests confirm the routing without requiring a live database.
