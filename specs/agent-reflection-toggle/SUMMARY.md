---
slug: agent-reflection-toggle
lane: high-risk
confidence: medium
status: intake
owner: Minh Tran
created: 2026-07-04
---

# Agent Reflection Toggle — Intake

## Intake statement

```text
Lane: high-risk
Confidence: medium
Reason: additive DB migration (agent_config gains a boolean) trips the data-model/migration hard gate; also changes existing test-covered reflection behavior. Scope is small — the allow_reflection seam already exists.
Flags: data-model (migration), existing-behavior, public-contract (additive config field)
Affects: agent_config table + schema, resolve_agent_context (AgentContext.allow_reflection), dashboard agent-config UI (MIN-48)
Input-type: change request
Route: high-risk chain (confirm approach first) → /writing-plans → /using-git-worktrees → /subagent-driven-development
Escalate: yes (migration hard gate needs ack + genuine design fork on where the flag lives / how broad the toggle is)
```

## Intent

User request, verbatim (via `/feature-intake`):

> configuration agent reflectionc can turn on/off via db config

Interpretation (one sentence): let the agent's **reflection** step be turned on/off through
the DB-backed agent configuration, driving the already-existing `AgentContext.allow_reflection`
flag instead of the current hardcoded `True`.

## Why this is not tiny (what the intake found)

- The toggle **plumbing already exists**: `make_reflection_node` reads
  `runtime.context.allow_reflection` and short-circuits to `END` when it is `False`
  (`app/agents/nodes.py:124-129`). `tests/agents/test_depth_toggles.py` already exercises this.
- What is missing is a **DB source** for that flag: `resolve_agent_context()`
  (`app/agents/context.py:79`) hardcodes `allow_reflection=True`, and the `agent_config`
  table (`app/db/models/agent_config.py`) has **no boolean field** — only provider/model/
  temperature/max_tokens. "via db config" therefore implies a small additive schema change.
- `AgentConfigCache` + generation-based graph rebuild (MIN-47) already propagate agent_config
  changes, so a config-driven flag will take effect without new refresh machinery.

## Design fork — RESOLVED (2026-07-04)

Confirmed with user (see `ESCALATIONS.md` ESC-1):

- **Storage → Option A:** add nullable `enabled` boolean to `agent_config`; gate **reflection
  only** via the existing `allow_reflection`. Smallest additive migration.
- **Dashboard UI → yes now:** expose the toggle as a checkbox in the MIN-48 config UI.

Confidence is now effectively `high` for direction; lane stays `high-risk` only for the
migration hard gate (narrowed to one nullable column). Ready for `/writing-plans`.

## Rationale

- Lane `high-risk`: adding a column to `agent_config` is a migration (hard gate). The migration
  is additive/nullable/reversible and the behavior seam is pre-tested, so real blast radius is
  small — a human may narrow scope to `normal`.
- Confidence `medium`: intent is unambiguous; the storage/breadth approach is not.

## Alternatives considered (at intake)

- Toggle graph topology in `build_graph` (wire sub-agents → END vs → reflection). Rejected as
  redundant: the `allow_reflection` short-circuit already achieves this without touching topology.
- Env/settings flag (no DB). Rejected: user explicitly asked for "db config".

### Verify

| Check | Command | Exit | Notes |
|---|---|---|---|
| Lint | `ruff check app scripts` | 0 | clean (4 pre-existing format-drift files untouched, none mine) |
| Migration (SQLite+Postgres) | `alembic upgrade head` | 0 | single head `d2f4b6a8c0e1`; applied on dev Postgres |
| Full suite (temp SQLite) | `pytest -q` | 0* | 1258 passed; *6 pre-existing env failures (5 OPENAI_API_KEY/ORS, confirmed failing on baseline `3cf7603`) — none from this change |
| Docker Postgres parity | `make test-docker` | 0 | full suite green on Postgres |
| Correctness gate | adversarial `/correctness-review` (opus, whole diff) | — | 3 findings → fixed → re-review ✅ 0 bugs |

> Local `travel.db` (SQLite convenience file, gitignored) is stale (pre-migration) and lacks the
> `enabled` column; the pytest suite uses isolated temp DBs so it is unaffected, but a local run
> pinned at `sqlite:///travel.db` needs `rm travel.db` + reseed (or `alembic upgrade head` against
> it). Per [[stale-travel-db-breaks-suite-on-schema-change]].

### Deviations

- Rule 1 — Fixed `test_identity_hybrid.py` tier spy, which hard-coded the pre-feature
  `resolve_agent_context(*, tier)` signature; Task 4 added the `allow_reflection` kwarg, so the
  spy now forwards it (asserts unchanged). `tests/api/agent/test_identity_hybrid.py`. Commit `83031c4`.
- Rule 1 — Adversarial correctness review found `upsert` wrote `enabled` unconditionally, so
  editing reflection's model via the list-page **modal** (the real edit UI), a CLI reseed, or any
  non-reflection save silently reverted an explicit disable (P1) and caused spurious graph
  rebuilds (P3×2). Fixed with preserve-on-absent write semantics (repo `_UNSET` sentinel →
  service None-guard → router None-on-no-marker) and surfaced the toggle in the actual modal
  (reflection-only, `disabled` inputs elsewhere so they never submit).
  `app/repositories/agent_config.py`, `app/services/agent_config_service.py`,
  `app/routers/dashboard.py`, `app/templates/agent_config.html`. Commit `1c6faed`.
- Note — the `risk-corroboration.sh` hook flagged `auth` on commit `1c6faed` (false positive:
  `max_tokens`/`maxTokens` matches the "token" substring; no auth/JWT/permission change in the
  diff). Downgraded for that single commit with `RISK_WARN_CATEGORIES="auth"`.

### Review Findings

All correctness findings resolved (✅ with sha `1c6faed`); none deferred. Final adversarial
re-review: 🐛 0 bugs.

### Rollback

- Revert code: `git revert 1c6faed 83031c4 c52b4bc 2211ed9 dcc82f3 bf2eeb0 b0f1069 436d5e5`
  (or revert the whole branch merge commit).
- Revert migration: `cd apps/api && ../../.venv/bin/alembic downgrade -1` (drops the `enabled`
  column; additive + nullable, so no data loss on downgrade).
