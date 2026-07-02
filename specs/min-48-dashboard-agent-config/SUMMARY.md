# min-48-dashboard-agent-config — Summary

Lane: high-risk
Confidence: high
Reason: high-risk holds on hard gates — first write (POST) endpoint on the dashboard (public contract) + provider/model/base_url editing that reconfigures the real LLM (external provider). All three scope forks resolved by owner on 2026-07-02 (defer system-prompt to MIN-45, no auth, per-agent editing), so direction is unambiguous → confidence high, proceed autonomously in the high-risk lane. No migration needed (see below).
Flags: external-systems, public-contract, existing-behavior, data-model (write path only — no schema change)
Affects: `app/routers/dashboard.py` (first write route), `app/repositories/agent_config.py` (MIN-43), `app/core/agent_config_cache.py` (MIN-47 cache invalidation on save), agent runtime config path (`clients/llm.py`, `core/lifespan.py` graph rebuild). NOT touched: schema/migration (no new columns), `app/prompts/active.yaml` (system-prompt deferred to MIN-45).
Input-type: spec slice
Route: high-risk full chain — brainstorming → xia2 → writing-plans → using-git-worktrees → subagent-driven-development. UNBLOCKED (forks resolved); notify-and-proceed. Commit note: public-contract gate needs `RISK_WARN_CATEGORIES="public-contract"` to authorize the new write endpoint.
Escalate: no (all three escalations resolved — see ESCALATIONS.md)

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

<!-- MIN-48, verbatim from the Linear ticket description. -->

> ## Goal
>
> Build a BE dashboard page that lets users configure LLM/agent settings (model, provider, system prompt, tier/mode, etc.) through a UI, and persist changes to the DB.
>
> ## Context
>
> * Follows the same server-rendered dashboard pattern already used for `GET /dashboard/hotels` (see `app/routers/dashboard.py`).
> * Depends on the config model/runtime-state work in MIN-43 (config stored in DB, loaded at runtime) and its caching sub-task MIN-47 (~1hr cache) — this dashboard is the UI on top of that config model.
> * Related to MIN-45 (prompt version manager dashboard) — system prompt editing here should reuse/align with that versioning approach rather than duplicating a separate prompt storage path.
>
> ## Proposed scope
>
> - [ ] Dashboard page (server-rendered, consistent with existing `/dashboard/*` pattern) listing current agent/model config
> - [ ] Form to edit: model, provider, tier/mode, system prompt, and other fields defined by the MIN-43 config model
> - [ ] Support per-agent config editing (main agent + each sub-agent), not just one global config
> - [ ] Write endpoint: validate input, persist to DB via the MIN-43 config repository/service (router → service → repository layering)
> - [ ] Show current values pulled from DB (respecting the MIN-47 cache — trigger cache invalidation on save)
> - [ ] Basic safeguards: confirm-before-save for destructive changes, show last-updated-by/at
> - [ ] Tests: form validation, write path, per-agent isolation (editing agent A doesn't affect agent B)
>
> ## Open questions
>
> * Auth/authz for who can access and edit this dashboard (no admin auth yet — same open question as MIN-43)
> * Should system prompt editing here link directly into the MIN-45 prompt version manager instead of a separate free-text field?
>
> ## Notes
>
> Depends on MIN-43 / MIN-47. Coordinate with MIN-45 for prompt editing UX.

### Dependency state (verified at intake, 2026-07-02)

- **MIN-43 ✅ merged** (PR #50). Present: `db/models/agent_config.py` (`AgentConfig`: `agent_name` unique, `provider`, `model`, `base_url`, `temperature`, `max_tokens` — **no `system_prompt`, no audit columns**), `repositories/agent_config.py` (`list_all` / `get` / `upsert`, validates `provider` against `PROVIDER_NAMES`), `schemas/agent_config.py`, `data/agent_config.py`. **No service layer** for agent config yet — issue asks router→service→repo, so a service must be added.
- **MIN-47 ✅ merged** (PR #52). `core/agent_config_cache.py` — TTL ~1h + graph rebuild. Save path must invalidate this.
- **MIN-45 ⛔ not built.** Only `app/prompts/active.yaml` exists — no PromptVersion model / router / diff dashboard. So "reuse MIN-45 versioning" has nothing to reuse yet.
- Every existing `/dashboard/*` route is **GET-only**; MIN-48 introduces the first write (POST) route on the dashboard.

### Owner decisions (2026-07-02, resolves all escalations)

1. **System prompt → defer to MIN-45.** This ticket edits `provider` / `model` / `base_url` /
   `temperature` / `max_tokens` / tier only. No `system_prompt` column, no YAML writer.
2. **Auth → none** (project posture; `include_in_schema=False`). `last-updated-by` dropped
   (no user identity source).
3. **Editing surface → per-agent** (one row per agent; repo already keys on `agent_name` unique).

Consequence: **no Alembic migration** — `AgentConfig` inherits `UUIDBase` → `created_at`/`updated_at`
(with `onupdate`) already exist, covering the "last-updated-at" ask. Scope is now: GET config-list
page + POST write route (→ new service → existing repo) + MIN-47 cache invalidation on save +
per-agent isolation tests. No schema change.

### Rationale

Config data-layer (model + repo + cache) already exists from MIN-43/47, so the mechanical write path is small. The risk and ambiguity are concentrated in the **system-prompt** field: it has no home in the current schema and its intended owner (MIN-45) does not exist yet — the chosen answer changes whether this ticket needs a migration, a YAML writer, or a stub. Confirming that fork (and the auth posture) up front avoids building the wrong storage path.

### Alternatives

- Ship provider/model/tier editing now and **defer system-prompt editing** to when MIN-45 lands (smallest, unblocks the config UI without a schema decision).
- Add a `system_prompt` column to `AgentConfig` + migration (self-contained, but forks prompt storage away from MIN-45's future version manager — the issue warns against this).
- Write system prompt back into `app/prompts/active.yaml` (no schema change, but bypasses DB/cache model and has no versioning).

### Deviations (planned — from design/plan)

- **Rule 2 — `from app.data.agent_config import AGENT_CONFIG_NODES` in `AgentConfigService`**, the
  first `app/data` import outside `app/db/seed.py`. Accepted at plan time: it is a plain constant
  (no seed coupling); lifting it to `core/` is more blast for no benefit. `app/services/agent_config_service.py`.
- **Rule 3 — pin `python-multipart>=0.0.7,<0.1`** in `apps/api/requirements.txt` (needed for
  FastAPI `Form(...)`; currently only transitively present).

### Verify

| Check | Command | Exit | Notes |
|---|---|---|---|
| Service unit tests | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config/test_agent_config_service.py -x` | _pending_ | validation, base_url=None, isolation, cache |
| Dashboard HTTP tests | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config/test_agent_config_dashboard.py -x` | _pending_ | list/edit/POST 303/400/404 |
| Cache method | `cd apps/api && ../../.venv/bin/python -m pytest tests/core/test_agent_config_cache.py -x` | _pending_ | invalidate() |
| Lint | `cd apps/api && ruff check app` | _pending_ | new files clean |

### Rollback

- Revert each task commit: `git revert <sha>` (no migration to undo).
- Remove the `python-multipart` line from `apps/api/requirements.txt` if the dep must be reverted.
