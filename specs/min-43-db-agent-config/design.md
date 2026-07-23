---
slug: min-43-db-agent-config
status: proposed
owner: Minh Tran
created: 2026-07-01
linear: MIN-43
related: runtime-context-config (shipped), MIN-48 (dashboard UI, downstream)
---

# MIN-43 — DB-backed per-agent model config + remove `mode`

## 1. Motivation

Agent/model configuration is currently fixed from env at graph-build time
(`settings.agent_llm_configs`, resolved in `get_agent_llm`). We want that config to
live in the **DB, per agent/sub-agent, editable without a redeploy** (the editing UI
is a separate ticket, MIN-48). At the same time the per-turn **`mode`** feature
(fast/balanced/deep) is being removed — the model is now chosen by the DB config, not
by a user-selected mode.

## 2. Scope & non-goals

**In scope**
- New `agent_config` table + ORM model + Pydantic schema + repository.
- An in-process config cache with a `sync_from_cache` classmethod + a
  `reload_from_db(session_factory)` loader; loaded at lifespan startup.
- `get_agent_llm` resolves per-agent config from the cache, **per-field fallback** to
  env then global defaults.
- Alembic migration + idempotent seed of a default row for **every LLM node**.
- Remove the `mode` feature end-to-end (BE + FE).
- Tests: per-agent happy path, per-field fallback, no cross-agent leakage, cache
  reload after upsert, SQLite/Postgres parity, mode-removal regression.

**Non-goals**
- Editing UI / write endpoints — MIN-48. MIN-43 only exposes the repo + `reload_from_db`
  for MIN-48 to call after a write.
- Editor authz (who may change config) — deferred (no admin authz exists yet).
- Per-conversation / per-user config — config is **app-global** (one row per agent,
  shared across all users).
- `system_prompt` config — out of scope (lives in sub-agent prompt files today).
- Removing tier gating — **tier stays** (authz: free loses booking + RAG + quota).
- Storing `temperature` / other model knobs in the DB — those stay in env
  `AgentLLMConfig`; MIN-43 stores only `provider`, `model`, `base_url`.

## 3. Current state (grounding)

- `get_agent_llm(agent_name, model_hint)` (`app/clients/llm.py:99`) is the single choke
  point: reads `settings.agent_llm_configs.get(agent_name)` → `AgentLLMConfig{provider,
  model, temperature, +extra}`, falling back to global `llm_provider` / tier model
  (`FAST_AGENTS` decides fast vs main). `_build_chat_model` (`llm.py:38`) applies
  `settings.llm_base_url` **globally** when set.
- LLM nodes that call `get_agent_llm`: `supervisor`, `planner`, `concierge`, `journal`,
  `booking`, `budget`, `summarize`, `reflection`, `extract_memory` (9 nodes).
- Sub-agent nodes bind the model **per request** via `resolver_for(name)` in
  `graph.py:79` → `get_agent_llm(name, model=ctx_model)`, memoized per `ctx_model` in a
  closure cache for the compiled graph's life.
- `mode` footprint: `ChatMode`/`ModelHint`/`ResponseStyle` in `app/enums.py`;
  `DEFAULT_MODE: ChatMode` + `from app.enums import ChatMode` in `app/agents/constants.py`
  (`DEFAULT_TIER`/`Tier` stay — tier is kept); `_MODE_POLICY` +
  `resolve_agent_context(tier, mode)` in `app/agents/context.py`; `ChatRequest.mode` +
  validator in `app/schemas/agent.py`; `_resolve_context` in `app/routers/agent.py`
  (`def` at :136); ctx_model plumbing in `graph.py` (call at :106) + `subagents/_base.py`
  (`ctx.response_style` at :100–102, CONCISE/DETAILED prompt branches at :117–124).
  FE: `apps/web/src/components/chat/useAgentStream.ts` (`MODE_STORAGE_KEY`, read/write,
  `mode` state, `setMode`, request body) + the mode-selector UI + `schema.d.ts`.
- The graph is built once in `core/lifespan.py`; DB is seeded idempotently from
  `app/data/` on startup.

## 4. Chosen approach

**Layer the DB config as a per-field override inside `get_agent_llm`, backed by an
in-process cache loaded at startup.** `get_agent_llm` stays the single choke point.

Rejected alternatives:
- **Pass config through `AgentContext`/`context_schema`** (what the ticket text
  literally suggests). Rejected: the DB config is **app-global**, not per-run —
  threading app-wide config through the per-request `context` channel is the wrong
  altitude and would touch every node. The `context` channel remains for `tier`
  (genuinely per-run). This is a deliberate, recorded deviation from the ticket wording.
- **Read the repo every turn (no cache).** Rejected by the owner ("cache in config") and
  adds DB I/O to every turn (the ReAct assistant node re-resolves many times per turn).

## 5. Components

### 5.1 Data model — `agent_config`
- ORM `app/db/models/agent_config.py` → `models.AgentConfig`. Uses the project's
  UUID/timestamp base; `agent_name: str` carries a **unique** index (natural key).
- Columns: `agent_name` (unique, not null), `provider` (nullable), `model` (nullable),
  `base_url` (nullable), + `id`/`created_at`/`updated_at` from the base.
- Pydantic `app/schemas/agent_config.py` — `AgentConfig` (read) + a write shape for the
  repo upsert; extends `AppBaseModel`.

### 5.2 Repository — `app/repositories/agent_config.py`
- `AgentConfigRepository(session)` with `list_all() -> list[models.AgentConfig]`,
  `get(agent_name) -> models.AgentConfig | None`, `upsert(agent_name, *, provider, model,
  base_url) -> models.AgentConfig`. ORM only (layer discipline).

### 5.3 Config cache — `app/core/agent_config_cache.py`
- A module-level singleton holding `{agent_name: AgentModelOverride}` where
  `AgentModelOverride` is a small dataclass/model of `{provider, model, base_url}` (all
  optional).
- Interface:
  ```python
  class AgentConfigCache:
      _cache: dict[str, AgentModelOverride] = {}
      @classmethod
      def sync_from_cache(cls, cache: dict) -> None: ...   # replace the in-memory map
      @classmethod
      def get(cls, agent_name: str) -> AgentModelOverride | None: ...
      @classmethod
      def clear(cls) -> None: ...

  def reload_from_db(session_factory) -> None:  # repo.list_all() -> build map -> sync_from_cache
  ```
- Importable by `clients/llm.py` with no circular import (core-level, like `get_settings`).
- MIN-48 calls `reload_from_db(session_factory)` after a write to invalidate + repopulate.

### 5.4 Runtime resolution — `get_agent_llm`
Per-field fallback chain (DB → env → global default):
- `override = AgentConfigCache.get(agent_name)`; `env = settings.agent_llm_configs.get(agent_name)`.
- `provider = override.provider or env.provider or settings.llm_provider`
- `model    = override.model    or env.model    or (fast_llm_model if fast else llm_model)`
- `base_url = override.base_url or settings.llm_base_url`
- `temperature` / `extra` come from `env` only (not stored in DB in MIN-43).
- `_build_chat_model` gains a `base_url` parameter so `get_agent_llm` passes the
  resolved value instead of `_build_chat_model` reading the global setting directly.
  (The global-`base_url` behavior is preserved as the fallback.)
- **Signature change:** with `mode` gone there is no per-request model hint, so
  `get_agent_llm(agent_name)` **loses its `model: ModelHint | None` parameter**; the
  `ModelHint` import and the `FAST/DEEP` branches (`llm.py:122–125`) are removed. `FAST_AGENTS`
  still decides the fast-vs-main default when neither DB nor env sets `model`.

### 5.5 Migration + seed
- Alembic revision adds `agent_config`. Rollback: `alembic downgrade -1`.
- Idempotent seed (from `app/data/`, run in `db/seed.py`): one row per LLM node (the 9
  above) with `provider=model=base_url=NULL` → every agent still falls back to env, and
  MIN-48 has editable rows. Seeding is upsert-by-`agent_name` (safe to re-run).
- After migrating locally, rebuild `travel.db` (memory
  `stale-travel-db-breaks-suite-on-schema-change`).

### 5.6 Startup wiring — `core/lifespan.py`
- After DB seed and before serving, open an isolated session and call
  `reload_from_db(session_factory)` so the cache is populated before the first request. Bind an
  isolated sessionmaker (memory `sqlalchemy-str-url-masks-password`), not the request session.

### 5.7 Remove `mode` (BE)
- `app/enums.py`: remove `ChatMode` and `ModelHint`. **Keep `ResponseStyle`** — decision
  (2026-07-01): `AgentContext.response_style` stays a fixed `DEFAULT` constant to minimise test
  churn (removing the field would break every test constructing `AgentContext(response_style=...)`
  — research counts ~19 tool tests + context tests). The enum keeps its single consumer: the
  `AgentContext` field default.
- `app/agents/subagents/_base.py`: remove the now-dead `ctx.response_style` read (`:100–102`)
  and the unreachable `CONCISE`/`DETAILED` prompt-injection branches (`:117–124`) —
  `response_style` is always `DEFAULT` after mode removal, so these never fire. Also drop the
  `from app.enums import ResponseStyle` import (`:37`) since `_base.py` no longer references it
  (the enum still lives in `enums.py`, used by `context.py`).
- `app/agents/constants.py`: remove `DEFAULT_MODE` and the `ChatMode` import (keep
  `DEFAULT_TIER`/`Tier`); update the module docstring (`:1–11,17–18`), which still describes
  "(tier, mode) defaults" and references `ChatMode`. Prevents the ImportError when `ChatMode`
  leaves `enums.py`.
- `app/agents/context.py`: remove `mode`, `model` (ModelHint), and `_MODE_POLICY`. **Keep** the
  `response_style: ResponseStyle = ResponseStyle.DEFAULT` field (`:49`) and the `ResponseStyle`
  import (`:30`). `resolve_agent_context(*, tier)` returns tier-ceiling capabilities + fixed
  BALANCED defaults (`allow_reflection=True`, `allow_memory_write=True`, `allow_episodic=True`,
  `response_style=DEFAULT`, `max_revisions=1`). Free tier keeps `allow_rag=False` +
  `allowed_subagents` excluding `booking`; premium unrestricted. Also update the `context.py`
  module docstring (`:1–18`), which still describes the "**mode**" and the "(tier, mode) →
  capability mapping".
- `app/schemas/agent.py`: remove `mode` from `ChatRequest` + its validator.
- `app/routers/agent.py`: `_resolve_context(uid, authed, session)` drops the `mode` param.
- `app/agents/graph.py` + `subagents/_base.py`: drop the `ctx_model` hint plumbing — the
  model is chosen by `get_agent_llm(name)` from DB/env config, so `resolver_for` and the
  `assistant` node no longer read `ctx.model`. They still read `allow_rag` / `allow_episodic`
  from context.
- `app/agents/nodes.py`: reflection node keeps reading `allow_reflection` / `max_revisions`
  from context (now fixed defaults) — behavior equals today's BALANCED.

### 5.8 Remove `mode` (FE)
- `apps/web/src/components/chat/useAgentStream.ts`: remove `ChatMode` type (`:18`),
  `MODE_STORAGE_KEY` (`:15`), `readStoredMode`/`writeStoredMode` (`:20–30`), `mode` state
  (`:156`), `setMode` (`:158`), `mode` in all three request bodies (send `:282`, resume `:399`,
  retry `:499`) and the `mode` entries in the `useCallback` deps (`:382`,`:467`,`:584`).
- `apps/web/src/components/chat/ChatPanel.tsx`: remove the `ChatMode` import (`:12`), `MODES`
  array (`:34`), `mode`/`setMode` destructure (`:44`), the mode-selector `<select>` UI
  (`:75–91`), and the `modeLabel`/`modeFast|Balanced|Deep` i18n usages.
- Regenerate `schema.d.ts` via `pnpm gen:api` (openapi-typescript against the running BE on
  `:8000`) after the BE change — the `mode?` field (`schema.d.ts:1682`) drops out. FE
  `typecheck` must pass. (Chosen over hand-editing to stay on the codegen workflow.)

## 6. Data flow

```
startup (lifespan): seed DB -> reload_from_db(session_factory) -> AgentConfigCache._cache
request: router resolve_agent_context(tier) -> context (tier only)
node run: get_agent_llm(name) -> AgentConfigCache.get(name) (DB override)
                              -> settings.agent_llm_configs (env)  [per-field fallback]
                              -> global defaults
MIN-48 write (later): repo.upsert(...) -> reload_from_db(session_factory) -> cache refreshed
```

## 7. Error handling & edge cases
- **No row / NULL fields** → per-field fallback to env then defaults (never fails).
- **Unknown provider string in DB** → `_build_chat_model` / `init_chat_model` raises on
  first use; validate provider against `LLMProvider` on upsert (repo/schema) so bad data
  can't be written. Seed writes NULLs only.
- **Cache not yet loaded** (e.g. a test that skips lifespan) → `AgentConfigCache.get`
  returns `None` → env fallback → today's behavior. Existing graph tests inject fakes and
  never hit `get_agent_llm`, so they stay green.
- **Cross-agent isolation** → cache is keyed strictly by `agent_name`; `get` never falls
  through to another agent's row.
- **base_url** → per-agent override or global; empty/NULL preserves the global setting.

## 8. Testing
- Repo: `get` / `list_all` / `upsert` incl. provider validation; SQLite + Postgres parity.
- Cache: `sync_from_cache` replaces the map; `reload_from_db` reflects an upsert.
- `get_agent_llm`: DB override wins over env; per-field fallback (e.g. `provider` from DB,
  `model` from env); `base_url` override; agent A's row does not affect agent B.
- Mode removal: `ChatRequest` rejects/ignores `mode`; default run equals today's BALANCED
  behavior (reflection on, RAG per tier); free-tier gating unchanged; FE `typecheck` green.
- Migration applies clean; seed is idempotent (re-run adds no duplicate rows).

## 9. Risks / hard gates
- **Migration + new table** (Rule-4 data gate) — approved (ESCALATIONS E002). Rollback
  `alembic downgrade -1`; rebuild `travel.db` after.
- **Remove `mode`** — Rule-4 removal of existing, test-covered behavior + **public-contract**
  change (`mode` leaves `ChatRequest`) + **weakening-validation** (validator removed). Commit
  with `RISK_WARN_CATEGORIES="public-contract,weakening-validation"` (memories
  `public-contract-hard-gate`, `weakening-validation-gate-on-removed-assert`).
- **Model spend / provider mistakes via DB** — provider validated on write; NULL seed keeps
  env defaults, so a bad deploy can't silently change models.
- **Deviation from ticket** — global (per-agent-row) config, not per-conversation, and not via
  `context_schema`; recorded in SUMMARY.md.
