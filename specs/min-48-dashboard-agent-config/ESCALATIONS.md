# min-48-dashboard-agent-config — Escalations

> Deny-on-no-response: with no recorded decision below, the work stays BLOCKED.

## Resolutions (owner, 2026-07-02) — all cleared, work UNBLOCKED

- **E1 → Option A**: defer system-prompt editing to MIN-45. No prompt column / no YAML writer.
- **E2 → Option A**: no auth (project posture). `last-updated-by` dropped.
- **E3 → per-agent**: one config row per agent (main + each sub-agent).

## E1 — System-prompt storage/editing path (scope-deciding)

**Trigger:** Ambiguous direction (>1 materially different build) + issue open question.

**Problem:** The issue asks to edit "system prompt" via the form, but the MIN-43 `AgentConfig`
model has no prompt field. System prompts currently live in `app/prompts/active.yaml`. MIN-45
(the intended prompt version manager) is **not built yet**, so "reuse MIN-45 versioning" has no
target to reuse. Three materially different builds:

- **(A) Defer prompt editing** — this ticket edits provider/model/base_url/temperature/max_tokens/
  tier only; system-prompt editing waits for MIN-45. No schema change. *(recommended — smallest,
  unblocks the config UI, keeps prompt storage aligned with MIN-45's future design.)*
- **(B) New `system_prompt` DB column** on `AgentConfig` + Alembic migration. Self-contained but
  forks prompt storage away from MIN-45 (the issue explicitly warns against duplicating a prompt path).
- **(C) YAML writer** — form writes back to `app/prompts/active.yaml`. No schema change, but no
  versioning and bypasses the DB/cache config model.

**Decision:** RESOLVED 2026-07-02 — see per-item resolution above the divider.

## E2 — Auth/authz posture for the dashboard write endpoint

**Trigger:** Public-contract hard gate (first write route on `/dashboard/*`) + issue open question.

**Problem:** Project convention is "No auth" and dashboards are `include_in_schema=False`,
human-facing. This ticket adds the first **mutating** dashboard route, which can repoint the
agent at any provider/model/base_url. Options:

- **(A) No auth now** — consistent with current project posture and MIN-43's deferral; note the
  gap and revisit when admin auth lands. *(recommended for parity with the rest of the app.)*
- **(B) Minimal guard** — e.g. shared-secret / env-gated write, small but introduces an auth
  pattern the rest of the app doesn't have.

**Decision:** RESOLVED 2026-07-02 — see per-item resolution above the divider.

## E3 — Per-agent vs global editing surface (confirm)

MIN-43 owner note said "make agents config global, will config via the dashboard (in another
ticket)" — but MIN-48's scope asks for **per-agent** editing. The repository already supports
per-agent rows (`agent_name` unique). Confirm the form should expose **one row per agent**
(main + each sub-agent) vs a single global row.

**Decision:** RESOLVED 2026-07-02 — see per-item resolution above the divider.
