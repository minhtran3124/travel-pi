---
slug: trip-research-deep-agent
doc: design
created: 2026-09-18
status: proposed
depends_on: research-brief.md, ESCALATIONS.md (E001 StoreBackend · E002 BackgroundTask + poll + SSE · E003 chat + trip page · E004 propose-only), PR #219 (stack floors)
---

# Design — trip-research-deep-agent

File paths relative to `apps/api/` unless noted.

## 1. Position in the architecture

A **second, independent graph** built with `deepagents.create_deep_agent`, living in a new package
`app/research/`. It shares the process-lifetime checkpointer and store with the chat graph, reuses
the tool registry's read-only tools and the `agent_runs` persistence, and is launched either by a
REST call on the agent (JWT) surface or by a no-LLM launcher node the supervisor routes to.

This is a deliberate, documented exception to `techstacks/langgraph.md` ("no create_agent /
middleware in the top graph"): the top chat graph stays hand-built; the research job adopts the
1.x middleware harness because its needs (file-backed artifact, isolated subagents, rubric loop,
todo ledger) are exactly what that harness standardises — which is the condition the profile's
*Direction* section names. The profile gets a paragraph recording this (Task in wave 4).

```
trip page ──POST /agent/trips/{id}/research──► router ──► ResearchService.start()
chat "research my trip" ──supervisor──► research_launch node ──┘        │
                                                                       ▼
                                          BackgroundTask run_trip_research(run_id, ctx)
                                                                       │
                     agent_runs/agent_run_steps ◄── metrics ◄── deep agent (main + 5 subagents)
                     progress bus (in-process)  ◄── events  ◄──   │ StoreBackend
                                                                   ▼
                                            store ns ("users", uid, "research", trip_id)
                                            /research/*.md   /plan/proposal.json
GET /agent/research/{run_id}          ◄── status + steps + file index (DB + store)
GET /agent/research/{run_id}/stream   ◄── SSE: bus if live, else DB snapshot + poll
GET /agent/research/{run_id}/files/… ◄── file content (store)
POST …/research/{run_id}/revise       ──► same job on the existing dossier with an instruction
```

## 2. Package layout (`app/research/`)

| File | Responsibility |
|---|---|
| `context.py` | `ResearchContext` frozen dataclass: `user_id, trip_id, run_id, language, timezone, tier`. Passed as `context=` to the deep agent; the `StoreBackend` namespace factory and the launcher read it. |
| `state.py` | `ResearchState(DeepAgentState)`: `trip_id: str`, `user_id: str` (plain channels so existing tools with `InjectedState("trip_id")` resolve inside subagents), plus `progress: Annotated[list[dict], _append]` kept private to the parent. |
| `tools.py` | `research_tools()` = union of planner + concierge tools filtered by `TOOL_METADATA[name]["readOnly"]`, minus `EPISODIC_TOOL_NAME` and the clarification tool; grouped per subagent (flights / stays / days / entry-season / budget). No new tool. |
| `prompts.py` | reads `prompts/trip_research/vN.md` (main), `prompts/trip_research_<dimension>/vN.md` (subagents) and `prompts/trip_research_grader/vN.md` through the registry; `active.yaml` gains the pointers. |
| `agent.py` | `build_research_agent(*, store, checkpointer, llm=None, grader_llm=None)`: `create_deep_agent(model=get_agent_llm("trip_research"), tools=..., subagents=[SubAgent(...) ×5], backend=CompositeBackend(default=StateBackend(), routes={"/research/": StoreBackend(store, ns), "/plan/": StoreBackend(store, ns)}), middleware=[TodoListMiddleware(), RubricMiddleware(model=get_agent_llm("trip_research_grader"), max_iterations=2, on_evaluation=...)], context_schema=ResearchContext, state_schema=ResearchState, checkpointer=..., store=..., name="trip_research")`. Registers `HarnessProfile(excluded_tools={"execute"}, general_purpose_subagent=disabled)` for the OpenAI instance. Built once at lifespan (`app.state.research_agent`) and rebuilt with the chat graph on config generation change. |
| `runner.py` | `run_trip_research(run_id, ctx, *, instruction=None, session_factory, agent, bus)`: sync entry point for `BackgroundTask` that drives `asyncio.run(...)`? **No** — FastAPI `BackgroundTask` accepts an `async def`; the runner is `async`, calls `agent.astream_events(..., version="v3")`, publishes progress to the bus, records steps through `TurnMetricsHandler`, and finalises `AgentRun` on an isolated session. Every failure ends in `finish(status="failed", error_type=...)` and a terminal bus event; nothing raises out of the task. |
| `progress.py` | `ProgressBus`: `dict[run_id, list[asyncio.Queue]]` + last-N ring buffer per run, `publish(run_id, event)`, `subscribe(run_id) -> AsyncIterator`, `close(run_id)`. Per-process; documented limitation. |
| `service.py` | `ResearchService`: `start(user, trip_id, instruction=None)` — ownership check (trip.user_id == user.id, via `TripService`), tier/rate gate, "one running per trip" guard (query `agent_runs` kind=research status=running for trip), mints `run_id`, `AgentRunRepository.start(kind="research", channel="research")`, commits, schedules the task; `status(run_id)` — run row + steps summary + file index from the store; `file(run_id, path)`; `latest(trip_id)`; `revise(run_id, instruction)` → new run on the same namespace with the instruction and the previous run id in `meta`. |
| `files.py` | `ResearchFiles(store, user_id, trip_id)`: `list()`, `read(path)`, `write(path, text)` (user edits from the UI), `proposal()` (parsed + validated `/plan/proposal.json`). Uses `store.aget/asearch/aput` with the same `("users", uid, "research", trip_id)` namespace; **no memory guard** (different namespace kind, content never enters the chat graph); path allowlist `^/(research|plan)/[A-Za-z0-9._/-]+$`. |
| `proposal.py` | `Proposal` pydantic schema: `itinerary: list[{day, time, place_id|None, title, notes}]`, `shortlist: list[place_id]`, `flights: list[offer_id]`, `hotels: list[hotel_id]`, `budget_estimate`. `validate_against_db(session)`: every id must exist (places/flight offers/hotels). Deterministic check run **before** the LLM rubric; failure → a `HumanMessage(name="proposal_validator")` with the invalid ids, at most 2 retries. |

## 3. Agent design

- **Main agent** (`trip_research`, prompt v1): given the trip snapshot (`get_trip_summary`), traveller preferences block (existing `search_preferences`, formatted like D2 in MIN-65), language and today's date; writes todos for the five dimensions; delegates each to a subagent via `task()`; reads back their reports from `/research/`; writes `/research/overview.md` and `/plan/proposal.json`; on `instruction` (revise), edits in place with `edit_file` instead of regenerating.
- **Subagents (isolated):**
  | name | tools | writes |
  |---|---|---|
  | `flights` | `search_flights`, `get_airports`, `resolve_date` | `/research/flights.md` |
  | `stays` | `search_hotels`, `check_hotel_availability`, `search_places` | `/research/stays.md` |
  | `days` | `search_places`, `get_route`, `get_city_route`, `get_weather`, `get_climate` | `/research/days/day-N.md` |
  | `entry_season` | `get_visa`, `get_local_tips`, `search_travel_knowledge`, `get_climate` | `/research/entry-and-season.md` |
  | `budget` | `get_trip_budget`, `estimate_trip_budget`, `get_fx_rate` | `/research/budget.md` |
  Each has `TodoListMiddleware()`, its own short prompt, `model` = same instance; tool names are taken from the registry at build time and asserted to exist (a missing name fails the build, not the run).
- **Rubric** (grader prompt v1): every dimension file exists and cites tool-backed facts; every day has meals + ≤3 activities; proposal ids validated; total within trip budget if set; language matches. Deterministic checks (file presence, proposal validation) run in `on_evaluation`-adjacent code before the grader, so the LLM grader never sees a structurally broken dossier.
- **Budgets:** parent `recursion_limit` 120, subagents 60 (via `.with_config` on the compiled subagent — verify API at implementation), rubric `max_iterations=2`, tool-result eviction default. Whole run wall-clock guard 10 min via `asyncio.timeout` → `failed(timeout)`.
- **LLM config:** two new seeded `agent_config` rows: `trip_research` (sibling provider/model) and `trip_research_grader` (in `FAST_AGENTS`). `get_agent_llm` resolution as everywhere.

## 4. Progress and streaming

- Events (BE `streaming/research_events.py`, mirrored in `apps/web/src/lib/stream/research.ts`):
  `research_start{run_id,trip_id}`, `research_phase{todos:[{content,status}]}`, `research_subagent{name,status}`, `research_tool{name,status}`, `research_file{path,bytes}`, `research_eval{iteration,result,explanation}`, `research_done{status,files:[...],proposal:bool}`, `research_error{code,message}`. No message text or tool args cross the wire (same posture as `agent_runs`).
- Sources: `astream_events(v3)` projections (`run.subagents`, `run.tool_calls`, `values.todos`), `RubricMiddleware.on_evaluation`, `StoreBackend` writes detected by diffing the file index after each subagent completes.
- `GET .../stream`: if the bus has the run (live, same process) replay the ring buffer then tail; otherwise emit a snapshot built from `agent_run_steps` + file index and re-poll every 2 s until terminal. Terminal → `research_done`/`research_error` then close.
- Poll: `GET /agent/research/{run_id}` returns `{status, started_at, finished_at, phase (todos), steps_summary{tool_calls, subagents}, files[], proposal_ready, error}`.

## 5. Public contract (agent surface, JWT)

| Method | Path | Notes |
|---|---|---|
| POST | `/agent/trips/{trip_id}/research` | body `{instruction?: str, language?: str}` → 202 `{run_id}`; 403 not owner; 409 a run is already running for the trip; 429 rate limit (`research_start`: 3/day/user, `enforce_rate_limit`) or quota. |
| GET | `/agent/trips/{trip_id}/research` | latest run summary or 404. |
| GET | `/agent/research/{run_id}` | status (above). |
| GET | `/agent/research/{run_id}/stream` | SSE. |
| GET | `/agent/research/{run_id}/files` | index. |
| GET | `/agent/research/{run_id}/files/{path:path}` | content (`text/markdown` or JSON for proposal). |
| PUT | `/agent/research/{run_id}/files/{path:path}` | user edit (allowlisted path). |
| POST | `/agent/research/{run_id}/revise` | `{instruction}` → 202 new `run_id` on the same dossier. |

All under `CurrentUserDep`; ownership by `trip.user_id == user.id` (REST `X-User-Id` is the same Supabase id, `apps/web/src/lib/identity/provider.tsx`). Tier: all tiers in v1 (open question 1 in the brief). Routes stay thin: validation + `ResearchService` + `HTTPException` mapping.

## 6. Chat entry

- `SupervisorIntent.target_agent` gains `"research"`; prompt **v14** documents it ("research/plan the whole trip in depth" → research, needs an active trip; a mere search stays planner). `ALL_SUBAGENTS` gains `"research"`; `route_tasks` unchanged in shape (single agent name). New node `research_launch` registered with `destinations=("reflection", END)`: no LLM; if no `trip_id` → `awaiting_user` + `system_reply("research_needs_trip")`; else calls `ResearchService.start` through the same path the router uses (session from `session_scope()`), replies with `system_reply("research_started")` naming the trip page, sets `current_flow="research"`; reflection skips it via the existing `awaiting_user`-style guard (flag `research_started` in state, LastValue reducer). Suggestion chip key `research.view_progress` (+ `research.start` on `current_flow="planner"` when a trip is active). i18n keys in `apps/web/messages/{en,vi}.json`.
- Tier gating: `research` is not in `PREMIUM_ONLY_SUBAGENTS` (v1). Eval: routing goldens `research-*` (en/vi) with `expected_flow="research"` under a new `research` capability + dataset file.

## 7. Trip page (apps/web)

- New tab **Research** (`trips/[tripId]` tab id `research`): empty state with "Research this trip" (POST), live progress list (SSE via `streamBaseUrl()`, JWT; hook `useResearchStream(runId)` mirroring `useAgentStream` structure), file tree + markdown viewer (`react-markdown` already a dependency? — verify; else render pre-formatted), inline edit for `.md` files (PUT), proposal panel with "Apply to trip" that calls existing REST endpoints (`POST /trips/{id}/items`, shortlist add) through the REST client with `X-User-Id`, one request per item with the existing `Idempotency-Key` whitelist, progress + partial-failure summary.
- `schema.d.ts` regenerated (`gen:api`) after the BE contract lands.

## 8. Data and safety

- No migration. Dossier lives in the store namespace; `agent_runs` row per research run (`kind="research"`, `channel="research"`, `trip_id`), steps via existing table; `meta` on the run's first step carries `{"instruction_present": bool, "revise_of": run_id}` — never the instruction text.
- PII: the user's `instruction` passes through the existing `pii_guardrail` redaction helper before it enters the agent; dossier content is user data, read only by its owner.
- Stale runs: on lifespan start, `research` runs still `running` are marked `failed(error_type="process_restart")`.
- Cost logging: existing token accounting via `TurnMetricsHandler` → `agent_runs` totals per run.

## 9. Testing strategy

- Offline (FakeLLM, `InMemoryStore`, `MemorySaver`): build; scripted parent → `task` → subagent writes a file → proposal validation fails once → retry → done; bus events order; router 202/403/409/429; SSE snapshot path when no bus; file PUT allowlist; launcher node with/without trip; supervisor routing unit test (FakeLLM structured response). Postgres (`make test-docker` variant): `StoreBackend` on `PostgresStore` round-trip.
- Keyed smoke (`eval/research_smoke.py`, not in CI): one real run on a seeded trip; asserts files exist, proposal validates, cost under a cap; report JSON to `eval/reports/`.
- Web: vitest for the SSE parser mirror and the apply flow; Playwright e2e optional.

## 10. Waves (input to writing-plans)

1. Dependency + `app/research/{context,state,tools,agent,prompts}` + seeded agent_config + offline build/invoke tests (no routes).
2. `runner.py`, `progress.py`, `service.py`, `files.py`, `proposal.py`, lifespan wiring, stale-run sweep, tests.
3. Routes + SSE events + FE stream mirror + poll; rate limit; tests.
4. Chat entry (supervisor v14, launcher node, suggestions, i18n, eval goldens) + `techstacks/langgraph.md` exception paragraph.
5. Trip page Research tab + apply flow + `gen:api`; keyed smoke script; docs.

## 11. Alternatives considered

- Progress via DB polling only (no bus): simpler, but 2 s latency on every event and heavier DB reads per open tab; kept as the fallback path instead of the only path.
- One namespace per user with `trip_id` in the path: rejected — `ls/glob/grep` scan the whole namespace.
- `memory=["/memory/AGENTS.md"]` for preferences: rejected — designed for agent-editable memory; preferences are injected as text in the system prompt (existing helper), keeping the memory guard authoritative.
- Bind write tools with `interrupt_on`: rejected by E004.
