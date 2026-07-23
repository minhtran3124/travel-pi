# Research Brief — MIN-43 DB-backed per-agent config + remove `mode`

> Depth: **Deep** (schema/migration + touches the graph-build/lifespan path). xia2 `PROJECT.md`
> is the harness meta-repo profile, not this app — flagged; depth is Deep on an unambiguous
> migration signal regardless, so classification is unaffected. Upstream/Docs web search skipped:
> every needed pattern already exists in-repo (pure reuse), so external prior art adds no signal.

## Bottom Line

| Field | Value |
|---|---|
| **Recommendation** | **Reuse existing** patterns — every building block already has an in-repo template. |
| **Why this is the lightest credible path** | The config layer clips onto one choke point (`get_agent_llm`) and copies the existing model/repo/schema/migration/seed patterns; mode removal is a mechanical (if wide) deletion. |
| **Confidence** | 88% |
| **Next step** | `writing-plans` → `PLAN.md`. First task must **grep-verify** the exact `response_style` test blast radius before choosing full-prune vs keep-as-constant. |

## Repo Snapshot

| Field | Detected |
|---|---|
| Repo type | Monorepo (pnpm+turbo): FastAPI backend `apps/api/`, Next.js web `apps/web/` |
| Primary language + runtime | Python 3.10+ (Docker runs 3.12), SQLAlchemy 2.0 `Mapped[]` ORM |
| Frameworks | FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2, LangGraph 1.0, Next.js |
| Relevant packages | `langchain.init_chat_model`, `langgraph.runtime.Runtime` |
| Constraints | Layers routers→services→repositories; ORM only in `repositories/`; `datetime.now(timezone.utc)`; seed idempotent from `app/data/`; rebuild `travel.db` after schema change |

## Feature Understanding and Assumptions

- **Requested feature:** Store per-agent (main + sub-agents) model config (`provider`/`model`/`base_url`) in the DB, cached in-process, resolved at runtime with per-field env fallback; edited via MIN-48 dashboard later. **Also remove the `mode` feature entirely (FE+BE).**
- **Success:** A DB row overrides an agent's provider/model/base_url without redeploy (cache reloadable); `mode` no longer exists anywhere; default agent behavior equals today's BALANCED; tier gating intact; SQLite+Postgres parity.
- **Assumptions from request (locked in SUMMARY/ESCALATIONS):** per-agent rows; migration approved; in-process cache via `sync_from_cache`; fixed BALANCED depth defaults; keep tier; provider+model+base_url only (no temperature/system_prompt in DB).
- **Still needs confirmation:** `response_style` full-prune vs keep-as-constant (drives test churn — see Risks).

## Evidence Ledger

| Label | Evidence |
|---|---|
| `Local` | `get_agent_llm` (`clients/llm.py:99`) is the single model-resolution choke point reading `settings.agent_llm_configs`; `_build_chat_model:38` applies global `llm_base_url`. |
| `Local` | `UUIDBase` (`db/base.py:73`) = UUID PK + ISO `created_at/updated_at`; unique via partial `Index(..., unique=True, sqlite_where/postgresql_where)` (`db/models/trip.py:22`). |
| `Local` | Repo base `RepositoryBase(session_or_factory)` with `_session()`/`_commit()` (`repositories/base.py:22`); `UserRepository` (`repositories/user.py:17`) shows get/ensure/upsert. |
| `Local` | `AppBaseModel(ConfigDict(from_attributes=True))` (`schemas/base.py:15`). |
| `Local` | Alembic head = **`a1f3e2c9b7d5`** (users-tier); create-table template `0ab2cdadfc16_add_agent_tables_*` (`op.create_table` + unique index). |
| `Local` | `seed_all(session_factory)` (`db/seed.py:294`) idempotent via `session.merge()` (PK) or select-by-natural-key (City, `:106`); called `lifespan.py:43`. |
| `Local` | Isolated sessionmaker pattern: `_isolated_factory(session)` binds `sessionmaker(bind=session.get_bind())` (`routers/agent.py:121`); `get_session_factory(url)` used by seed. |
| `Local` | Mode removal ripples into ~19 tool tests + several context tests that construct `AgentContext`/read `response_style` (see Risks). |
| `Inference` | Because config is app-global, a startup-loaded singleton cache (not `context_schema`) is the correct altitude — matches the choke-point at `get_agent_llm`. |

## Local Findings

**Config layer — reuse targets**
- **Model:** new `app/db/models/agent_config.py` → `AgentConfig(UUIDBase)`; `agent_name` unique via the partial-index pattern (`trip.py:22`). Register in `db/models/__init__.py` (explicit import + `__all__`).
- **Schema:** `app/schemas/agent_config.py` extending `AppBaseModel`.
- **Repository:** `app/repositories/agent_config.py` mirroring `UserRepository` (`_session()/_commit()`, `list_all/get/upsert`). Validate `provider` against `LLMProvider` on upsert.
- **Migration:** new revision, `down_revision = "a1f3e2c9b7d5"`; copy `0ab2cdadfc16` create-table + unique-index shape.
- **Seed:** add to `seed.py` — one row per LLM node with NULLs; **natural-key upsert** (select-by-`agent_name` then insert, City pattern `:106`) because PK is UUID, not `agent_name` (so `merge()` won't dedupe by name).
- **Cache:** new `app/core/agent_config_cache.py` — singleton with `sync_from_cache(cls, cache)` + `get(agent_name)` + module `reload_from_db(session_factory)`. Import-safe for `clients/llm.py`.
- **Resolution:** extend `get_agent_llm(agent_name)` with per-field fallback DB→env→global; add `base_url` param to `_build_chat_model` (preserve global fallback).
- **Wiring:** call `reload_from_db(get_session_factory(settings.database_url))` in `lifespan.py` right after `seed_all` (`:43`), before graph build (`:68`). Reuse `get_session_factory` (same as seed) — no password-masking issue.

**Mode removal — confirmed footprint (BE)**
- `enums.py`: `ChatMode` (:185), `ModelHint` (:213), `ResponseStyle`.
- `constants.py`: `DEFAULT_MODE` (:19) + `ChatMode` import (:15) — keep `DEFAULT_TIER`/`Tier`; update docstring.
- `context.py`: `mode`/`model`/`response_style` fields, `_MODE_POLICY` (:56), `resolve_agent_context(tier, mode)` → `(tier)`, `ResponseStyle` import (:30). **AgentContext + tier logic STAY.**
- `clients/llm.py`: drop `model: ModelHint` param + FAST/DEEP branches (:122) + import (:28).
- `subagents/_base.py`: `ResponseStyle` import (:37), `ctx.response_style` read (:100–102), CONCISE/DETAILED branches (:117–124).
- `schemas/agent.py`: `ChatRequest.mode` (:31–36) — note research says **no** `model_validator` on mode (validation is server-side in `resolve_agent_context`), so the "weakening-validation" gate risk is lower than assumed but the `public-contract` change stands.
- `routers/agent.py`: `_resolve_context` (:136) drop `mode` param; call sites `:180` `:274` drop `body.mode`.

**Mode removal — FE**
- `useAgentStream.ts`: `ChatMode` type (:18), `MODE_STORAGE_KEY` (:15), read/write (:20–30), state (:156), `setMode` (:158), request bodies (send :282, resume :399, retry :499) + useCallback deps (:382,:467,:584).
- `ChatPanel.tsx`: `ChatMode` import (:12), `MODES` array (:34), destructure (:44), selector `<select>` UI (:75–91), i18n labels (`modeLabel`/`modeFast|Balanced|Deep`).
- Regenerate `schema.d.ts` (`mode?` at :1682) via `pnpm gen:api` (needs BE on :8000) — or hand-edit to drop the field.

**Conventions to preserve:** ORM only in repositories; isolated factory bound to engine; `session.merge`/select-by-key idempotent seed; explicit model registration; `AppBaseModel`.

## Recommendation

- **Primary:** **Reuse existing** — no new dependency, no new pattern. All five config pieces have a direct in-repo template; the choke-point design keeps blast radius to one function + additive files.
- **Next-best that lost:** passing config through `AgentContext`/`context_schema` (the ticket's literal wording) — wrong altitude for app-global config and would touch every node; rejected in design §4.
- **What would change it:** if config later needs per-user/per-conversation scope, revisit the context-channel approach.

## Risks, Unknowns, and Follow-Up Questions

- **Test blast radius (biggest risk):** removing `response_style` (full-prune) touches every test that constructs `AgentContext(response_style=...)` or asserts on it — research counts **~19 tool tests + `test_context_episodic.py`/`test_context_memory_write.py`** plus the mode-specific suites to delete (`test_mode_context.py`, `test_depth_toggles.py`, `test_deferred_model.py`) and rewrite (`test_agent_context.py`, `test_tier_gating.py` — tier stays, but they call `resolve_agent_context(..., mode=...)`). **The plan's first task must grep-verify the exact count and decide full-prune vs keep-`response_style`-as-constant** (keeping the field at `DEFAULT` and removing only the prompt branches would sharply cut tool-test churn; costs one unused field). This changes plan sizing, not the design's core.
- **New MIN-43 tests needed:** deferred-model tests keyed on `ModelHint` (`test_deferred_model.py`) get replaced by tests that DB config drives model per agent + per-field fallback + no cross-agent leak + cache reload.
- **Migration/DB:** rebuild `travel.db` after migrating or the whole suite fails (memory `stale-travel-db-breaks-suite-on-schema-change`); run `make test-docker` for Postgres parity.
- **Public contract:** `mode` leaves `ChatRequest` → commit with `RISK_WARN_CATEGORIES="public-contract"` (weakening-validation likely N/A — no validator on `mode`, confirm at commit).
- **Follow-up questions (max 2):**
  1. `response_style`: full-prune the field (cleaner, more test churn) or keep it as a fixed `DEFAULT` constant (less churn, one unused field)?
  2. FE `schema.d.ts`: regenerate via `pnpm gen:api` against a running BE, or hand-edit the single `mode?` field?

## Source Pack

- **Local files read:** `clients/llm.py`, `agents/context.py`, `agents/constants.py`, `agents/graph.py`, `agents/subagents/_base.py`, `core/config.py`, `schemas/agent.py`, `routers/agent.py`, `db/base.py`, `db/models/{trip,user,__init__}.py`, `repositories/{base,user}.py`, `schemas/base.py`, `db/seed.py`, `core/lifespan.py`, `alembic/versions/*`, FE `useAgentStream.ts`, `ChatPanel.tsx`, `package.json`, `schema.d.ts`.
- **Upstream / Docs:** none (pure in-repo reuse; external search skipped as no-signal).

## Evidence Boundary

> **Confirmed from artifacts:** the config choke point + all reuse templates (model/repo/schema/migration/seed/lifespan); Alembic head `a1f3e2c9b7d5`; the BE + FE mode footprint with line numbers.
> **Inferred:** exact number of tool tests that *set* vs merely *default* `response_style` (subagent reported ~19 referencing `AgentContext`; not each verified as constructing with `response_style`) — the plan must grep to confirm.
> **Not checked:** whether any non-test caller outside `app/` imports the removed enums; Postgres-specific migration behavior (run `make test-docker`).
