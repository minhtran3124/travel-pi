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

_(to be filled by the executing plan)_

### Rollback

_(to be filled once the approach + migration are chosen; will include `alembic downgrade -1`
and `git revert <sha>`)_
