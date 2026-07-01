# min-43-db-agent-config — Escalations

Default: **deny-on-no-response**. No recorded decision → work stays blocked.

---

## E001

- raised_by: orchestrator
- date: 2026-07-01
- trigger: ambiguous-direction
- question: What is the config granularity and how does the new DB config layer relate to the already-shipped `runtime-context-config` layer (`AgentContext` policy + `agent_llm_configs` env + `users` table)?
- context: Blocks all of MIN-43 — the table shape, repository, and runtime-load path all depend on this answer.
- options:
  - A) **Per-agent rows with global fallback**, DB overrides env `agent_llm_configs`; the config feeds `get_agent_llm(name, model=...)` deferred binding already added in `runtime-context-config`. Consequence: cleanest fit with existing code; one new table `agent_config(agent_name, model, provider, tier, system_prompt, ...)`.
  - B) **Global single-row config** only. Consequence: simpler, but the ticket explicitly requires per-sub-agent config and per-agent fallback — likely under-delivers.
  - C) **Per-conversation config**. Consequence: much larger scope (ties config to conversation state); probably out of scope for MIN-43.
- default_if_no_response: BLOCK
- decision: **PER-AGENT rows** (clarified 2026-07-01) — one table, one row per agent/sub-agent, each row holding that agent's config (provider + model). "Global" meant app-wide scope (shared across users/conversations, edited via the MIN-48 dashboard), NOT a single row. This matches the ticket's original "per-agent keys" wording. Config resolution: per-agent row → fallback to env when a row/value is absent.
- decided_by: Minh Tran
- decided_at: 2026-07-01

## E002

- raised_by: orchestrator
- date: 2026-07-01
- trigger: hard-gate
- question: Approve the data-model hard gate — a new `agent_config` table + Alembic migration + default-row seed?
- context: MIN-43 cannot store runtime config without a new table; this is the Rule-4 migration gate.
- options:
  - A) Approve; migration proceeds with rollback recorded (`alembic downgrade -1`) and `travel.db` rebuilt after (per memory `stale-travel-db-breaks-suite-on-schema-change`).
  - B) Reject the new table; store config as JSON on an existing table or in settings — narrower blast radius but weaker query/edit story (and MIN-48's UI needs a real table to write to).
- decision: **APPROVED** (Option A) — new table + Alembic migration + default-row seed; rollback `alembic downgrade -1`, rebuild `travel.db` after.
- decided_by: Minh Tran
- decided_at: 2026-07-01

## E003

- raised_by: orchestrator
- date: 2026-07-01
- trigger: ambiguous-direction
- question: Cache layer + invalidation, and who may edit runtime config (no admin authz exists yet)?
- context: Ticket open questions; affect whether a cache/invalidation path and any authz guard are in MIN-43's scope or deferred (MIN-48 adds the editing UI).
- options:
  - A) Defer both — read from DB per run with env fallback, no cache, no editor authz in MIN-43; caching + authz become follow-ups (edit path lands in MIN-48).
  - B) Include a simple in-process cache with invalidate-on-write in MIN-43.
- decision: **CACHE IN MIN-43** (Option B) — config object holds an in-process cache, kept in sync from the DB via a classmethod, e.g. `@classmethod def sync_from_cache(cls, cache: dict) -> None:`. Editor authz deferred (edit path lands in MIN-48).
- decided_by: Minh Tran
- decided_at: 2026-07-01

## E004

- raised_by: orchestrator
- date: 2026-07-01
- trigger: ambiguous-direction
- question: Removing `mode` deletes the per-turn driver of model hint + `allow_reflection` / `allow_rag` / `response_style` / `max_revisions` (`_MODE_POLICY`). What replaces those levers, and does tier gating stay?
- context: Blocks the mode-removal task — determines what `AgentContext`/`resolve_agent_context` become and whether depth/style are fixed or DB-configured.
- options:
  - A) **Fixed defaults + keep tier.** Model comes from the new global DB config; reflection/RAG/response_style/max_revisions revert to today's BALANCED defaults; `tier` gating (authz: free loses booking/RAG, quota) stays. `resolve_agent_context` loses its `mode` arg. Smallest, safest.
  - B) **Fold depth/style into the global DB config too.** Reflection/RAG/response_style/max_revisions become DB-configured global fields (dashboard-editable in MIN-48), not just model. Bigger config surface.
  - C) **Remove tier gating as well.** If mode goes and there's no premium tier story, strip tier too. Largest removal — confirm before doing (extra Rule-4 + authz gate).
- default_if_no_response: BLOCK
- decision: **Option A** (2026-07-01) — model comes from the per-agent DB config; reflection/RAG/response_style/max_revisions revert to today's BALANCED defaults; **tier gating stays** (authz: free loses booking/RAG + quota). `resolve_agent_context` drops its `mode` arg.
- decided_by: Minh Tran
- decided_at: 2026-07-01
