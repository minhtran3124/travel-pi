# min-43-db-agent-config — Summary

Lane: high-risk
Confidence: high
Reason: DB migration + new table + Rule-4 removal of `mode` keep the lane high-risk; all open questions resolved by the owner on 2026-07-01 (per-agent config rows, migration approved, in-process cache, fixed depth defaults + keep tier, remove mode), so direction is unambiguous — confidence raised to high.
Flags: data-model, existing-behavior (Rule-4 removal of `mode`), public-contract, authorization, audit/security
Affects: agent runtime config path (`clients/llm.py` get_agent_llm / `settings.agent_llm_configs`), `core/lifespan.py` graph build, `AgentContext` policy (`app/agents/context.py`), new DB table + migration
Input-type: change request

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

<!-- MIN-43, verbatim from the Linear ticket description. -->

> ## Goal
>
> Allow model/agent configuration to be **stored in the DB** and **loaded at runtime**, instead of only reading from env/static config at startup. This is the "Runtime State" piece of the `mode + tier` direction (see the specs/ notes on `context_schema` and LangGraph runtime config).
>
> **Must apply to the main agent AND all sub-agents** — not just the top-level graph. Each sub-agent should be able to resolve its own model/provider/tier config at runtime, not just inherit a single global setting.
>
> ## Context
>
> * LLM/agent configuration currently comes from env (`init_chat_model()`, `LLM_*`), fixed when the graph is built in `core/lifespan.py`.
> * We need a dynamic config layer: pick model/provider, tier, mode... changeable without a redeploy — for the main agent and every sub-agent in the graph.
> * Related: LangGraph 1.0's three-channel model (state / context / config) — the driver is mode/tier, not persistence.
>
> ## Proposed scope
>
> - [ ] Define a **config model** (table + ORM model in `app/db/models/`, Pydantic schema in `app/schemas/`) that supports per-agent keys (not just one global row)
> - [ ] Repository + service to read/write runtime config (respect the router → service → repository layering)
> - [ ] Enumerate all sub-agents currently in the graph and confirm each one is wired to read from this config
> - [ ] Load config from the DB at agent run time (via RunnableConfig/Runtime context_schema), with fallback to env when the DB has no value — fallback must work per sub-agent too
> - [ ] Seed/migration for the default config, including default rows for each sub-agent
> - [ ] Tests: happy path per agent, fallback when config is missing, SQLite/Postgres parity, and a test confirming sub-agent A's config doesn't leak into sub-agent B's run
>
> ## Open questions (resolve before implementing)
>
> * Config granularity: global / per-agent / per-conversation? → leaning per-agent (with global fallback), needs confirmation
> * Cache layer + invalidation on update?
> * Who is allowed to edit runtime config (no admin auth/authz yet)?
>
> > Ticket created from Claude Code — scope is a draft; brainstorm/plan before coding.

Owner clarifications in-session (2026-07-01), verbatim:

> 1. make agents config global, will config via the dashboard (in another ticket).
> 2. approved
> 3. cache in config
> ex:
> ```
>  @classmethod
>     def sync_from_cache(cls, cache: dict) -> None:
> ```

> update thêm là bỏ luôn feature mode (chế độ) hiện tại đi, user sẽ ko dc chọn nữa, clean both (FE+BE)

## What changed

**Shipped, all three phases** (see `PLAN.md` §7 Status Log for the full task-by-task record).
The task was classified `high-risk`, escalated at `low` confidence, and the owner resolved all
three escalations on 2026-07-01 (see `ESCALATIONS.md`). Resolved design for MIN-43:

- **Per-agent config rows** (one table, one row per agent/sub-agent), each holding **provider +
  model** for that agent. "Global" = app-wide scope (shared across users/conversations, edited
  via the MIN-48 dashboard), not a single row. Matches the ticket's "per-agent keys" wording.
- **New DB table + Alembic migration + default-row seed** (a default row per agent) — approved
  (data-model hard gate).
- **In-process cache** inside the config object, synced from the DB via a classmethod
  (`@classmethod def sync_from_cache(cls, cache: dict) -> None:`). Resolve per agent at runtime
  with **env fallback** when a row/value is absent.
- **Remove `mode` entirely (FE + BE).** After removal: model comes from the per-agent DB config;
  `allow_reflection`/`allow_rag`/`response_style`/`max_revisions` revert to today's BALANCED
  defaults; **tier gating stays** (authz). `resolve_agent_context` drops its `mode` arg.

**Added scope (owner, 2026-07-01): remove the `mode` feature entirely (FE + BE).** Users will
no longer pick a response mode (fast/balanced/deep). This is a Rule-4 removal of existing,
test-covered behavior and a public-contract change (`mode` leaves `ChatRequest`). Footprint:
BE — `app/enums.py` (`ChatMode`), `app/agents/context.py` (`_MODE_POLICY` +
`resolve_agent_context(tier, mode)`), `app/schemas/agent.py` (`ChatRequest.mode`),
`app/routers/agent.py`, `app/agents/graph.py`, `app/agents/subagents/_base.py`; FE —
`apps/web/src/components/chat/useAgentStream.ts` (selector, localStorage, request body) +
`schema.d.ts`. Open ripple (see `ESCALATIONS.md` E004): `mode` currently drives model hint +
`allow_reflection`/`allow_rag`/`response_style`/`max_revisions`; with `mode` gone, model comes
from the new global DB config, but the depth/style levers need a new source (fixed defaults vs
also DB-configured). Tier gating (authz) is assumed to stay unless decided otherwise.

### Rationale

DB migration + a new table is a data-model hard gate → `high-risk` regardless of flag count.
Confidence is `low` because the ticket ships with three unresolved open questions (granularity,
caching, editor authz) *and* materially overlaps the already-implemented `runtime-context-config`
work (`AgentContext` policy function + `agent_llm_configs` env config + `users` table) — two
engineers would build this differently depending on how it integrates with that existing layer.
Per the intake rule, low confidence escalates before work even though the lane's proof path is clear.

### Alternatives considered

- Proceed autonomously in high-risk lane without escalation — rejected: the intake ambiguity
  rubric fires (>1 materially different interpretation), so the human gate is on the uncertainty
  axis, not the risk axis.

### Deviations

See `PLAN.md` §7 Status Log for the full list (recon-corrected DELETE/REWRITE test classifications,
two Rule-1 auto-fixes in Task A.6/A.1, additional mode-kwarg test fixes discovered outside the
plan's original `<files>` sets). Summary: Task 0 recon found the plan's B.2 action wrongly slated
`test_depth_toggles.py` for deletion (it has zero `mode` references); corrected before B.1/B.2 ran.

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| BE suite (SQLite) | `cd apps/api && ../../.venv/bin/python -m pytest -q` | 0 | 1164 passed |
| BE suite (Postgres) | `cd apps/api && make test-docker` | 0 | 1164 passed, exact parity with SQLite |
| BE lint | `cd apps/api && ruff check app scripts` | 0 | clean |
| Migration reversibility | `alembic upgrade head && alembic downgrade -1 && alembic upgrade head` | 0 | single head, clean round-trip |
| FE test suite | `pnpm --filter web test` | 0 | 70 passed (vitest) |
| FE typecheck | `npx tsc --noEmit` (apps/web) | 0 | plan's named `pnpm --filter web typecheck` script doesn't exist |
| FE lint | `pnpm --filter web lint` | 0 | clean |

### Rollback

- Revert code: `git revert 63282d8 1cee9db a8fa157` (Phase C, then B, then A — B depends on A,
  C depends on B).
- Revert migration: `cd apps/api && ../../.venv/bin/alembic downgrade -1`, then rebuild `travel.db`.

### Harness-Delta

- none
