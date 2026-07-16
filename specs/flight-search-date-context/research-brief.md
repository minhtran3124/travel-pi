---
slug: flight-search-date-context
kind: research-brief
depth: Deep
created: 2026-07-09
---

# Research Brief — Flight & Hotel Date Awareness + Multi-Turn Stitching

## Feature + depth
**Deep.** The feature mutates the public `ChatRequest` contract (new `timezone` field →
public-contract gate), threads a new value through the agent graph (`AgentContext` → node),
ships new prompt-registry versions (graph rebuild), and touches deterministic tool validation
(weakening-validation gate). Research is local-only — no upstream/docs needed.

## What already exists (per focus question)

1. **`ground_current_date`** `Local app/agents/state.py:79-100`. Signature today:
   `def ground_current_date(base: SystemMessage) -> SystemMessage`. Body builds today at `:92`
   `today = datetime.now(timezone.utc).strftime("%Y-%m-%d")`. Note text `:94`:
   `CURRENT DATE: today is {today} (UTC). This is the only correct value for "today". Resolve
   every relative date ("today", "tomorrow", "next Friday", "this weekend") against it…`. The
   `"next Friday"` phrase is present at `:95` (LLM is expected to resolve it). **Cleanest tz add:**
   `def ground_current_date(base, tz: str | None = None)` — `today = datetime.now(ZoneInfo(tz)).…`
   when `tz` truthy else current UTC path; default `None` preserves behavior exactly.

2. **Call site** `Local app/agents/subagents/_base.py:111`:
   `system_with_summary(state, ground_current_date(system))` (import at `:36`). Repo-wide grep:
   the ONLY production caller is `_base.py:111`; other hits are the def (`state.py:79`) and one
   test (`tests/agents/test_state.py:184-192`). Adding a param is additive, not a rename.

3. **`AgentContext`** `Local app/agents/context.py:30-43` — a `@dataclass(frozen=True)`, NOT a
   state field. Fields: `tier, allow_reflection, allow_memory_write, allow_episodic,
   response_style, allowed_subagents, max_revisions`. It is the LangGraph 1.0 **context channel**:
   graphs declare `StateGraph(TravelAgentState, context_schema=AgentContext)` (`_base.py:120`),
   the router passes `graph.ainvoke(..., context=ctx)` (`agent.py:206,211/218,371`), and nodes
   read it via `runtime: Runtime[AgentContext]` → `runtime.context` (`_base.py:96-99`,
   `supervisor.py:60,90-93`). **Adding `timezone: str | None = None` is clean** and rides the
   exact path `tier`/`allow_reflection` already take: `_resolve_context` builds it →
   `resolve_agent_context(...)` returns it → node reads `runtime.context.timezone`.

4. **Supervisor** `Local app/agents/supervisor.py:74`:
   `intent = router.invoke([system_with_summary(state, base), *state["messages"]])` — no
   `ground_current_date`, so routing is date-blind. `base` is built at `:67-73`. To match the
   sub-agent pattern: wrap with `ground_current_date(base, tz)` where `tz` comes from
   `runtime.context` (already read at `:90-93` as `ctx`).

5. **Tool date parsing.**
   - Flight: `Local app/tools/flight_tools.py:85-100` — `today = datetime.now(timezone.utc).date()`,
     `strptime(departure_date, "%Y-%m-%d")` → `ToolException` on bad format (`:89`) and past date
     (`:94`). `SearchFlightsArgs` `departure_date` at `:58`.
   - Hotel: `Local app/tools/hotel_tools.py` — `search_hotels` (`:124`) has `check_in`/`check_out`
     with the SAME `strptime("%Y-%m-%d")` + past-check block at `:168-177` (only `check_in` gets a
     past-check). `book_hotel` (`:325`) takes `check_in`/`check_out` (`:99-100`) but does NOT
     `strptime`/past-validate them (passes straight to service). `browse_hotels` (`:242`) is
     **date-less** (no check-in/out — confirms memory hint). **Tools needing `resolve_travel_date`:**
     `search_flights` (departure_date), `search_hotels` (check_in, check_out). `book_hotel` is
     optional — booking dates normally arrive already-ISO from a prior search.

6. **Prompt registry** `Local app/prompts/registry.py`. File-backed: `prompts/<name>/v<N>.md`,
   active version declared in `active.yaml` (`:53-58`). `get(name)` returns
   `active.yaml[name]` version, else `max(versions)` (`:71-73`). Module-level singleton
   `registry = PromptRegistry()` at `:107`. **`active.yaml` is NOT empty** —
   `Local app/prompts/active.yaml` currently: `planner: 5`, `booking: 4`, `supervisor: 5`, etc.
   MIN-43's DB `agent_config` table governs **model/provider/temperature only**, NOT prompt
   version — prompt selection is purely file + `active.yaml`. **To ship a new version:** (a) add
   `app/prompts/planner/v6.md` and `app/prompts/booking/v5.md`; (b) bump `active.yaml`
   (`planner: 6`, `booking: 5`). Both are files. **Rebuild required:** registry is read once at
   import and the graph is baked at lifespan startup — editing a prompt does NOT hot-reload the
   running agent (`prompt-changes-need-graph-rebuild-not-hot-reloaded`); force via
   `docker exec api-api-1 touch app/main.py` or a restart.

7. **Router** `Local app/routers/agent.py`. Body read as `body: ChatRequest` (`:174`, `:290`).
   Context built in `_resolve_context(...)` (`:145-169`) → `resolve_agent_context(tier=…,
   allow_reflection=…)`. `ctx` passed to graph at `:206/218` (chat) and `:371` (stream).
   **Exact spot:** read `body.timezone`, validate via `zoneinfo.ZoneInfo`, fallback to
   `get_settings().agent_timezone` on missing/invalid (log warning), pass into
   `_resolve_context`/`resolve_agent_context` so it lands on `AgentContext.timezone`.
   `ChatRequest` `Local app/schemas/agent.py:16` extends `AppBaseModel` — adding
   `timezone: str | None = Field(default=None, …)` is clean/additive/backward-compatible.

8. **Config** `Local app/core/config.py:35` `class Settings(BaseSettings)` (pydantic-settings),
   `@lru_cache get_settings()` at `:233`. Env var = UPPERCASE field name (e.g. `climate_years`
   ← `CLIMATE_YEARS`; `agent_recursion_limit: int = 25` at `:170`). Add
   `agent_timezone: str = "Asia/Ho_Chi_Minh"` in the agent-runtime block (~`:169-176`), read via
   `AGENT_TIMEZONE`.

## What must be built (per design component)
- **A (tz plumbing):** `ChatRequest.timezone` field (schema); `Settings.agent_timezone` (config);
  `AgentContext.timezone` field (context); router validation + threading in `_resolve_context`
  and both handlers. Thread tz `resolve_agent_context(..., timezone=tz)`.
- **B (grounding):** add `tz` param to `ground_current_date` (state.py); update call at
  `_base.py:111` to pass `runtime.context.timezone`; add a NEW grounding call in
  `supervisor.py:74`.
- **C (tool normalization):** new `app/core/dates.py::resolve_travel_date(raw, today) -> str`;
  call it before `strptime` in `search_flights` and `search_hotels` (and pass tz-aware `today`).
- **D (prompts):** new `planner/v6.md` + `booking/v5.md` (reframe "never guess dates", sharpen
  stitch rule, confirm-then-call); bump `active.yaml`.

## Prompt-shipping mechanism (the riskiest unknown — resolved)
File + pointer, both required, NOT DB. Add `v<N>.md` under the prompt dir; set the version in
`app/prompts/active.yaml`. `get()` falls back to `max(versions)` only if `active.yaml` omits the
name, so the bump is mandatory to activate. Running graph is baked at startup → **rebuild/restart
to take effect** (registry singleton + lifespan graph). No migration, no DB row.

## Lightest credible path (reuse > adapt > build)
1. **Reuse** the existing context channel — `timezone` on `AgentContext` follows `tier`/
   `allow_reflection` verbatim (router → `resolve_agent_context` → `runtime.context`). No new
   state channel (design §A confirmed).
2. **Adapt** `ground_current_date` (add optional `tz`, default preserves UTC) and the two tool
   parse blocks (prepend `resolve_travel_date`).
3. **Build** only the small new surface: `app/core/dates.py`, two prompt versions, the config
   default, the schema field.
   **tz-threading path (explicit):** `body.timezone` → validate(ZoneInfo)/fallback
   `settings.agent_timezone` → `AgentContext.timezone` → `graph.ainvoke(context=ctx)` →
   `runtime.context.timezone` → `ground_current_date(base, tz)` in both `_base.py` node and
   `supervisor.py`; tools compute `today` in tz.

## Risks / gotchas
- **Graph rebuild:** prompt + graph baked at lifespan; verify against a rebuilt graph, not the
  live container.
- **Public-contract gate:** `ChatRequest.timezone` trips it even though additive — authorize via
  `RISK_WARN_CATEGORIES="public-contract"` (`public-contract-hard-gate` memo).
- **Weakening-validation gate:** `resolve_travel_date` loosening the strict `strptime` may warn;
  also editing/removing `raise ToolException` lines can trip `weakening-validation`.
- **Hotel differs from flight:** `search_hotels` past-checks only `check_in` (not `check_out`);
  `book_hotel` doesn't validate dates at all; `browse_hotels` is date-less. Insert
  `resolve_travel_date` only where dates are parsed (flight departure_date, hotel check_in/out).
- **tz must reach the node:** `runtime.context` can be `None` in tests (`_base.py:98`,
  `supervisor.py:90-93`) — guard `tz = ctx.timezone if ctx else None` and let
  `ground_current_date(None)` keep UTC.

## Open questions
- Should `book_hotel` also normalize dates, or rely on already-ISO values from search? (Design
  §C lists "hotel search/quote" — booking not explicitly in scope.)
- Confirm-first UX (design §6) is an LLM behavior only verifiable via DeepEval (FakeLLM canned in
  unit tests) — no deterministic gate. Acceptable?
- FE side (`apps/web`) must send `Intl…timeZone`; out of this BE research scope but a dependency
  for the end-to-end fix.
