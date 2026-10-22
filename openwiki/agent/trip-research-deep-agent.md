---
type: Subsystem
title: Trip-research deep agent
description: The second, independent LangGraph graph (built with deepagents) that researches one trip into a dossier and a machine-readable proposal. Covers how it is built (per-dimension subagents, skills, store-backed files, write permissions, rubric grader), run bookkeeping and concurrency in ResearchService, the background runner, the in-process progress bus and SSE stream, the premium REST routes, and the chat graph's research launcher node.
tags: [agent, research, deepagents, langgraph, background-runs, sse, premium, rubric]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-25T03:45:43.723Z
sources:
  - id: openwiki-source-f18f564b85852ec3a8a054dc
    resource: repo://apps/api/app/core/lifespan.py
  - id: openwiki-source-1bc8bf59d677c1978cc37404
    resource: repo://apps/api/app/main.py
  - id: openwiki-source-798ba55c4480c62612a305f8
    resource: repo://apps/api/app/research/agent.py
  - id: openwiki-source-0c58839f339358aa0d3a7bf9
    resource: repo://apps/api/app/research/launcher.py
  - id: openwiki-source-1b337a2e95bf1b4210b5072f
    resource: repo://apps/api/app/research/progress.py
  - id: openwiki-source-c96ce73f3b1954acd480222a
    resource: repo://apps/api/app/research/reader.py
  - id: openwiki-source-69b5620a4514fcbadef1ab2e
    resource: repo://apps/api/app/research/runner.py
  - id: openwiki-source-0eca2c2947d58fc87166359c
    resource: repo://apps/api/app/research/runtime.py
  - id: openwiki-source-b842553da9494f6fbfc62431
    resource: repo://apps/api/app/research/service.py
  - id: openwiki-source-eb2fa7f03387ddcbed3d582f
    resource: repo://apps/api/app/research/state.py
  - id: openwiki-source-b382d662352789d3dd40199d
    resource: repo://apps/api/app/research/tools.py
  - id: openwiki-source-78962817c8892c18c792d9cf
    resource: repo://apps/api/app/research/validate.py
  - id: openwiki-source-a57484fe5e6748ebaa29a453
    resource: repo://apps/api/app/routers/research.py
  - id: openwiki-source-ed4231fc18f9da6e736c6abc
    resource: repo://apps/api/app/streaming/research_events.py
generated: { by: "claude-code", at: "2026-09-25T03:45:43.723Z" }
---

# Trip-research deep agent

"Deep trip research" is a long-running job that researches **one concrete trip** end to end: flights, stays, day plans, entry rules and season, and budget. It writes the results into a dossier of Markdown files plus `/plan/proposal.json`, which the traveller can apply to the trip. The agent is **not** part of the chat graph. It is a second compiled graph built with `deepagents.create_deep_agent` (`apps/api/app/research/agent.py`). It shares the chat graph's checkpointer and store but has its own model config, prompt, tools, lifecycle and streaming surface. A run takes minutes, so it always runs in the background: the REST routes and the chat launcher only book a run and return right away.

The feature is behind a kill switch, `research_enabled`, which defaults to on (see [Configuration and environments](../architecture/configuration-and-environments.md)). It is premium-only in both the REST surface and the chat routing.

## Building the agent

Lifespan builds the agent once. The build runs in its own `try` block after the chat graph, so a research build failure never affects chat:

1. `app.state.research_bus = ProgressBus()` is always set, and `app.state.research_agent` starts as `None`.
2. When `research_enabled` is on, `build_research_agent(store=..., checkpointer=...)` builds the agent on the **same** store and checkpointer instances as the chat graph. Next, `ResearchService(...).sweep_stale()` flips abandoned `running` rows to `interrupted`. Finally, `set_research_runtime(agent, bus)` publishes the pair in a process-level holder (`app/research/runtime.py`).
3. If the build fails, the error is logged and the agent stays `None`. The REST routes then answer `503`, and the chat node declines.

The runtime holder exists because the chat graph is built **before** the research agent. The chat graph's `research` node therefore cannot capture the agent at build time. Instead, it reads the holder when it runs, so the chat path and the REST routes drive **one** agent through **one** bus. The agent resolves its models at build time (`get_agent_llm("trip_research")` and `get_agent_llm("trip_research_grader")`). It is not rebuilt when the per-agent config changes, so a model change needs a restart (see [LLM providers and per-agent configuration](llm-providers-and-agent-config.md)).

What `build_research_agent` assembles:

- **System prompt** `registry.get("trip_research")` (see [Prompt registry](prompt-registry.md)). The per-dimension methodology is in `SKILL.md` files under `app/research/skills/` (`flights`, `stays`, `day-plans`, `entry-and-season`, `budget`, `proposal`, `dossier-format`), which the agent reads through a read-only `/skills/` route.
- **Five isolated subagents**, one per research dimension: `flights`, `stays`, `days`, `entry_season` and `budget`. Each gets a short delegation description, its own tool set, the skills route, a todo list and three middlewares, explained below. A harness profile keyed on the model's own provider (`ls_provider`) removes the `execute` tool and disables the general-purpose subagent. Keying on the provider rather than a hard-coded `"openai"` means the profile also matches `FakeLLM` in tests.
- **A `CompositeBackend`** that routes paths by prefix. `/skills/` maps to a read-only filesystem view of the skills directory. `/research/` and `/plan/` map to a `StoreBackend` in the namespace `("users", user_id, "research", trip_id)`. `/memory/` maps to a `GuardedStoreBackend` in `("users", user_id, "research_memory")`. Anything else lives in graph state.
- **Filesystem permissions**, where the first matching rule wins: reads are allowed everywhere, writes are allowed only under `/research/**`, `/plan/**` and `/memory/**`, and every other write is denied.
- **A rubric grader.** `RubricMiddleware` runs the grader model with at most two iterations. It has two tools: `read_file` over the same backend, and `validate_proposal`, which loads `/plan/proposal.json` and checks every place, flight-offer and hotel id against the database through the repositories. `validate_proposal` is bound only to the grader and is never registered in the tool registry.
- **Limits.** The main agent is capped at `recursion_limit=150`. deepagents offers no declarative per-subagent limit, so subagents inherit the same 150 (the source comments explain why).

### Tools: the registry, read-only and filtered

`app/research/tools.py` adds no new tools. It selects tools from the existing registry, so `/agent/manifest` and the MCP surface stay unchanged. The main agent gets only `get_trip_summary`, which is its source for the destination, dates and party. Each subagent gets a named subset, for example `flights` → `search_flights` and `resolve_date`, and `budget` → `get_trip_budget` and `estimate_trip_budget`. Every tool is checked **at import time**:

- it must be read-only according to `TOOL_METADATA`;
- it must not be in `EXCLUDED` (`list_trips`, `recall_past_trips`, `get_user_preferences`, `parse_nl_query` and the episodic tool);
- it must not expose `trip_id` or `user_id` as model-visible arguments. The run owns those ids and the model cannot know them. A live run once invented `trip_id="current"` and died, and `expense_summary` is left out for the same reason.

The tools read `trip_id`, `user_id`, `preferences` and `language` from state through `InjectedState`. `ResearchState` extends `DeepAgentState` with those four keys. Each key uses the reducer `keep_run_constant`, because several subagents run in parallel and write the same value back in one step. With plain last-value channels, that raised `InvalidUpdateError`.

### Middleware that makes shared tools work for research

- **`_ToolErrorsToMessages`** turns any tool exception into an error `ToolMessage`, using the same `describe_tool_failure` verdict as the chat graph. Without it, a single ambiguous date would end a turn that represents minutes of work. The middleware implements both the sync and the async hooks, because the runner streams asynchronously while offline tests call `invoke`.
- **`_ToolIdsToContent`** appends the ids the proposal must cite (`place_id`, `offer_id`, `hotel_id`) to the model-facing content of the places, flights and hotels tools. Those tools normally keep ids only in the side-panel artifact. Adding the ids here leaves chat and MCP output unchanged.
- **`_WriteInTravellerLanguage`** adds a line to every model call's system message that names the traveller's language, taken from `state["language"]`. A subagent sees only the task text the main agent wrote, and one live run produced English dimension files under a Vietnamese summary.

## Run bookkeeping: `ResearchService`

`app/research/service.py` owns ownership checks, the one-run-per-trip rule, the `agent_runs` rows, resuming, dossier file access and the stale-run sweep. It always works through a session factory and never reuses a request session. A run is an `agent_runs` row with `kind` and `channel` both set to `research`. Its thread id and conversation id are both `research:{user_id}:{trip_id}`, so each trip has one checkpoint thread and a revise is the next turn on it (see [Observability, turn metrics and cost](observability-and-metrics.md)).

`start(user_id, trip_id)` books a run:

1. If the trip is not the caller's, it raises `NotFoundError`.
2. Inside **one transaction** it takes a transaction-scoped advisory lock named `research_start:{user_id}:{trip_id}` (`app/db/locks.py`; a no-op on SQLite), then checks for a `running` row. Two concurrent starts for the same trip are therefore serialized: the second one sees the first one's row.
3. If a `running` row is **live on this process's bus**, it raises `ConflictError` (409). If the row is not live, the process that drove it died (the bus is in-memory and uvicorn runs one worker). That row is marked `interrupted`, and the new run **resumes** its checkpointed thread.
4. Only a fresh start spends the per-user daily cap: `research_start` bucket, `research_daily_limit` per 24 h, via `RateLimitRepository.hit`. The cap is spent only after the lock shows this start wins, so the losing side of a double click never costs a slot, and a resume does not spend it again. A start over the cap raises `RateLimitError` (429). The cap is enforced here, rather than on a route, because all three launch paths (REST start, REST revise, chat) book through `start`.
5. The run is opened on the bus **before** commit. Otherwise a concurrent start could see the committed row, find it not live, and resume it a second time.

`launch(...)` then drives the booked run. It never raises. For a resume it drops the new instruction and continues the checkpointed turn, unless the checkpoint shows no unfinished turn, in which case it runs the fresh turn instead. `chat_state` reports what the chat should say instead of booking: `running`, `completed`, `needs_review`, or `None`. `completed_summary` returns the traveller-facing `/research/summary.md` of the latest completed run.

## The background runner

`run_trip_research` (`app/research/runner.py`) drives one turn and never lets an exception escape, because it runs as a FastAPI `BackgroundTask` or an `asyncio` task:

- On a fresh turn it seeds `/memory/AGENTS.md` from the chat preference store if the file is missing. It then builds the input: the instruction (or a default), an optional `Departing from:` line and a `Language:` line, plus the grader rubric in `state["rubric"]` and the four injected state keys. A resume passes `None` so the agent continues its checkpoint.
- It streams `agent.astream_events(..., version="v3", context=ResearchContext)` under `asyncio.timeout(research_timeout_s)`. `derive_events` maps each stream item to progress events that it publishes on the bus.
- After the stream finishes, it reads the grader's terminal verdict (`_rubric_status`) from the checkpoint. `RubricMiddleware` never changes the reply for a rejected dossier, so the checkpoint is the only place to learn that the grader gave up.
- `_finalize` writes the terminal row and steps on the isolated factory. On failure it adds an error step with `error_type`, on a resume it stamps `resumed_from`, and when a verdict exists it adds a `rubric` step. It then publishes a terminal `research_done` or `research_error` event and **closes** the run on the bus. A timeout or any exception finalizes the run as `failed`. A cancelled task keeps its `running` row, so the next `start` resumes it without spending the cap.

## Progress bus and the SSE stream

`ProgressBus` (`app/research/progress.py`) is per-process and not durable. For each run it keeps a ring buffer of the last 200 events and a set of subscriber queues. A late subscriber replays the buffer, then follows live publishes. `close` sends a sentinel to every subscriber and releases the buffer, but keeps a closed **tombstone**. `has(run_id)` reports a closed run as gone, so the SSE route falls back to the DB snapshot, and a closed run is never brought back. Subscribers are deliberately not checked for closure after the replay: a run that finishes mid-replay has already put its terminal event in the queue, and stopping early would drop it.

Events (`app/streaming/research_events.py`) carry only projected progress, never message text, tool arguments or file contents: `research_start`, `research_phase` (todos), `research_subagent`, `research_tool` (name and status), `research_file` (path and byte count), `research_eval`, and the terminal `research_done` (status, file list, `proposal_ready`) and `research_error`. `derive_events` is table-driven and maps any shape it does not recognize to `[]`.

`GET /agent/research/{run_id}/stream` follows the bus while the run is live. Otherwise it emits a snapshot and polls the row every 2 s until a terminal status arrives. A `running` row with no live channel is reported as `interrupted` instead of being polled forever. The stream therefore **always ends with a verdict**, including when the run finishes between the `has` check and the subscription.

## REST surface

`app/routers/research.py` is mounted only when `research_enabled` is on (`app/main.py`), so with the flag off every path returns 404. Every route requires the JWT user and `require_premium`, and a run owned by someone else reads as 404.

| Route | Behaviour |
|---|---|
| `POST /agent/trips/{trip_id}/research` | Book a run (202, returns `run_id` and `thread_turn`). The body has `instruction`, `language` and `origin`. The instruction is PII-redacted before the background launch. A trip that is not the caller's gives 403. 409 if a live run exists, 429 over the daily cap, 503 if the agent is unavailable. |
| `POST /agent/research/{run_id}/revise` | The next turn on the same trip thread, booked through the same `start`. |
| `GET /agent/trips/{trip_id}/research` / `GET /agent/research/{run_id}` | Status, dossier file index, `proposal_ready` (only when completed), `thread_turn` and `review` (`passed` / `needs_review` / `null`, from the recorded grader verdict). A `running` row that is not live shows as `interrupted` without a DB write. |
| `GET` / `PUT /agent/research/{run_id}/files/{path}` | Read or overwrite one dossier file. Markdown reads go through `reader_view`, which strips tool-name citations, labelled ids, bare-UUID lines and the trailing `## Ids` section. The JSON proposal keeps its ids so the client can apply it. |
| `GET /agent/research/{run_id}/stream` | Progress SSE, as described above. |

## Entry from chat: the `research` node

The supervisor can route to `research` (see [Agent graph and supervisor routing](graph-and-supervisor.md)). `make_research_node` (`app/research/launcher.py`) makes **no model call**. In order, it:

1. replies `research_unavailable` when the flag is off, or when `service.runnable` is false because no agent was built;
2. asks which trip is meant (`research_needs_trip`, with `awaiting_user`) when there is no active trip;
3. answers the current state (`research_in_progress`, `research_completed` or `research_needs_review`, followed by the dossier summary) when the trip already has a live or finished run. It never re-runs the research, because a chat re-run would be an empty revise that spends the cap. Revising is done from the Research tab;
4. asks for the departure point (`research_needs_origin`) when `trip_facts` holds no `origin`, because the origin is never inferred;
5. otherwise calls `start`. It schedules `launch` with `asyncio.create_task`, holding a strong reference so the task cannot be garbage-collected, and replies `research_started`. A `ConflictError` gives the same "started" reply without a second driver, and a `RateLimitError` gives `research_limit_reached`.

The launcher's reply carries `research_started` or `research_status` in `additional_kwargs`. Reflection ends such a turn, so a REVISE cannot book a second job. The stream mapper surfaces the reply as a terminal node. All the reply text is English source copy localized through `system_reply` (see [Agent state, runtime context and reply language](state-context-and-language.md)). The web client's side of all this is in [Trip research UI](../frontend/trip-research-ui.md).

## Tests

`tests/research/` builds the agent with `FakeLLM` and covers: the build, permissions, subagent tools and the import-time guards (`test_tools.py`, `test_registry_snapshot.py`, `test_tool_ids.py`); state reducers; the runner's terminal states; the bus (`test_progress.py`); resume and orphan handling (`test_resume.py`); concurrent starts (`test_service_concurrency.py`); memory seeding and the guard; the reader view; and the language middleware. `tests/api/research/` covers the routes, the flag-off 404s (`test_routes_disabled.py`) and the SSE stream. `FakeLLM` never serializes content blocks to a provider, so only the keyed `eval/research_smoke.py` exercises a real provider end to end (see [Agent evaluation harness](../testing/agent-eval-harness.md)).
