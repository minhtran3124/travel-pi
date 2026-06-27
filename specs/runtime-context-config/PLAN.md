---
slug: runtime-context-config
status: active
owner: Minh Tran
created: 2026-06-27
---

# Runtime Context: user-selectable Mode + Tier

> Driver for the LangGraph `Runtime`/`context_schema` adoption described in
> `specs/travel-agent/RUNNABLE_CONFIG_RESEARCH.md` (§3–4). **Sequenced AFTER**
> `specs/conversation-persistence/` (user decision). Lane: **high-risk** — touches
> authorization (tier), a DB migration (new table), and quota (billing-adjacent).

## 1. Motivation

Let users pick a **mode** (e.g. `fast` vs `deep`) per turn, and gate capabilities by a
per-user **tier** (e.g. `free` vs `premium`). Per the research, these are *per-run, constant,
agent-doesn't-write, node/tool-must-read* values → the LangGraph 1.0 **`context` channel**,
not state and not `config["configurable"]`.

Confirmed scope (user answers, 2026-06-27):
- **Mode controls:** model choice · agent depth (reflection/RAG on-off) · response style ·
  reasoning limits (recursion_limit / token budget).
- **Tier gates:** model allowed · feature depth (RAG/memory/reflection) · usage quota ·
  tool/sub-agent availability.
- **Tier source:** **BE-resolved** from a user profile (Supabase/DB) — never trusted from the
  client.

## 2. Current state (from investigation)

- `get_agent_llm(agent_name)` (`clients/llm.py:63`) builds a fresh model **per call** from
  `settings.agent_llm_configs` → model id is already swappable at request time *for nodes that
  don't bind tools*.
- Sub-agents bind tools at **build time** (`subagents/_base.py:55 llm.bind_tools(tools)`) →
  per-request model swap needs **deferred binding** (see §4 decision D1).
- Supervisor routes via `Command(goto=...)` (`supervisor.py:40`) — natural gating point.
- Reflection node `make_reflection_node(max_revisions=1)` (`nodes.py:67`); RAG is a tool in the
  concierge set (`registry.py:33`, `get_tools_for("concierge")`).
- `TravelAgentState` (`state.py:15`): `user_id, trip_id, current_flow, summary, revisions,
  trip_context`. **No `mode`/`tier`.** No `context_schema` anywhere.
- **No users/profiles table** — `user_id` is a bare string; `Conversation.user_id` has no FK.
  Auth (`core/auth.py:43`) yields `AuthUser{id,email,role,claims}` — JWT carries a `role`
  claim, but only `user_id` reaches the agent today.
- **No quota/usage tracking** of any kind.
- FE `useAgentStream` builds the request body at `useAgentStream.ts:145` — clean spot to add a
  `mode` field (tier is NOT sent by the FE).

## 3. Non-goals

- Not moving `user_id`/`trip_id` out of **state**: tools depend on `InjectedState("user_id")`
  (`tools/memory_tools.py`). Keep them in state; add a **separate** `AgentContext` for the new
  per-run values. (Migrating tools to `ToolRuntime` is a later, optional cleanup.)
- Not building a billing system. Quota here = a simple per-day turn guard (§Phase D), not
  payments/Stripe.
- Not a multi-tenant authz overhaul — just a single `tier` attribute per user.

## 4. Architecture decisions (RESOLVED 2026-06-27)

**D1 — Per-request model selection with tool-bound sub-agents → DEFERRED BINDING (chosen).**
Keep ONE compiled graph; move `llm.bind_tools(tools)` from build time into the sub-agent node so
it binds `get_agent_llm(name, model=ctx.model)` at invoke time. `get_agent_llm` already builds
per call, so cost is one extra model-object build per turn. Supervisor/reflection (no tools)
swap models freely. *(Rejected: prebuilt graph-variant registry — duplicates the graph and
multiplies with tier; revisit only if deferred binding profiles hot.)*

**D2 — Tier storage & resolution → ADD `users` TABLE (chosen).**
Add a minimal `users` table (`user_id PK, tier, created_at, updated_at`); resolve tier BE-side
in `resolve_agent_context()` at the router; default `free` when absent. The DB row is the source
of truth (also needed for quota D4). *(Rejected: trust JWT `role` claim only — role ≠ billing
tier and quota needs DB anyway.)* This still requires a migration (hard gate) — execute B.1 with
the rollback recorded, but the design decision is no longer blocked.

**D3 — Capability resolution lives at the boundary.** Compute a single resolved `AgentContext`
(tier ∩ mode → concrete capabilities) in the router, so nodes stay dumb (just read flags). The
policy table (what `free`+`fast` actually yields) is one function, not scattered `if tier==`.

**D4 — Quota → IN THIS PLAN, simple guard (chosen).**
Enforce as a **router-level precondition guard** (count today's turns per user, return 429 over
the tier limit) — not context; runs before invoke. Limits in settings per tier. Phase D.2 stays
in scope. *(Rejected: split to a separate plan / skip — kept here to ship abuse protection with
the gating it depends on.)*

## 5. Success Criteria

- FE can send `mode`; BE resolves `tier` from the user profile (never from the request body).
- Nodes/tools read capabilities from `runtime.context` (typed `AgentContext`); no tier/mode
  logic duplicated across nodes.
- `fast` mode demonstrably uses the cheaper model + skips reflection; `deep` runs full depth.
- `free` tier is blocked from premium-only sub-agents/tools and hits the quota guard; `premium`
  is not.
- Existing chats unaffected when no `mode` is sent (defaults preserve today's behavior).

## 6. Tasks

### Phase A — Context plumbing (no behavior change yet)

```xml
<task id="A.1" wave="1">
  <files>apps/api/app/agents/context.py, apps/api/app/agents/graph.py, apps/api/tests/agents/test_agent_context.py</files>
  <action>Add app/agents/context.py defining `AgentContext` (dataclass): tier:str="free", mode:str="balanced", model:str|None, allow_reflection:bool=True, allow_rag:bool=True, response_style:str="default", allowed_subagents:frozenset[str]|None=None, max_revisions:int=1. Add a pure `resolve_agent_context(*, tier, mode) -> AgentContext` that maps (tier, mode) → concrete capabilities (the single policy function, D3) with safe defaults. Wire `StateGraph(TravelAgentState, context_schema=AgentContext)` in graph.py (compile unchanged otherwise). No node reads it yet. Unit-test the policy matrix (free+fast, premium+deep, unknown→defaults).</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_agent_context.py -x</verify>
  <done>AgentContext + resolver exist with tested policy matrix; graph compiles with context_schema; behavior unchanged.</done>
</task>
```

```xml
<task id="A.2" wave="2">
  <files>apps/api/app/schemas/agent.py, apps/api/app/routers/agent.py, apps/api/tests/api/agent/test_mode_context.py</files>
  <action>Add `mode: str | None` to ChatRequest (validated enum, default None → "balanced"); do NOT add tier to the request schema (BE-resolved, security). In both /chat and /stream handlers, resolve tier (Phase B repo; until B lands, default "free"), build context via resolve_agent_context(tier=..., mode=body.mode), and pass it to the graph as `context=` on ainvoke/astream (alongside the existing cfg). Move per-run reasoning limits (recursion_limit) into cfg from the resolved context. Keep user_id/trip_id in the state dict (Non-goal). Coordinate with persistence plan's invoke-site edits (that plan ships first).</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_mode_context.py -x</verify>
  <done>Requests carry mode; router passes a resolved AgentContext via context=; tier never read from request body.</done>
</task>
```

### Phase B — Tier storage (hard gate: migration)

```xml
<task id="B.1" wave="3">
  <files>apps/api/app/db/models/user.py, apps/api/app/db/models/__init__.py, apps/api/alembic/versions/xxxx_add_users_tier.py, apps/api/app/repositories/user.py, apps/api/tests/api/user/test_user_repo.py</files>
  <action>D2 resolved (add users table). Add models.User (user_id PK str, tier str default 'free', created_at/updated_at via the project's UUID/timestamp base) + Alembic migration + UserRepository.get_tier(user_id)->str (default 'free' if absent) and an upsert helper. Wire resolve in router (A.2) to use UserRepository. Hard gate (migration) — record Rollback (alembic downgrade -1) in SUMMARY before shipping; rebuild travel.db after migrating (memory stale-travel-db-breaks-suite-on-schema-change).</action>
  <verify>cd apps/api && ../../.venv/bin/alembic upgrade head && ../../.venv/bin/python -m pytest tests/api/user/test_user_repo.py -x</verify>
  <done>users table migrates clean; get_tier returns stored tier or 'free'; router resolves real tier.</done>
</task>
```

### Phase C — Mode behaviors

```xml
<task id="C.1" wave="4">
  <files>apps/api/app/agents/subagents/_base.py, apps/api/app/clients/llm.py, apps/api/tests/agents/test_deferred_model.py</files>
  <action>Implement D1 deferred binding: parameterize sub-agent model by runtime context. Refactor build_subagent so the LLM is resolved+bound INSIDE the node via get_agent_llm(name, model=runtime.context.model or default).bind_tools(tools), reading runtime: Runtime[AgentContext]. Keep the default (model=None → current per-agent config) so unset mode preserves today's models/FAST_AGENTS behavior. Verify a 'fast' context selects the cheap model and 'deep' the strong one.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_deferred_model.py -x</verify>
  <done>Sub-agent model is chosen per-request from context; defaults unchanged when mode unset.</done>
</task>
```

```xml
<task id="C.2" wave="5">
  <files>apps/api/app/agents/nodes.py, apps/api/app/agents/supervisor.py, apps/api/tests/agents/test_depth_toggles.py</files>
  <action>Gate depth by context. Reflection node (nodes.py:67) reads runtime.context.allow_reflection / max_revisions and short-circuits when disabled (fast mode). Supervisor/concierge tool selection filters the RAG tool when context.allow_rag is False. Response_style (context) is injected into the sub-agent system prompt. All gates default to today's behavior when context is default.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_depth_toggles.py -x</verify>
  <done>fast mode skips reflection + RAG and shortens style; deep runs full; default unchanged.</done>
</task>
```

### Phase D — Tier gating

```xml
<task id="D.1" wave="6">
  <files>apps/api/app/agents/supervisor.py, apps/api/app/tools/registry.py, apps/api/tests/agents/test_tier_gating.py</files>
  <action>Enforce tier capability. Supervisor routing refuses to goto a sub-agent not in context.allowed_subagents (falls back to a safe default / explanatory message). get_tools_for(domain) filters premium-only tools when the tier disallows them. NOTE: shares supervisor.py with C.2 → sequence after it.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_tier_gating.py -x</verify>
  <done>free tier cannot reach premium sub-agents/tools; premium can; defaults permissive.</done>
</task>
```

```xml
<task id="D.2" wave="6">
  <files>apps/api/app/services/quota_service.py, apps/api/app/routers/agent.py, apps/api/tests/api/agent/test_quota.py</files>
  <action>D4 quota guard (may be split to its own plan). Add a per-day turn count per user (count user-role messages by created_at, or a small usage counter) and a quota_service.check_and_count(user_id, tier) raising a 429-mapped domain error when over the tier limit. Call it at the start of /chat and /stream BEFORE invoke. Limits come from settings per tier. Does not touch context (it's a precondition, not per-run context).</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_quota.py -x</verify>
  <done>Over-limit free user gets 429; premium higher/uncapped; under-limit unaffected.</done>
</task>
```

### Phase E — Frontend

```xml
<task id="E.1" wave="7">
  <files>apps/web/src/components/chat/useAgentStream.ts, apps/web/src/lib/query/agent.ts</files>
  <action>Add `mode` to the ChatRequest type + send it in the body (useAgentStream.ts:145). Add a minimal mode selector (e.g. fast/balanced/deep) surfaced to the chat UI; persist the choice (localStorage, like userId/conversationId). Do NOT send tier. Handle a 429 quota response with a clear user-facing message.</action>
  <verify>cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm --filter web typecheck</verify>
  <done>User can pick a mode; it's sent + persisted; quota 429 surfaces cleanly; tier never sent.</done>
</task>
```

## 7. Risks / hard gates

- **Migration + new table (B.1)** — Rule 4 / data-loss gate. ESCALATE to confirm D2 before
  migrating. Rollback: `alembic downgrade -1`.
- **Authorization (tier) (B.1, D.1)** — tier IS an authz boundary. Never accept tier from the
  client; always BE-resolve. Security-reviewer pass recommended.
- **Quota (D.2)** — billing-adjacent; confirm limits + behavior. Candidate to split into its own
  plan if it grows beyond a per-day counter.
- **Public contract (A.2, E.1)** — `mode` added to ChatRequest. Commit with
  `RISK_WARN_CATEGORIES="public-contract"` (memory `public-contract-hard-gate`).
- **Model spend** — `deep`/premium routes to a stronger (costlier) model. Guard with tier so
  free users can't select the expensive model.
- **Graph perf (D1)** — deferred binding builds a model object per turn; measure; fall back to a
  registry if hot.
- **Test DB** — no impact beyond the new migration; per memory
  `stale-travel-db-breaks-suite-on-schema-change` rebuild travel.db after B.1.

## 8. Waves

| Wave | Tasks | Parallel | Notes |
|------|-------|----------|-------|
| 1 | A.1 | single | context type + resolver + schema wiring |
| 2 | A.2 | single | router passes context= (shares schemas/router with persistence — after that plan) |
| 3 | B.1 | single | migration/authz (D2 resolved — proceed, record rollback) |
| 4 | C.1 | single | deferred model binding |
| 5 | C.2 | single | depth toggles (shares supervisor.py with D.1) |
| 6 | D.1, D.2 | 2 (disjoint files) | gating + quota |
| 7 | E.1 | single | FE mode selector |

## 9. Status Log

- 2026-06-27 — Drafted after confirming mode+tier direction (BE-resolved tier, persistence
  first).
- 2026-06-27 — Decisions D1/D2/D4 resolved (deferred binding · add users table · quota in-plan).
  Plan finalized; ready to execute after `specs/conversation-persistence/` ships. No remaining
  design blockers; B.1 still passes through the migration hard gate at commit time.
