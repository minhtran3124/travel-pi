# Escalations — agent-reflection-toggle

Deny-on-no-response: work stays blocked until a decision is recorded here.

## ESC-1 — Confirm storage approach + migration (hard gate: data migration)

**Raised:** 2026-07-04 at intake.
**Blocking:** yes (migration hard gate + design fork).

### Context

The reflection on/off behavior already flows through `AgentContext.allow_reflection`
(pre-tested). The only new work is a DB source for that flag. The `agent_config` table has no
boolean field, so "db config" needs an additive schema change. How broad the toggle is, is a
real design fork.

### Decision needed

1. **Where the flag lives / breadth** — one of:
   - **A (recommended):** add nullable `enabled` boolean to `agent_config`; gate **reflection
     only** by reading the `reflection` row's `enabled` in `resolve_agent_context`. Smallest diff.
   - **B:** add generic `enabled` to `agent_config` so **any support agent** (summarize /
     reflection / extract_memory) can be toggled. Same migration, broader behavior + tests.
   - **C:** separate feature-flag/settings table; keep `agent_config` LLM-only.
2. **Dashboard UI** — expose the toggle as a checkbox in the MIN-48 config UI now, or defer and
   edit via seed/SQL only?

### Decision

Resolved by user (2026-07-04):

1. **Storage/breadth → Option A.** Add nullable `enabled` boolean to `agent_config`; gate
   **reflection only** by reading the `reflection` row's `enabled` in `resolve_agent_context`
   → drives the existing `allow_reflection`. Smallest additive migration; the migration hard
   gate is narrowed to a single nullable column.
2. **Dashboard UI → add the checkbox now.** Expose the toggle in the MIN-48 config UI so it's
   editable through the dashboard (true "db config via UI").

Status: **unblocked** — proceed to `/writing-plans`.
