# Summary — runtime-context-config

- **Lane:** high-risk
- **Confidence:** high (mechanism clear; D1/D2/D4 resolved 2026-06-27)
- **Reason:** Adds user-selectable mode + per-user tier via LangGraph 1.0 `context_schema`.
  Touches a DB migration (new `users` table), an authorization boundary (tier), and quota
  (billing-adjacent). Design decisions locked; the migration (B.1) still passes the hard gate
  at commit time (rollback recorded), but no design sign-off remains outstanding.

## Rationale

This is the now-justified driver for the `Runtime`/`context` adoption from
`specs/travel-agent/RUNNABLE_CONFIG_RESEARCH.md`. mode/tier are per-run, constant,
agent-doesn't-write values → the `context` channel (not state, not `config["configurable"]`).
Sequenced **after** `specs/conversation-persistence/` per user decision.

## Decisions resolved (2026-06-27, see PLAN §4)

- **D1** model selection → **deferred in-node binding** (one graph; bind in node from context).
- **D2** tier storage → **add `users` table** (BE source of truth; needed for quota).
- **D4** quota → **in this plan**, simple per-day turn guard returning 429.

## Alternatives considered

- Trust client-supplied tier — rejected (forgeable; tier is an authz boundary).
- Move user_id/trip_id to context now — rejected (tools use InjectedState; out of scope).
- Per-request graph rebuild for model choice — rejected (slow; deferred binding instead).

## Rollback

- Migration (B.1 — revision `a1f3e2c9b7d5`): `cd apps/api && ../../.venv/bin/alembic downgrade -1`
- Code (B.1): `git revert <sha>` — reverts model, __init__, repository, migration file, router wire-up, and tests.

## Verify

| Check | Command | Exit | Notes |
|-------|---------|------|-------|
| Context resolver | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_agent_context.py -x` | — | plan stage |
| Alembic upgrade | `cd apps/api && DATABASE_URL="sqlite:///test_run.db" ../../.venv/bin/alembic upgrade head` | 0 | B.1 executed |
| Alembic round-trip | `cd apps/api && DATABASE_URL="sqlite:///test_run.db" ../../.venv/bin/alembic downgrade -1 && alembic upgrade head` | 0 | B.1 executed |
| User repo + agent tests | `cd apps/api && DATABASE_URL="sqlite:///test_run.db" ../../.venv/bin/python -m pytest tests/api/user/test_user_repo.py tests/api/agent -x -q` | 0 | 39 passed |
| Lint | `cd apps/api && ../../.venv/bin/ruff check app` | 0 | B.1 executed |
| FE typecheck | `cd apps/web && pnpm --filter web typecheck` (Node v24) | — | plan stage |

## Deviations

- Rule 3 — ruff-on-edit hook stripped `sqlite_insert` from `app/repositories/user.py` (added before use in a draft; final file is clean). Commit `TBD`.
- Rule 3 — ruff-on-edit stripped `UserRepository` import from `app/routers/agent.py` on first edit pass; re-added together with its usage site in one atomic edit.

## Notes

- `mode` added to ChatRequest = public-contract gate → commit with
  `RISK_WARN_CATEGORIES="public-contract"`.
