---
slug: trip-research-deep-agent
doc: research-brief
created: 2026-09-18
depth: Deep
---

# Research brief — trip-research-deep-agent

Depth: **Deep** (intake lane high-risk; external surface = new runtime dependency `deepagents 0.7.15`).
No waiver requested.

## Bottom Line

| Field | Value |
|---|---|
| **Recommendation** | **Adapt upstream** — build a *second* graph with `deepagents.create_deep_agent` (StoreBackend dossier, isolated subagents, RubricMiddleware, TodoListMiddleware), reusing the app's read-only tools, LLM resolver, `agent_runs` persistence and SSE plumbing. The chat graph and the 5 specialists stay hand-built. |
| **Why this is the lightest credible path** | Every capability the job needs (file-backed artifact the agent edits, isolated subagents with compact reports, rubric-driven revision, todo progress) already ships in deepagents and was smoke-built against this repo's `FakeLLM` + 17 registry tools in one script; hand-rolling them in the chat harness re-hits the turn ceilings (`agent_recursion_limit=25`, 12 tool rounds, ledger 4) that motivated the feature. |
| **Confidence** | 80% |
| **Next step** | `writing-plans` from `design.md` §Waves; first wave = dependency + `app/research/` graph + offline FakeLLM test. |

## Repo Snapshot

| Field | Detected |
|---|---|
| Repo type | pnpm/Turborepo monorepo: FastAPI API (`apps/api`) + Next.js web (`apps/web`) |
| Primary language + runtime | Python 3.12 (Docker image) / 3.14 (local `.venv`); TypeScript, Node 24 |
| Frameworks / platforms | FastAPI 0.136, SQLAlchemy 2.0, Alembic, LangGraph 1.2.11, langchain 1.4.1, langchain-core 1.6.3, Next.js + TanStack Query v5 + next-intl |
| Relevant packages | `deepagents` 0.7.15 (new), `langgraph-checkpoint-postgres` 3.1.x, `langchain-openai` 0.3.34, `langsmith` → 0.12.6 (transitive bump) |
| Detectable versions | `apps/api/requirements-ai.txt` floors after PR #219; resolved set in scratch venv: deepagents 0.7.15, langsmith 0.12.6, wcmatch 11.0.1, `pip check` clean |
| Important constraints | `techstacks/langgraph.md` posture "explicit over magic, no create_agent/middleware in the top graph" (this feature is a documented exception, see design §1); tools are thin adapters and `tools/registry.py` is the single source of truth; agents/tools never hold business logic; `agent_runs` stores structure/pointers only, never content; background code never reuses the request session; SSE parser/panels in `apps/web/src/lib/stream/` mirror `streaming/{events,panels}.py` in lockstep; REST identity `X-User-Id` = Supabase user id (`apps/web/src/lib/identity/provider.tsx:11-17`), agent surface = JWT; AI deps must not force fastapi/starlette/pydantic caps |

## Feature Understanding and Assumptions

- **Requested feature:** a minutes-long "research this trip" job started from the trip page or from chat; a deep agent researches flights, stays, day plans, entry/season and budget, writes a multi-file dossier the user can read and edit across sessions, self-checks against a rubric, and produces a proposal the user applies to the real trip. Decisions E001–E004: StoreBackend dossier; BackgroundTask + poll + SSE progress; both chat and trip-page entry; propose-only.
- **What success appears to mean:** `POST` starts a run and returns 202 in <1 s; the trip page shows live phase/tool progress; within a few minutes the dossier (`/research/*.md`, `/plan/proposal.json`) exists in the store namespace for that user+trip; the proposal references only real catalog/flight/hotel IDs; the user can edit a file and re-run "revise"; a chat message "research my trip" starts the same job.
- **Assumptions from the request:** no writes to the trip by the agent (E004); chat entry only launches and points to progress (E002 decision text); reuse of read tools only.
- **Assumptions still needing confirmation:** (1) tier: research available to `free` with a daily cap, or `premium`-only like booking — design defaults to *all tiers, 3 starts/day/user, one running run per trip*; (2) the trip page surface: a new **Research tab** (design default) vs a card on Today.

## Evidence Ledger

| Label | Evidence |
|---|---|
| `Local` | Chat turn ceilings: `app/core/config.py:127 agent_recursion_limit=25`, `app/agents/constants.py:25 MAX_LEDGER_STEPS=4`, `context.py:29 max_revisions=1`; round budget history in `specs/agent-tool-round-budget`. |
| `Local` | `AgentRun`/`AgentRunStep` (`app/db/models/agent_run.py:14`, `agent_run_step.py:13`) hold metrics + step structure, no content; `AgentRunRepository.start/finish/add_steps` (`app/repositories/agent_run.py:70/98/124`); background pattern `run_memory_extraction` + `_isolated_factory` (`routers/agent.py:136,352`). |
| `Local` | Store: `open_store` builds `PostgresStore`/`InMemoryStore` with `index=` (`app/memory/store.py:110-140`); namespaces `("users", user_id, kind)`; guard is explicit in `upsert_*` helpers, not a store interceptor (`guard.py:275`, `store.py:205/254/280`). |
| `Local` | Tools: `TOOLS_BY_DOMAIN` planner/concierge (`tools/registry.py:33/45`), `TOOL_METADATA.readOnly` (`:93`); explicit `args_schema` declares injected args (`flight_tools.py:89-105`); no tool uses `InjectedStore`/`InjectedToolCallId`. |
| `Local` | Auth: `CurrentUserDep`, `require_premium` (`app/core/auth.py:114/121`); quota `check_quota` (`routers/agent.py:189`); rate limit `enforce_rate_limit` requires no open transaction (`core/rate_limit.py:44-59`), consumer pattern `routers/feedback.py:48-78`. |
| `Local` | SSE: taxonomy `streaming/events.py`, one canonical `astream` in `streaming/mapper.py:55`, FE mirror `apps/web/src/lib/stream/parseSSE.ts:113` (unknown event → `null`, forward-compatible :253); SSE direct-to-origin, REST via `/api/be` proxy (`techstacks/frontend.md:151`). |
| `Local` | Supervisor entry seams: `_Target` (`supervisor.py:34`), `ALL_SUBAGENTS` (`constants.py:9`), `route_tasks` (`nodes.py:323`), `destinations=` rule (`techstacks/langgraph.md`), suggestions keys (`suggestions.py:27`, `apps/web/messages/en.json:596`), prompt registry pointer flip (`prompts/active.yaml`). |
| `Local` | LLM: `get_agent_llm` falls back silently to the env model when the agent-config row is missing/NULL (`clients/llm.py:75-82`; `docs/solutions/agent/new-agent-config-node-seeds-null-model.md`). |
| `Local` | Identity: web `IdentityProvider` publishes the Supabase `session.user.id` as the id used for `X-User-Id` (`apps/web/src/lib/identity/provider.tsx:11-60`) → REST owner == JWT `sub`. |
| `Local` | PoC (scratch venv, this session): `create_deep_agent(model=FakeLLM, tools=17 concierge read tools, backend=StoreBackend(InMemoryStore, ns=("users","u1","research","t1")), subagents=[SubAgent(...)], middleware=[TodoListMiddleware()])` builds and `ainvoke`s; `uv pip check` clean with deepagents 0.7.15 + langsmith 0.12.6 + langchain-openai 0.3.34. |
| `Upstream` | deepagents 0.7.15 wheel: `create_deep_agent` signature and default middleware order (`graph.py:271-291, 862-938`); `StoreBackend` namespace factory receives `Runtime`, key = absolute path, value `{"content","encoding",...}`, `ls/glob/grep` scan the whole namespace (`backends/store.py:42-87, 208-228, 230-304, 447`); `SubAgent` shares the parent backend and inherits tools/context (`middleware/subagents.py:66-218, 692-700, 760-763`); `RubricMiddleware` activates on `state["rubric"]`, status is private (`middleware/rubric.py:556-568, 639-655, 1262-1272`); `TodoListMiddleware` opt-in since 0.7 (PR #4929); no interrupts unless `interrupt_on` (`graph.py:916-921`); no harness profile for `gpt-5.4-mini` (`profiles/_builtin_profiles.py:140-148`); langsmith imported at runtime, no key needed, tracing off unless `LANGSMITH_TRACING=true`. |
| `Docs` | https://docs.langchain.com/oss/python/deepagents/{overview,quickstart,customization,subagents,backends,middleware,streaming,event-streaming,human-in-the-loop,memory,skills,profiles}; https://reference.langchain.com/python/deepagents/; https://www.langchain.com/blog/deep-agents-v0-7 — version-matched to 0.7.15 (docs default to latest = 0.7.x). |
| `Inference` | `astream_events(version="v3")` projections (`run.subagents`, `run.tool_calls`) are the cleanest progress source, but a BackgroundTask cannot stream to a later-opened SSE connection; an in-process progress bus keyed by run id plus DB snapshot fallback is needed (design §4). |

## Local Findings

- **Relevant files:** `app/agents/{graph,supervisor,nodes,constants,context,suggestions,metrics,prompt_map}.py`, `app/agents/subagents/_base.py`, `app/tools/registry.py`, `app/tools/_base.py`, `app/memory/store.py`, `app/memory/guard.py`, `app/clients/llm.py`, `app/core/{auth,rate_limit,lifespan,agent_config_cache}.py`, `app/routers/{agent,feedback,trips}.py`, `app/streaming/{events,mapper,agent_run,persistence}.py`, `app/repositories/agent_run.py`, `app/db/models/{agent_run,agent_run_step}.py`, `app/db/seed.py`, `app/prompts/{registry.py,active.yaml,supervisor/v13.md}`, `apps/web/src/lib/stream/*`, `apps/web/src/app/trips/[tripId]/page.tsx`, `apps/web/src/lib/identity/provider.tsx`, `eval/adapters/config.py`, `tests/api/agent/test_agent_chat.py:67-86`.
- **Extension points:** `get_agent_llm(name)` + seeded `agent_config` row; `TOOLS_BY_DOMAIN`/`TOOL_METADATA` for a `research` tool selection; `AgentRunRepository` for run/step persistence (`kind="research"`, `channel="research"`); `TurnMetricsHandler` callbacks for ordered steps; `_isolated_factory` for background sessions; `app.state.agent_store` + `agent_checkpointer` shared with the chat graph; `route_tasks` + `destinations=` for a new supervisor target; suggestions keys; SSE event taxonomy + FE parser that ignores unknown events.
- **Conventions to preserve:** routers thin → services → repositories; agents/tools no business logic; `session_scope()`/factory for background; `ToolException` mapping; best-effort metrics never raise into the reply; prompt = new `vN.md` + pointer flip; store built with `index=`; content never in `agent_runs`; JWT on the agent surface; lockstep SSE mirror; `gen:api` for `schema.d.ts`.
- **Reusable as-is:** all read-only tools of planner + concierge (17 concierge tools bound in PoC), `FakeLLM`, `AgentRunRepository`, `TurnMetricsHandler`, `_isolated_factory`, `check_quota`, `enforce_rate_limit`, `CurrentUserDep`, `open_store`, i18n message files, `useAgentStream`-style SSE consumer patterns.
- **Missing locally:** any job/status route (only two `BackgroundTask` call sites); a progress channel between a background run and a later SSE subscriber; a `research` namespace kind with its own guard policy; an `agent_config` row for `trip_research` and its grader; a research tab/card on the trip page; a proposal-apply UI; a `research` entry in the supervisor target enum.

## Upstream Findings

- **Repositories inspected:** `langchain-ai/deepagents` (0.7.15 wheel source), `langchain-ai/langchain` (create_agent middleware), `langchain-ai/langgraph` (Runtime merge, `astream_events` v3).
- **Pattern already present upstream:** the "research agent" reference shape — main agent with `write_todos`, `task()` to isolated subagents, files as the deliverable, rubric grading loop.
- **Areas worth modeling:** subagent spec per research dimension with a *subset* of tools and a short system prompt; `CompositeBackend` keeping `large_tool_results/` on `StateBackend` while `/research/` routes to `StoreBackend`; `on_evaluation` callback → progress event; `name=` on the deep agent for stream attribution.
- **Match to this repo:** high for the agent core (tools already LangChain `@tool`s with async I/O); medium for progress (upstream assumes a live stream consumer in-process).
- **Gaps/uncertainties:** no harness profile for `gpt-5.4-mini` (tool descriptions untuned; the auto-added `general-purpose` subagent must be disabled); `general-purpose` disabling API is `register_harness_profile("openai", HarnessProfile(..., general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False)))` and keys off `ls_provider` of the model instance — verify at implementation on the real `ChatOpenAI` instance.

## Docs Findings

- **Official sources checked:** deepagents docs pages listed in the Evidence Ledger; API reference; v0.7 release post.
- **Version-matched vs latest-stable:** docs track 0.7.x = installed 0.7.15; `TodoListMiddleware` opt-in (0.7.0) confirmed in wheel.
- **Built-ins that support the feature:** StoreBackend (persistent dossier), CompositeBackend (route `/research/` vs scratch), SubAgent isolated mode, RubricMiddleware (self-check with retry), TodoListMiddleware (phase progress), `astream_events(v3)` projections, `interrupt_on` (unused in v1).
- **Recommended APIs:** pass a `BaseChatModel` instance (no Responses-API forcing), `context_schema` dataclass + `ainvoke(context=...)` for per-run user/trip, `state_schema` subclassing `DeepAgentState` if `InjectedState` keys are needed, `name=` for attribution.
- **Caveats:** `store=` must be passed or `StoreBackend(store=)`; namespace factory must not run without `context`; `ls/glob/grep` scan a namespace fully → one namespace per (user, trip); subagent-returned custom state keys merge into the parent (give reducers or keep private); `_rubric_status` is private state; langsmith becomes a runtime import (no key needed); `AnthropicPromptCachingMiddleware` is a no-op on OpenAI.

## Recommendation

- **Primary:** adapt upstream — `deepagents` for the research job only, wired to existing seams (design.md).
- **Why lightest:** one new dependency (already resolves cleanly), zero schema migration (dossier in the store; progress from `agent_run_steps`), zero new tools, no change to the 5 specialists; the supervisor change is a routing hop to a no-LLM launcher node.
- **Why the next-best lost:** (a) hand-rolled second `StateGraph` with a file-store tool set — rebuilds filesystem tools, subagent isolation, rubric loop and todo ledger that deepagents ships and tests; (b) extending the chat turn — ceilings + SSE contract growth; (c) Managed Deep Agents — hosting/identity/LangSmith-key mismatch (intake).
- **What would flip it:** if `general-purpose` subagent cannot be disabled for the OpenAI instance or `StoreBackend` writes turn out to need the memory guard's semantics, fall back to `FilesystemMiddleware(tools=[...])` allowlists and a thin `research_files` service in front of the store.

## Risks, Unknowns, and Follow-Up Questions

- **Technical risks:** background run dies with the process (accepted for v1; status stays `running` → add a stale-run sweep on start: any `research` run older than N min with no steps becomes `failed`); token cost of a multi-subagent run on `gpt-5.4-mini` (cap: `max_iterations=2` rubric, per-subagent `recursion_limit`, tool-result eviction default 20k tokens); dossier poisoning via tool outputs is contained because v1 never feeds dossier text into the chat graph; `agent_runs` must keep holding no content (dossier lives only in the store).
- **Evidence gaps:** progress-bus behaviour under uvicorn `--reload` (dev) and multi-worker (prod) — bus is per-process; poll fallback covers it; `astream_events(v3)` projections not yet exercised against `FakeLLM` (PoC used `ainvoke`).
- **Version uncertainties:** langsmith 0.9.2 → 0.12.6 bump ships with deepagents (app has no direct langsmith import; `langchain-core` allows `<1.0`).
- **Follow-up questions:** answered 2026-09-18 — (1) premium-only (E005); (2) dedicated Research tab (E006).

## Source Pack

- **Local files read:** `techstacks/langgraph.md`, `techstacks/frontend.md:78-170`, `specs/agent-run-trace-detail/design.md`, `docs/solutions/agent/{new-agent-config-node-seeds-null-model,sync-node-breaks-async-only-tools,explicit-args-schema-breaks-tool-injection}.md`, plus the `app/`, `apps/web/`, `eval/`, `tests/` paths listed under Local Findings (via the seam map `scratchpad/local-seams.md`).
- **Upstream repositories or pages checked:** deepagents 0.7.15 wheel source (unpacked); https://github.com/langchain-ai/deepagents/pull/4929; https://www.langchain.com/blog/deep-agents-v0-7
- **Official docs domains or pages checked:** https://docs.langchain.com/oss/python/deepagents/ (overview, quickstart, customization, subagents, backends, middleware, streaming, event-streaming, human-in-the-loop, memory, skills, profiles); https://reference.langchain.com/python/deepagents/

## Evidence Boundary

> Confirmed from artifacts: dependency resolution + `pip check`; `create_deep_agent` build/invoke with `FakeLLM` and 17 registry tools on `StoreBackend(InMemoryStore)`; every seam file:line above; deepagents API signatures from the wheel.
> Inferred from patterns: progress-bus design; cost bounds; that `register_harness_profile("openai", ...)` matches the app's `ChatOpenAI` instance.
> Not checked: `astream_events(v3)` output shape with `FakeLLM`; PostgresStore behaviour with `StoreBackend` (PoC used `InMemoryStore`); Gemini/Anthropic model instances under deepagents.
