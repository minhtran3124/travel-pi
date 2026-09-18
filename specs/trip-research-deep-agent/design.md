---
slug: trip-research-deep-agent
doc: design
created: 2026-09-18
revised: 2026-09-18 (v2 — "leverage deepagents, do not rewrite": skills, memory, permissions, rubric-with-tools, thread resume)
status: proposed
depends_on: research-brief.md, ESCALATIONS.md (E001 StoreBackend · E002 BackgroundTask + poll + SSE · E003 chat + trip page · E004 propose-only · E005 premium-only · E006 Research tab), PR #219
---

# Design — trip-research-deep-agent (v2)

File paths relative to `apps/api/` unless noted.

## 0. Principle (owner, 2026-09-18)

Use the deep-agent harness for everything it already does; write code only for what is
*ours* — domain tools (already exist), identity/tier/ownership, run bookkeeping, and the wire to
the web app. v1 of this design had six pieces that re-implemented harness features; v2 removes
them:

| v1 (rewrite) | v2 (harness feature) |
|---|---|
| per-dimension methodology in 6 registry prompts | **Skills** (`SKILL.md` per dimension, progressive disclosure) |
| preferences pasted into `system_prompt`; `memory=` rejected | **Memory** `AGENTS.md` per user, agent-editable |
| `files.py` path allowlist for writes | **Permissions** rules (`deny` writes outside `/research/**`, `/plan/**`, `/memory/**`) |
| `proposal.py` validator injecting a `HumanMessage` retry loop | **RubricMiddleware grader with tools** (`validate_proposal` tool + rubric text) |
| "revise" = new run that re-reads the dossier | **Thread resume**: one checkpointed thread per dossier; revise = next turn |
| stale-run sweep marks `failed` | **Resume from checkpoint** (`ainvoke(None, config)`) + sweep only as last resort |
| custom truncation of big tool outputs | built-in **large-tool-result offloading** + `SummarizationMiddleware` |

## 1. Position in the architecture

A second, independent graph built with `deepagents.create_deep_agent`, in a new package
`app/research/`. It shares the process-lifetime checkpointer and store with the chat graph,
binds the registry's read-only tools unchanged, records runs in `agent_runs`, and is launched
from the agent (JWT) surface or by a no-LLM launcher node the supervisor routes to. The top chat
graph and the 5 specialists stay hand-built; this is the documented exception foreseen in
`techstacks/langgraph.md` *Direction* (wave 4 records it there).

```
trip page ──POST /agent/trips/{id}/research──► router ──► ResearchService.start()
chat "research my trip" ──supervisor──► research_launch ──┘          │
                                                                     ▼
                                        BackgroundTask run_trip_research(run_id, ctx, turn)
                                                                     │  thread = research:{uid}:{trip}
   agent_runs / steps ◄── TurnMetricsHandler ◄── deep agent ─────────┤
   progress bus       ◄── astream_events(v3) + rubric events         │
                                                                     ▼  CompositeBackend
   /skills/**  ← FilesystemBackend(app/research/skills, read-only)   │
   /memory/AGENTS.md ← StoreBackend ns ("users", uid, "research_memory")
   /research/**, /plan/** ← StoreBackend ns ("users", uid, "research", trip_id)
   everything else (large_tool_results, conversation_history) ← StateBackend (thread-scoped)
```

## 2. The agent (`app/research/agent.py`)

```python
def build_research_agent(*, store, checkpointer, llm=None, grader_llm=None):
    model  = llm or get_agent_llm("trip_research")
    grader = grader_llm or get_agent_llm("trip_research_grader")
    backend = CompositeBackend(
        default=StateBackend(),
        routes={
            "/skills/":   FilesystemBackend(root_dir=SKILLS_DIR, virtual_mode=True),
            "/memory/":   StoreBackend(store=store, namespace=lambda rt: ("users", rt.context.user_id, "research_memory")),
            "/research/": StoreBackend(store=store, namespace=lambda rt: ("users", rt.context.user_id, "research", rt.context.trip_id)),
            "/plan/":     StoreBackend(store=store, namespace=lambda rt: ("users", rt.context.user_id, "research", rt.context.trip_id)),
        },
    )
    return create_deep_agent(
        model=model,
        tools=research_tools(),                       # registry read-only tools, no new tool
        system_prompt=registry.get("trip_research"),  # short: role, dossier layout, output contract
        skills=["/skills/"],
        memory=["/memory/AGENTS.md"],
        permissions=[
            FilesystemPermission(operations=["read"],  paths=["/**"], mode="allow"),
            FilesystemPermission(operations=["write"], paths=["/research/**", "/plan/**", "/memory/**"], mode="allow"),
            FilesystemPermission(operations=["write"], paths=["/**"], mode="deny"),   # first match wins
        ],
        subagents=SUBAGENTS,                          # §3
        middleware=[
            TodoListMiddleware(),
            RubricMiddleware(model=grader, tools=[validate_proposal, *fs_read_tools()], max_iterations=2,
                             on_evaluation=progress.on_rubric),
        ],
        backend=backend,
        context_schema=ResearchContext,
        state_schema=ResearchState,
        checkpointer=checkpointer,
        store=store,
        name="trip_research",
    )
```

- `HarnessProfile` registered for the OpenAI instance: `excluded_tools={"execute"}`,
  `general_purpose_subagent=disabled` (no untargeted delegation). Verified path: profile lookup
  keys off `ls_provider:model` of a `BaseChatModel` instance.
- `ResearchContext` (frozen dataclass): `user_id, trip_id, run_id, language, timezone`. Passed
  as `context=`; the namespace factories read it; the grader inherits it.
- `ResearchState(DeepAgentState)`: `trip_id`, `user_id`, `preferences`, `language` — the keys
  the registry tools inject (`search_flights`/`search_hotels` take `InjectedState("preferences")`
  and `("language")`; trip tools take `("trip_id")`). Isolated subagents receive these keys
  because `state_schema` is forwarded to declarative subagents. `todos` stays per agent.
- Built at lifespan next to the chat graph (`app.state.research_agent`), rebuilt on config
  generation change (same trigger as `resolve_travel_graph`).
- Two seeded `agent_config` rows: `trip_research`, `trip_research_grader` (grader in
  `FAST_AGENTS`). Missing rows degrade silently — the KB entry — so the seed is a wave-1 task.

## 3. Skills, subagents, memory, rubric

**Skills (`app/research/skills/`, in git, read-only at runtime):**
`dossier-format/` (file layout, headings, citation rule "every fact names the tool that produced
it"), `flights/`, `stays/`, `day-plans/`, `entry-and-season/`, `budget/`, `proposal/` (schema and
id rules for `/plan/proposal.json`). Each `SKILL.md` ≤ 500 lines, `name` = directory. Only the
name+description index rides in the system prompt; bodies load on activation. Subagents declare
`skills=["/skills/"]` explicitly (custom subagents do not inherit).

**Subagents (isolated, same model instance, each with `TodoListMiddleware()` and `skills`):**

| name | tools (registry names, asserted at build) | writes |
|---|---|---|
| `flights` | `search_flights`, `get_airports`, `resolve_date` | `/research/flights.md` |
| `stays` | `search_hotels`, `check_hotel_availability`, `search_places` | `/research/stays.md` |
| `days` | `search_places`, `get_route`, `get_city_route`, `get_weather`, `get_climate` | `/research/days/day-N.md` |
| `entry_season` | `get_visa`, `get_local_tips`, `search_travel_knowledge`, `get_climate` | `/research/entry-and-season.md` |
| `budget` | `get_trip_budget`, `estimate_trip_budget`, `get_fx_rate` | `/research/budget.md` |

The main agent: reads `get_trip_summary` + `/memory/AGENTS.md`, writes todos, `task()`s the five
subagents, reads their files, writes `/research/overview.md` and `/plan/proposal.json`, and updates
`/memory/AGENTS.md` with durable learnings about how this traveller wants research done
("prefers boutique stays", "skip museums"). On a revise turn it uses `edit_file`, not rewrites.

**Memory:** `/memory/AGENTS.md` per user, seeded once (code, wave 2) from the existing
preference store (`search_preferences`, formatted as in MIN-65 D2) so the first run is not cold;
afterwards the agent owns it. It is read only by the research agent — never by the chat graph —
so the chat memory guard stays the authority for chat memory. A `StoreBackend` policy hook on the
`/memory/` route runs the guard's content rules on write (wave 2), so injection text cannot be
persisted there.

**Rubric (`prompts/trip_research_grader/v1.md`, activated by `state["rubric"]` on every run):**
every dimension file exists and cites tools; each day has meals and ≤ 3 activities; the proposal
passes `validate_proposal`; totals respect the trip budget if set; language matches the request.
`validate_proposal` is the one new tool, **grader-only** (not bound to the agent): it reads
`/plan/proposal.json` through the backend and checks every id against the DB
(places, flight offers, hotels) — deterministic "code computes", surfaced to the grader as
evidence. `max_iterations=2`; the terminal status is read post-run via `aget_state`.

## 4. Runs, threads, progress

- **Thread = dossier.** `thread_id = f"research:{user_id}:{trip_id}"`. The first run is turn 1;
  every "revise" is the next `HumanMessage` on the same thread, so the agent keeps its context
  and the files; the built-in `SummarizationMiddleware` (offloads to `/conversation_history/`)
  bounds history. Each turn still gets its own `agent_runs` row (`kind="research"`,
  `channel="research"`, `trip_id`) for metrics; the row's first step `meta` carries
  `{"turn": n, "revise": bool}` — never text.
- **Runner** (`app/research/runner.py`, `async def`, scheduled with FastAPI `BackgroundTask`):
  `async for` over `agent.astream_events(input, version="v3", config={"configurable": {"thread_id": ...}, "callbacks": [metrics]}, context=ctx)` → publishes progress; wraps in
  `asyncio.timeout(RESEARCH_TIMEOUT_S)`; always finalises the run row on an isolated session;
  never raises out of the task.
- **Resume, not restart.** If the process died mid-run (row `running`, no terminal step), the
  next `POST` for that trip resumes the checkpointed thread with `ainvoke(None, config)` under a
  new run row (`meta.resumed_from`). The lifespan sweep only marks rows `running` for > 30 min
  as `interrupted`.
- **Progress bus** (`app/research/progress.py`): in-process `run_id → (ring buffer, queues)`;
  events are derived, not authored: `run.tool_calls` (tool name + status; for `write_file`/
  `edit_file` the path only), `run.subagents` (name, status), `values.todos` (phase), rubric
  `on_evaluation` (iteration, result), terminal status. No message text, no tool args.
- **SSE** `GET /agent/research/{run_id}/stream`: live from the bus when present, else a snapshot
  from `agent_run_steps` + file index, re-polled every 2 s until terminal.

## 5. Public contract (agent surface, JWT, premium)

| Method | Path | Notes |
|---|---|---|
| POST | `/agent/trips/{trip_id}/research` | `{instruction?, language?}` → 202 `{run_id, thread_turn}`; 403 not owner / not premium; 409 running; 429 `research_start` 3/day/user. First call = turn 1, later calls on the same trip = revise turns. |
| GET | `/agent/trips/{trip_id}/research` | latest run summary (status, turn, files, proposal_ready) or 404 |
| GET | `/agent/research/{run_id}` | status + phase (todos) + steps summary + file index |
| GET | `/agent/research/{run_id}/stream` | SSE (§4) |
| GET | `/agent/research/{run_id}/files/{path:path}` | content via `backend.download_files` |
| PUT | `/agent/research/{run_id}/files/{path:path}` | user edit via `backend.upload_files`; same permission rules evaluated by the backend, so no separate allowlist |

`CurrentUserDep` + `require_premium`; ownership `trip.user_id == user.id` (REST `X-User-Id` is
the Supabase id). Routers thin; `ResearchService` owns the checks and the run bookkeeping.

## 6. Chat entry

`SupervisorIntent.target_agent` + `_Target` gain `"research"`; supervisor prompt **v14** ("research
/ plan the whole trip in depth → research; a plain search stays planner; needs an active trip").
`ALL_SUBAGENTS` gains `"research"`; `PREMIUM_ONLY_SUBAGENTS` gains `"research"` (free tier gets
the existing premium notice through `allowed_subagents`). New node **`research`** (named like a
specialist so the existing `for name in SUBAGENTS` wiring and reflection destinations cover it;
no LLM): no `trip_id` → `awaiting_user` +
`system_reply("research_needs_trip")`; else `ResearchService.start` (own `session_scope()`),
reply `system_reply("research_started")`, `current_flow="research"`. Suggestion keys
`research.view_progress`, `research.start` (+ i18n en/vi). Eval: routing goldens `research-*` en/vi under the existing `routing` capability (see §12).

## 7. Trip page (apps/web)

**Research tab** (E006), locked with an upgrade hint on free tier. Empty state → "Research this
trip"; live progress (`useResearchStream(runId)` over `streamBaseUrl()` with JWT; parser in
`lib/stream/research.ts` mirroring `streaming/research_events.py`); file tree + markdown viewer;
inline edit (PUT); "Revise" box (POST with instruction); proposal panel with "Apply to trip" that
calls the existing REST endpoints (`POST /trips/{id}/items`, shortlist add) via the REST client
with `X-User-Id`, one request per item, partial-failure summary. `gen:api` after the BE lands.

## 8. Data and safety

No migration. `agent_runs` keeps holding structure only; dossier, memory and history live in the
store / checkpointer. `instruction` passes the existing PII redaction before it becomes a
`HumanMessage`. Dossier text never enters the chat graph. Cost accounting through
`TurnMetricsHandler` per run; hard caps: `RESEARCH_TIMEOUT_S=600`, rubric `max_iterations=2`,
agent `recursion_limit` 150 (deepagents sets 9 999 by default — we override via
`.with_config`), subagent `recursion_limit` 60.

## 9. Testing

Offline (`FakeLLM`, `InMemoryStore`, `MemorySaver`): build with the real skills directory; scripted
turn: todos → `task(flights)` → subagent `write_file` → main `write_file` proposal → grader calls
`validate_proposal` (invalid id once) → revision → satisfied; permissions deny a write to
`/skills/x`; second turn on the same thread edits instead of rewriting; runner finalises on
timeout; bus ordering; routes 202/403(owner)/403(premium)/409/429; SSE snapshot path; launcher
node; supervisor routing. Postgres variant: `StoreBackend` on `PostgresStore` round-trip +
checkpoint resume. Keyed smoke `eval/research_smoke.py` (not CI): one real run on a seeded trip
→ files exist, proposal validates, cost ≤ cap.

## 10. Waves (input to writing-plans)

1. Dependency (`deepagents>=0.7.15,<0.8`) · `app/research/{context,state,tools,agent}.py` · skills directory · prompts `trip_research` v1 + grader v1 · seeded agent_config rows · offline build/turn tests.
2. `runner.py`, `progress.py`, `service.py` (start/status/latest/resume), memory seeding + policy hook, lifespan wiring, sweep, tests.
3. Routes + `research_events.py` + FE stream mirror + rate limit + tests.
4. Chat entry (supervisor v14, `research` node, reflection guard, tier gate, suggestions, i18n, eval goldens) + `techstacks/langgraph.md` exception paragraph.
5. Research tab + apply flow + `gen:api` · keyed smoke script · flip `research_enabled` default to true.

Waves 1–3 ship with `research_enabled=false`, so the chat product is untouched until wave 4 is reviewed.

## 11. Alternatives considered

- `response_format=Proposal` (typed structured output) instead of the agent writing
  `/plan/proposal.json`: typed for free, but the proposal would no longer be a file the agent
  can `edit_file` on a revise turn and the user can read in the tree; kept as a fallback if the
  file route proves brittle.
- Progress by DB polling only: kept as the fallback path, not the only one.
- Bind write tools with `interrupt_on` / `permissions mode="interrupt"`: rejected by E004 for v1;
  the harness supports it later without redesign.
- One namespace per user with trip in the path: rejected (`ls/glob/grep` scan a whole namespace).

## 12. Non-replacement guarantee and blast radius (owner requirement, 2026-09-18)

**Goal restated:** add a deep-agent research capability *beside* the existing product. Nothing
that works today changes behaviour; the feature is additive and can be switched off.

### 12.1 What is touched, and how

| Surface | Kind of change | Guard |
|---|---|---|
| `requirements-ai.txt` | **add** `deepagents` (transitive `langsmith` 0.9→0.12) | same gate as PR #219: full suite ×2 interpreters, Docker suite, eval-smoke baseline compare |
| `app/research/**`, `app/research/skills/**`, `prompts/trip_research*/v1.md` | **new** | isolated package; nothing imports it except lifespan, the router and the launcher node |
| `app/agents/supervisor.py` `_Target`, `SupervisorIntent`, prompt **v14** | **modify (routing enum + new prompt version)** | v13 stays on disk; v14 = v13 + one rule + two examples; routing goldens for every existing capability re-run and must be unchanged; the unknown-target fallback already exists |
| `app/agents/constants.py` `ALL_SUBAGENTS` + `PREMIUM_ONLY_SUBAGENTS` | **append** `"research"` | the graph wires `for name in SUBAGENTS: add_edge(name, "reflection")` and `reflection.destinations=(*SUBAGENTS, ...)`, so the launcher node **is named `research`** and registered like a specialist; free tier excludes it through the existing `allowed_subagents` path |
| `app/agents/graph.py` | **add** one node `research` | no existing edge changes |
| `app/agents/nodes.py` reflection | **add** a guard in the shape of `_booking_committed_this_turn` (`_research_started_this_turn`) so a REVISE never re-launches a job | existing guards untouched |
| `app/agents/suggestions.py`, `apps/web/messages/*.json` | **append** keys | existing keys untouched |
| `app/db/seed.py` | **append** two `agent_config` rows | idempotent seed; existing rows untouched |
| `app/core/lifespan.py` | **add** `app.state.research_agent` | build failure is caught and logged; chat graph startup is unaffected; research routes answer 503 |
| `app/streaming/research_events.py`, `apps/web/src/lib/stream/research.ts` | **new** | chat SSE taxonomy and parser untouched; the chat parser already ignores unknown events |
| `app/routers/research.py` | **new** router under `/agent/...` | no existing route changes; `/agent/manifest` and MCP unchanged because `validate_proposal` lives in `app/research/`, **not** in `tools/registry.py` |
| `tools/registry.py`, the 5 specialists, `plan_node`, memory extraction, `pii_guardrail`, summarize, `route_tasks` | **untouched** | asserted by the plan's "unchanged files" list + `blast-radius-check.sh` |
| store / checkpointer | **new namespaces / thread ids** (`("users", uid, "research", trip)`, `("users", uid, "research_memory")`, `research:{uid}:{trip}`) | disjoint from `prefs/procedural/episodes` and from chat thread ids; `_search_kind` and memory guard are not consulted for them |
| `agent_runs` | **new row values** `kind="research"`, `channel="research"` | no schema change; dashboard lists them like any run |
| eval | **add** routing goldens `research-*` under the existing `routing` capability | no TAXONOMY change (a new capability would perturb `eval-compare` against the committed baseline) |
| `techstacks/langgraph.md` | **add** one paragraph | documentation only |
| web | **new** Research tab + hook + parser | existing tabs and the chat widget untouched |

### 12.2 Kill switch

`settings.research_enabled` (default **true** once shipped, **false** during rollout waves 1–4):
when false, the research router returns 404, the launcher node replies
`system_reply("research_unavailable")`, the web tab is hidden, and lifespan skips building the
research agent. Flipping it never touches the chat graph.

### 12.3 Proof obligations carried into PLAN.md

- SC: full BE suite passes with the **same count** as `main` before the feature (additive tests only add).
- SC: eval-smoke per-capability results equal the baseline (routing goldens for planner/concierge/journal/booking/budget unchanged under v14).
- SC: `ALL_TOOLS` names, `/agent/manifest` and the MCP tool list are byte-identical before/after.
- SC: with `research_enabled=false` the whole new surface is invisible (routes 404, tab hidden) and the chat suite is green.
- SC: the launcher never starts a second job in the same turn (reflection guard test).
