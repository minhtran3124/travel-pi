---
slug: min-43-db-agent-config
status: active
owner: Minh Tran
created: 2026-07-01
linear: MIN-43
---

# DB-backed per-agent model config + remove `mode` — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans (or subagent-driven-development) to implement this plan task-by-task.

**Goal:** Move per-agent model config (`provider`/`model`/`base_url`) into the DB, resolved at
runtime through an in-process cache with per-field env fallback, and remove the `mode` feature
end-to-end (FE + BE).

**Architecture:** Additive DB config layer clips onto the single model-resolution choke point
`get_agent_llm` (Phase A ships independently, `mode` still present). Then `mode` is removed as a
coordinated deletion (Phase B/C). Config is app-global (one row per agent), loaded once at
lifespan startup and reloadable via `reload_from_db` (MIN-48 calls it after a write).

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (`UUIDBase`), Alembic, Pydantic v2 (`AppBaseModel`),
LangGraph 1.0, Next.js (openapi-typescript codegen).

**Source artifacts:** `specs/min-43-db-agent-config/design.md`, `research-brief.md`,
`SUMMARY.md`, `ESCALATIONS.md`.

---

## 1. Motivation

LLM/agent config is fixed from env at graph-build time (`settings.agent_llm_configs`, resolved in
`get_agent_llm`). MIN-43 makes it DB-backed + editable without redeploy (edit UI = MIN-48), and
removes the per-turn `mode` selector (model now comes from the DB config, not from `mode`).

## 2. Non-goals

- Editing UI / write endpoints (MIN-48). MIN-43 exposes only the repo + `reload_from_db`.
- Editor authz; per-conversation/per-user config; storing `temperature`/`system_prompt` in DB.
- Removing tier gating — **tier stays** (free loses booking + RAG + quota).

## 3. Success Criteria

- A DB row overrides an agent's `provider`/`model`/`base_url` without redeploy; per-field fallback
  to env then global default; cache reloadable via `reload_from_db`.
- Seed creates one NULL row per LLM node (idempotent); SQLite + Postgres parity.
- `mode` no longer exists anywhere (BE + FE); default agent behavior equals today's BALANCED;
  existing chats unaffected.
- Full test suite green on SQLite and via `make test-docker`.

## 4. Tasks

> **Global gotchas** (apply to every task): run BE commands from `apps/api/`; venv at
> `../../.venv`; after any schema change rebuild `travel.db` (memory
> `stale-travel-db-breaks-suite-on-schema-change`); the `ruff-on-edit` hook strips imports added
> before use — add import + usage together (memory `ruff-on-edit-strips-unused-imports`);
> `apps/api/.env` `OPENAI_API_KEY=test` breaks ~14 LLM/RAG tests locally — move `.env` aside for a
> green run (memory `env-openai-key-test-breaks-llm-tests`).

### Task 0 — Recon: exact `response_style` / mode test blast radius

```xml
<task id="0.1" wave="0">
  <files>specs/min-43-db-agent-config/PLAN.md</files>
  <action>Discovery only (no code change). From apps/api, grep the exact consumer set that Phase B must touch, and record the file list in this task's Status Log entry so B.1/B.2 edit precisely:
    grep -rn "response_style\|ResponseStyle" app/ tests/ ;
    grep -rn "ChatMode\|ModelHint\|_MODE_POLICY\|DEFAULT_MODE" app/ tests/ ;
    grep -rn "resolve_agent_context\|body.mode\|\.mode\b\|mode=" app/ tests/ .
    Classify each test file as DELETE (mode-only: test_mode_context, test_depth_toggles, test_deferred_model), REWRITE (drops mode arg but keeps tier/other: test_agent_context, test_tier_gating, test_context_episodic, test_context_memory_write), or CONSTRUCTS-AgentContext (tool tests — confirm whether they SET response_style or just default; since we KEEP response_style=DEFAULT, default-only constructors need NO change). Write the confirmed lists into §5 Status Log.</action>
  <verify>cd apps/api && grep -rln "ChatMode\|ModelHint\|response_style" app/ tests/ | sort | tee /tmp/min43_modefootprint.txt && test -s /tmp/min43_modefootprint.txt</verify>
  <done>The precise DELETE / REWRITE / NO-CHANGE test lists are recorded in §5 Status Log; B.1/B.2 reference them.</done>
</task>
```

---

### Phase A — DB config layer (additive; ships independently, `mode` untouched)

### Task A.1 — `AgentConfig` ORM model + registration + Pydantic schema

```xml
<task id="A.1" wave="1">
  <files>apps/api/app/db/models/agent_config.py, apps/api/app/db/models/__init__.py, apps/api/app/schemas/agent_config.py, apps/api/tests/db/test_agent_config_model.py</files>
  <action>Create models.AgentConfig(UUIDBase) mirroring app/db/models/trip.py: __tablename__="agent_config"; columns agent_name: Mapped[str] (not null), provider/model/base_url: Mapped[str | None] = mapped_column(default=None). Add a plain UNIQUE index on agent_name (Index("ix_agent_config_agent_name", "agent_name", unique=True)) — agent_name is NOT NULL, so no partial sqlite_where/postgresql_where is needed (unlike trip.py's nullable idempotency_key). Register in db/models/__init__.py (explicit import + add to __all__, keep alphabetical-ish grouping). Add app/schemas/agent_config.py: class AgentConfig(AppBaseModel) with agent_name: str, provider/model/base_url: str | None = None (extends AppBaseModel → from_attributes). Test: import the model, assert __tablename__ + that the unique index exists + that a schema round-trips from an ORM-like object.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/db/test_agent_config_model.py -x</verify>
  <done>AgentConfig model + unique index + schema exist and import cleanly; registered in models.__all__.</done>
</task>
```

### Task A.2 — `AgentConfigRepository` (get / list_all / upsert)

```xml
<task id="A.2" wave="2">
  <files>apps/api/app/repositories/agent_config.py, apps/api/tests/api/agent_config/test_agent_config_repo.py</files>
  <action>Create AgentConfigRepository(RepositoryBase) mirroring app/repositories/user.py (use _session()/_commit()). Methods: list_all() -> list[models.AgentConfig]; get(agent_name) -> models.AgentConfig | None (select by agent_name); upsert(agent_name, *, provider=None, model=None, base_url=None) -> models.AgentConfig (get-or-insert then set fields, self._commit). Validate provider against the LLMProvider values in app/core/config.py on upsert — raise ValueError (or the project's BadRequest) on an unknown provider so bad data can't be written. Test with the request-scoped session fixture: upsert inserts then updates the same row (no duplicate), get returns None when absent, invalid provider rejected. ORM only — no logic leaks up.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config/test_agent_config_repo.py -x</verify>
  <done>Repo get/list_all/upsert work idempotently; invalid provider rejected; SQLite green.</done>
</task>
```

### Task A.3 — Alembic migration for `agent_config`

```xml
<task id="A.3" wave="2">
  <files>apps/api/alembic/versions/xxxx_add_agent_config.py</files>
  <action>Generate a revision with down_revision = "a1f3e2c9b7d5" (the CURRENT head — confirm with `alembic heads` first; do NOT use c3e5a7b9d1f2, which is 4 revisions back and would create multiple heads). Copy the create-table shape from alembic/versions/0ab2cdadfc16_add_agent_tables_*.py: op.create_table("agent_config", id/created_at/updated_at columns matching UUIDBase, agent_name (String, nullable=False), provider/model/base_url (String, nullable=True)); create the UNIQUE index on agent_name (op.create_index(..., unique=True) — plain unique index; agent_name is NOT NULL so no partial sqlite_where/postgresql_where needed). downgrade() drops the index + table. Do NOT autogenerate blindly — hand-write to match the model. After writing, run upgrade + downgrade + upgrade to confirm reversibility, then rebuild travel.db.</action>
  <verify>cd apps/api && ../../.venv/bin/alembic upgrade head && ../../.venv/bin/alembic downgrade -1 && ../../.venv/bin/alembic upgrade head && test "$(../../.venv/bin/alembic heads | wc -l | tr -d ' ')" = "1"</verify>
  <done>Migration applies + reverses clean; single head; chain extends a1f3e2c9b7d5.</done>
</task>
```

### Task A.4 — Config cache (`sync_from_cache` + `reload_from_db`)

```xml
<task id="A.4" wave="3">
  <files>apps/api/app/core/agent_config_cache.py, apps/api/tests/core/test_agent_config_cache.py</files>
  <action>Create a core-level, import-safe singleton (no app.agents / app.clients imports → avoids cycles). Shape:

    from dataclasses import dataclass
    @dataclass(frozen=True)
    class AgentModelOverride:
        provider: str | None = None
        model: str | None = None
        base_url: str | None = None

    class AgentConfigCache:
        _cache: dict[str, AgentModelOverride] = {}
        @classmethod
        def sync_from_cache(cls, cache: dict[str, AgentModelOverride]) -> None:
            cls._cache = dict(cache)
        @classmethod
        def get(cls, agent_name: str) -> AgentModelOverride | None:
            return cls._cache.get(agent_name)
        @classmethod
        def clear(cls) -> None:
            cls._cache = {}

    def reload_from_db(session_factory) -> None:
        # opens a session via the factory (like seed_all), reads AgentConfigRepository.list_all(),
        # builds {agent_name: AgentModelOverride(provider, model, base_url)}, calls sync_from_cache.
    Test: sync_from_cache replaces the map; get returns None for unknown; reload_from_db reflects an upsert (seed a row via repo with an in-memory factory, reload, assert get() returns it); clear empties it.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/core/test_agent_config_cache.py -x</verify>
  <done>Cache replace/get/clear + reload_from_db(session_factory) verified against a real repo row.</done>
</task>
```

### Task A.5 — Seed one NULL row per LLM node (idempotent)

```xml
<task id="A.5" wave="3">
  <files>apps/api/app/data/agent_config.py, apps/api/app/db/seed.py, apps/api/tests/db/test_seed_agent_config.py</files>
  <action>Add app/data/agent_config.py exporting AGENT_CONFIG_NODES = the 9 LLM node names (supervisor, planner, concierge, journal, booking, budget, summarize, reflection, extract_memory) — single source of truth. In db/seed.py add seed_agent_config(session) using the NATURAL-KEY upsert pattern (City, seed.py:106): for each name, select AgentConfig by agent_name; if absent insert with provider/model/base_url = None (leave NULLs → env fallback). Call it inside seed_all before the final commit. Idempotent: re-running adds no duplicate rows. Test: run seed twice, assert exactly 9 rows and all NULL.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/db/test_seed_agent_config.py -x</verify>
  <done>Seeding yields 9 NULL rows; re-seed is a no-op (idempotent).</done>
</task>
```

### Task A.6 — `get_agent_llm` per-field DB fallback + `base_url` on `_build_chat_model`

```xml
<task id="A.6" wave="4">
  <files>apps/api/app/clients/llm.py, apps/api/tests/clients/test_get_agent_llm_db_config.py</files>
  <action>ADDITIVE change (keep the existing get_agent_llm(agent_name, model=ModelHint|None) signature for now — mode removal drops the param in B.1). In get_agent_llm, after reading env cfg = settings.agent_llm_configs.get(agent_name), layer the DB override:
      from app.core.agent_config_cache import AgentConfigCache
      ov = AgentConfigCache.get(agent_name)
      provider = (ov.provider if ov else None) or (cfg.provider if cfg else None) or s.llm_provider
      resolved_model = (ov.model if ov else None) or (cfg.model if cfg else None) or (s.fast_llm_model if fast else s.llm_model)
      base_url = (ov.base_url if ov else None) or s.llm_base_url
    temperature/extra stay from env cfg. Add a base_url parameter to _build_chat_model(provider, model, *, temperature=None, base_url=None, **extra) and use `base_url or s.llm_base_url` inside (preserve today's global behavior when unset); pass the resolved base_url from get_agent_llm. Test (inject AgentConfigCache via sync_from_cache; monkeypatch _build_chat_model or init_chat_model to capture args): DB override wins over env; per-field fallback (provider from DB, model from env); base_url override passed through; agent A's row does not affect agent B; empty cache == today's behavior.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/clients/test_get_agent_llm_db_config.py -x</verify>
  <done>get_agent_llm resolves DB→env→global per field incl. base_url; no cross-agent leak; defaults unchanged when cache empty.</done>
</task>
```

### Task A.7 — Load the cache at lifespan startup

```xml
<task id="A.7" wave="4">
  <files>apps/api/app/core/lifespan.py, apps/api/tests/core/test_lifespan_config_reload.py</files>
  <action>In core/lifespan.py, right AFTER seed_all(get_session_factory(settings.database_url)) (line ~43) and before the graph build (~68), call reload_from_db(get_session_factory(settings.database_url)) so the cache is populated before the first request. Reuse get_session_factory (same as seed — no str(URL) password masking, memory sqlalchemy-str-url-masks-password). Test: run the lifespan startup path against a seeded temp DB and assert AgentConfigCache has the 9 seeded keys. Keep the call idempotent/safe if the table is empty.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/core/test_lifespan_config_reload.py -x</verify>
  <done>Cache is populated at startup from the seeded rows; startup is safe on an empty table.</done>
</task>
```

> **Phase A gate:** run the full suite — `cd apps/api && ../../.venv/bin/python -m pytest -q`.
> The DB config feature now works end-to-end with `mode` still present. Commit Phase A before B.

---

### Phase B — Remove `mode` (BE, coordinated deletion)

### Task B.1 — Remove `mode` across the agent core

```xml
<task id="B.1" wave="5">
  <files>apps/api/app/enums.py, apps/api/app/agents/constants.py, apps/api/app/agents/context.py, apps/api/app/agents/subagents/_base.py, apps/api/app/clients/llm.py, apps/api/app/agents/graph.py, apps/api/tests/agents/test_deferred_model.py</files>
  <action>Coordinated removal (edit together so imports never dangle). (1) enums.py: remove ChatMode + ModelHint; KEEP ResponseStyle. (2) constants.py: remove DEFAULT_MODE + the ChatMode import (keep DEFAULT_TIER/Tier); update the module docstring's "(tier, mode)" wording. (3) context.py: remove the `mode` and `model` (ModelHint) fields + `_MODE_POLICY`; KEEP `response_style: ResponseStyle = ResponseStyle.DEFAULT` and its import; change resolve_agent_context(*, tier) (drop `mode` param) to return fixed BALANCED defaults (allow_reflection=True, allow_memory_write=True, allow_episodic=True, response_style=DEFAULT, max_revisions=1) with the tier ceiling unchanged (free: allow_rag=False + allowed_subagents excludes booking); update the module docstring. (4) subagents/_base.py: remove the ResponseStyle import (:37), the ctx.response_style read (:100–102), and the CONCISE/DETAILED prompt branches (:117–124) — response_style is now always DEFAULT; keep the allow_rag/allow_episodic tool filtering. (5) clients/llm.py: drop the `model: ModelHint | None` param + the FAST/DEEP branches + the ModelHint import; get_agent_llm(agent_name) now relies on FAST_AGENTS + DB/env config only. (6) subagents/_base.py assistant node: remove the `ctx_model = ctx.model` read (ctx.model no longer exists) — MINIMAL PATH: keep the resolver's `Callable[[str | None], BaseChatModel]` arity and just pass `resolve_model(None)` (so the 5 sub-agent builders planner/journal/booking/budget/concierge.py keep their type hints untouched and stay OUT of this task's file set). (7) graph.py: in resolver_for, the inner resolve(ctx_model) now always gets None from _base — leave the closure cache keyed on None; no ModelHint import. Update tests per Task 0 lists: DELETE tests/agents/test_deferred_model.py; edit any caller of get_agent_llm(..., model=...) / resolve_agent_context(..., mode=...) in tests touched here.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents -x -q</verify>
  <done>Agent core compiles with no ChatMode/ModelHint; get_agent_llm(agent_name) resolves from DB/env; tests/agents green (deferred-model test removed).</done>
</task>
```

### Task B.2 — Remove `mode` from the API surface + fix remaining tests

```xml
<task id="B.2" wave="6">
  <files>apps/api/app/schemas/agent.py, apps/api/app/routers/agent.py, apps/api/tests/api/agent/test_mode_context.py, apps/api/tests/agents/test_agent_context.py, apps/api/tests/agents/test_depth_toggles.py</files>
  <action>Depends on B.1. (1) schemas/agent.py: remove ONLY the `mode` field from ChatRequest (`:31`). The `mode` field has NO validator. **KEEP** the `@model_validator _require_message_or_resume` (`:50`) — it guards message/resume and is unrelated to mode; deleting it would drop a required-input guard AND trip the weakening-validation gate. Do not touch it. (2) routers/agent.py: change _resolve_context(effective_user_id, authenticated, session) (drop the `mode` param) and both call sites (:180 /chat, :274 /stream) to stop passing body.mode; keep resolving tier server-side + passing context=ctx. (3) Tests per Task 0: DELETE test_mode_context.py + test_depth_toggles.py (mode-only); REWRITE test_agent_context.py to drop mode assertions and call resolve_agent_context(tier=...) (keep tier-matrix assertions). Leave test_tier_gating.py / test_context_*.py fixes to whatever Task 0 flagged (drop the mode kwarg only). Any tool test that merely defaults response_style needs NO change (field kept).</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent tests/agents -x -q</verify>
  <done>ChatRequest has no `mode`; router resolves tier only; agent + api/agent suites green.</done>
</task>
```

### Task B.3 — Full BE suite + Postgres parity + commit gate

```xml
<task id="B.3" wave="7">
  <files>apps/api/travel.db</files>
  <action>Rebuild travel.db (delete + let lifespan re-seed, or run the migration + seed path). Run the FULL BE suite on SQLite, then Postgres parity. Confirm no residual mode references: grep -rn "ChatMode\|ModelHint\|body.mode\|\.mode\b" app/ returns nothing meaningful (ResponseStyle references are expected/kept). This is the public-contract commit — commit with RISK_WARN_CATEGORIES="public-contract" (memory public-contract-hard-gate); confirm weakening-validation is N/A (no validator removed) or add the category if the gate fires.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest -q && make test-docker</verify>
  <done>Full suite green on SQLite + Postgres; no stray mode symbols; commit passes gates with the public-contract warn category. NOTE: this is a phase-level integration gate — it intentionally exceeds the plan-format 60s per-task <verify> budget (full suite + Docker Postgres spin-up).</done>
</task>
```

---

### Phase C — Remove `mode` (FE)

### Task C.1 — Strip the mode selector + regenerate the API schema

```xml
<task id="C.1" wave="8">
  <files>apps/web/src/components/chat/useAgentStream.ts, apps/web/src/components/chat/ChatPanel.tsx, apps/web/src/lib/api/schema.d.ts, apps/web/src/locales</files>
  <action>Node v24 (export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH"). (1) useAgentStream.ts: remove ChatMode type, MODE_STORAGE_KEY, readStoredMode/writeStoredMode, the mode state + setMode, `mode` from all three request bodies (send/resume/retry) and from the useCallback deps. (2) ChatPanel.tsx: remove the ChatMode import, MODES array, mode/setMode destructure, the mode-selector <select> block, and the modeLabel/modeFast|Balanced|Deep usages. (3) Remove the mode i18n keys from the locale files under src/locales (both en + vi). (4) Regenerate the API types: with the updated BE running on :8000, run `pnpm --filter web gen:api` so schema.d.ts drops the `mode?` field (do not hand-edit). Requires dummy NEXT_PUBLIC_SUPABASE_URL/KEY for the web build (memory env-supabase-required-for-web-dev-server).</action>
  <verify>cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm --filter web typecheck</verify>
  <done>No `mode` in FE; selector gone; schema.d.ts regenerated without `mode`; web typecheck passes.</done>
</task>
```

## 5. Risks / hard gates

- **Migration + new table (A.3)** — Rule-4 data gate, approved (ESCALATIONS E002). Rollback:
  `alembic downgrade -1`; rebuild `travel.db` after.
- **Public contract (B.2/B.3)** — `mode` leaves `ChatRequest`; commit with
  `RISK_WARN_CATEGORIES="public-contract"` (memory `public-contract-hard-gate`).
- **Weakening validation** — research indicates no `model_validator` on `mode`; if the gate fires
  on a removed `assert`/`raise`, add `weakening-validation` to the warn categories.
- **Cross-agent leakage** — cache keyed strictly by `agent_name`; covered by A.6 test.
- **Stale `travel.db`** — rebuild after A.3 and before B.3 (memory
  `stale-travel-db-breaks-suite-on-schema-change`).
- **FE codegen needs BE up** — `gen:api` hits `:8000`; run the updated BE first (memory
  `fe-talks-to-docker-api-8000-rebuild-after-be-change` if using Docker).

## 6. Waves

| Wave | Tasks | Parallel | Notes |
|------|-------|----------|-------|
| 0 | 0.1 | single | recon: mode/response_style test footprint |
| 1 | A.1 | single | model + schema + register |
| 2 | A.2, A.3 | 2 (repo vs alembic — disjoint) | repository + migration |
| 3 | A.4, A.5 | 2 (cache vs seed/data — disjoint) | cache + seed |
| 4 | A.6, A.7 | 2 (llm.py vs lifespan.py — disjoint) | resolution + startup wiring |
| — | Phase A gate | — | full suite green; commit Phase A |
| 5 | B.1 | single | agent-core mode removal (shared imports) |
| 6 | B.2 | single | API surface + tests (depends on B.1) |
| 7 | B.3 | single | full suite + Postgres + public-contract commit |
| 8 | C.1 | single | FE strip + schema regen |

## 7. Status Log

- 2026-07-01 — Plan drafted from approved design.md + research-brief.md. Decisions locked: keep
  `response_style` as fixed DEFAULT (min test churn); regenerate `schema.d.ts` via `pnpm gen:api`;
  per-agent rows for all 9 LLM nodes; migration approved. Task 0 must record the exact DELETE /
  REWRITE / NO-CHANGE test lists here before B.1/B.2 execute.
