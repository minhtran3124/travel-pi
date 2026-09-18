---
slug: trip-research-deep-agent
status: proposed
owner: minhtran3124
created: 2026-09-18
---

# trip-research-deep-agent — deep-agent trip research beside the chat product

## 1. Motivation

A "research this trip" job that runs for minutes, delegates to isolated subagents, keeps a
file-backed dossier the traveller can read/edit across sessions, self-checks against a rubric and
produces a proposal the traveller applies to the real trip. Built on `deepagents 0.7.15` as a
second graph; the chat graph and its 5 specialists are untouched (design §12). Decisions: E001
StoreBackend · E002 BackgroundTask + poll + SSE · E003 chat + trip page · E004 propose-only ·
E005 premium-only · E006 dedicated Research tab.

## 2. Non-goals

- No write tool bound to the research agent; no `interrupt_on` (E004).
- No change to `tools/registry.py`, the 5 specialists, `plan_node`, `route_tasks`, memory
  extraction, `pii_guardrail`, the chat SSE taxonomy or its FE parser.
- No DB migration; no new eval capability (goldens land under `routing`).
- No Managed Deep Agents / LangSmith hosting; no web-crawl tool.
- No worker/queue process; a run dies with the process and is resumed from its checkpoint.

## Global Constraints

- Every wave up to and including wave 6 ships with `settings.research_enabled = False`; only
  Task 7.2 flips the default. With the flag off, no existing behaviour changes.
- Additive only in shared files: `supervisor.py`, `constants.py`, `graph.py`, `nodes.py`,
  `suggestions.py`, `copy.py`, `seed.py`, `lifespan.py`, `config.py`, `main.py`, `active.yaml`,
  `messages/*.json`. Never edit an existing prompt version; new behaviour = new `vN.md`.
- `validate_proposal` lives in `app/research/`, is never registered in `tools/registry.py`, so
  `/agent/manifest` and MCP stay byte-identical.
- Harness features first: skills, memory, permissions, rubric-with-tools, thread resume,
  large-tool-result offload come from deepagents; do not hand-roll them (design §0).
- Multi-parameter signatures: one parameter per line with a trailing comma. Minimal comments:
  no docstring that restates the signature, no repeated rationale.
- Tests run offline with `FakeLLM`, `InMemoryStore`, `MemorySaver`; pin
  `DATABASE_URL=sqlite:///:memory:` in every Verify (the local `.env` reddens tests otherwise).
- Background code never reuses the request session; routers stay thin (validation →
  `ResearchService` → `HTTPException` mapping).
- No message text, tool arguments or dossier content in `agent_runs`, steps, logs or SSE.
- Stage `specs/trip-research-deep-agent/SUMMARY.md` (and `RUN.json`, `events.jsonl`) with every
  commit so the risk hook resolves the `high-risk` lane from this spec.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|------|-------------------------|-----------------------|------------|
| SC-1 | `deepagents` resolves with the pinned stack and imports; `langchain-openai` stays 0.3.x | `cd apps/api && ../../.venv/bin/python -c "import deepagents, langchain_openai; from importlib.metadata import version as v; from packaging.version import Version as V; assert V(v('deepagents'))>=V('0.7.15') and V(v('langchain-openai'))<V('1.0'); print(v('deepagents'), v('langsmith'))"` | exit 0 |
| SC-2 | Tool selection: `research_tools()` contains only registry read-only tools, excludes `list_trips`, `recall_past_trips`, `get_user_preferences`, `parse_nl_query`; every subagent tool name exists in the registry | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/research/test_tools.py -q` | exit 0 |
| SC-3 | Skills and prompts load: each `SKILL.md` has frontmatter `name` equal to its directory and ≤ 500 lines; `registry.get("trip_research")` and `registry.get("trip_research_grader")` return non-empty text at version 1 | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/research/test_skills_prompts.py -q` | exit 0 |
| SC-4 | Seeded `agent_config` rows `trip_research` and `trip_research_grader` exist with the same provider/model as `planner`; `trip_research_grader` is in `FAST_AGENTS` | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/research/test_seed_config.py -q` | exit 0 |
| SC-5 | `build_research_agent` compiles offline with `FakeLLM`; the compiled graph's tool names contain `task`, `write_todos`, `read_file`, `write_file`, `edit_file` and not `execute`; no `general-purpose` subagent is registered | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/research/test_agent_build.py -q` | exit 0 |
| SC-6 | Permissions: a scripted `write_file` to `/skills/x/SKILL.md` returns a permission-denied tool message and no store key is created; a write to `/research/flights.md` succeeds and the store holds key `/research/flights.md` under `("users","u1","research","t1")` | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/research/test_agent_permissions.py -q` | exit 0 |
| SC-7 | A scripted full turn writes `/research/overview.md` and `/plan/proposal.json`; `validate_proposal` reports one unknown place id on the first grade, the agent revises, the second grade is `satisfied`; `aget_state` shows `_rubric_status == "satisfied"` | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/research/test_agent_turn.py -q` | exit 0 |
| SC-8 | A second turn on thread `research:u1:t1` reuses the checkpoint (the `HumanMessage` count is 2) and edits `/research/overview.md` via `edit_file` instead of `write_file` | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/research/test_agent_revise.py -q` | exit 0 |
| SC-9 | Memory: first run seeds `/memory/AGENTS.md` from 2 stored preferences (both lines present); a write containing an injection phrase from the guard's rule set is rejected by the `/memory/` policy hook | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/research/test_memory.py -q` | exit 0 |
| SC-10 | Progress bus: events for one run arrive in publish order, a late subscriber receives the ring buffer first, and `close` ends the iterator; event payloads contain no `content`/`args` keys | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/research/test_progress.py -q` | exit 0 |
| SC-11 | Runner: a scripted run finishes with `agent_runs.status == "completed"`, ≥ 1 step of kind `tool`, and a terminal `research_done` bus event; a run exceeding the timeout finishes `failed` with `error_type == "TimeoutError"` and never raises | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/research/test_runner.py -q` | exit 0 |
| SC-12 | Service: `start` refuses a trip the user does not own (`NotFoundError`), refuses a second start while one is `running` (`ConflictError`), returns a `run_id` otherwise; `latest(trip_id)` returns that run; a stale `running` row older than 30 min is marked `interrupted` by the sweep | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/research/test_service.py -q` | exit 0 |
| SC-13 | Routes with `research_enabled=false`: every `/agent/research*` and `/agent/trips/{id}/research` path returns 404 | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/api/research/test_routes_disabled.py -q` | exit 0 |
| SC-14 | Routes with the flag on: POST → 202 with `run_id`; free tier → 403; foreign trip → 403; second POST while running → 409; 4th start in a day → 429; GET status → 200 with `status`, `files`, `proposal_ready` | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/api/research/test_routes.py -q` | exit 0 |
| SC-15 | SSE: with no bus entry the stream emits `research_start`, a snapshot `research_phase`, then `research_done` and closes; with a live bus it replays the buffer then tails; event names match the FE union | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/api/research/test_stream.py -q` | exit 0 |
| SC-16 | FE parser: `parseResearchSegment` maps each of the 8 event types and returns `null` for an unknown event | `cd apps/web && pnpm exec vitest run src/lib/stream/research.test.ts` | exit 0 |
| SC-17 | Supervisor: "research my trip in depth" (en) and "nghiên cứu kỹ cả chuyến đi giúp mình" (vi) route to `research`; the v13 routing examples still route unchanged under v14 (planner/concierge/journal/booking/budget fixtures) | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/agents/test_supervisor_research_routing.py -q` | exit 0 |
| SC-18 | Chat node `research`: without a trip → `awaiting_user` and the `research_needs_trip` copy; with a trip and premium → one job started and the `research_started` copy; with the flag off → `research_unavailable`; on the free tier the supervisor's existing premium notice is returned and no job starts | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/agents/test_research_node.py -q` | exit 0 |
| SC-19 | Reflection guard: a REVISE verdict after a `research` turn ends the turn without re-entering `research` (start called exactly once) | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/agents/test_reflection_research_guard.py -q` | exit 0 |
| SC-20 | Non-replacement: the tool registry, the specialist package and the chat stream taxonomy are unchanged versus `main` | `git diff --quiet main -- apps/api/app/tools/registry.py apps/api/app/agents/subagents apps/api/app/streaming/events.py apps/web/src/lib/stream/parseSSE.ts` | exit 0 |
| SC-21 | Eval goldens: `research-routing-en-01` and `research-routing-vi-01` exist under `routing` with `expected_flow == "research"` and validate against the taxonomy | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/eval/test_research_goldens.py -q` | exit 0 |
| SC-22 | Lint clean on the API scope | `cd apps/api && ../../.venv/bin/ruff check app scripts tests/research tests/api/research` | exit 0 |
| SC-23 | Web typecheck + lint clean | `cd apps/web && pnpm exec tsc --noEmit && pnpm lint` | exit 0 |
| SC-24 | Research tab: renders the locked state for a free user, the empty state with a start button for premium, and a file list after a mocked status response | `cd apps/web && pnpm exec vitest run src/components/trips/research` | exit 0 |
| SC-25 | Keyed smoke script exists, has a `--dry-run` that lists the seeded trip and exits 0 without a key | `cd apps/api && DATABASE_URL=sqlite:///:memory: OPENAI_API_KEY= ../../.venv/bin/python -m eval.research_smoke --dry-run` | exit 0 |

## 4. Tasks

### Task 1.1 — Dependency and settings (wave 1)

- **Files:** apps/api/requirements-ai.txt, apps/api/app/core/config.py
- **Action:** Add `deepagents>=0.7.15,<0.8` with a comment naming the spec; add settings
  `research_enabled: bool = False`, `research_timeout_s: int = 600`,
  `research_daily_limit: int = 3`, `research_stale_minutes: int = 30`. Reinstall the repo venv
  (`uv pip install --python .venv/bin/python -r apps/api/requirements.txt`) and record the
  resolved `langsmith` version in SUMMARY.
- **Verify:** `cd apps/api && ../../.venv/bin/python -c "import deepagents, langchain_openai; from importlib.metadata import version as v; from packaging.version import Version as V; assert V(v('deepagents'))>=V('0.7.15') and V(v('langchain-openai'))<V('1.0'); from app.core.config import settings; assert settings.research_enabled is False"`
- **Done:** SC-1 passes; `uv pip check --python .venv/bin/python` prints "All installed packages are compatible".
- **Criteria:** SC-1
- **Interfaces:** Consumes the deepagents 0.7.15 floors from research-brief.md. Produces `apps/api/requirements-ai.txt`, `settings.research_*`.

### Task 1.2 — Research context, state and tool selection (wave 1)

- **Files:** apps/api/app/research/__init__.py, apps/api/app/research/context.py, apps/api/app/research/state.py, apps/api/app/research/tools.py, apps/api/tests/research/__init__.py, apps/api/tests/research/test_tools.py
- **Action:** Test-first. `ResearchContext` frozen dataclass (`user_id, trip_id, run_id, language, timezone`); `ResearchState(DeepAgentState)` with channels `trip_id, user_id, preferences, language`; `research_tools()` = planner ∪ concierge tools filtered by `TOOL_METADATA[...]["readOnly"]` minus `EXCLUDED = {"list_trips","recall_past_trips","get_user_preferences","parse_nl_query", EPISODIC_TOOL_NAME}`; `SUBAGENT_TOOLS` dict per design §3 table, resolved by name against the registry with an assertion at import.
- **Verify:** `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/research/test_tools.py -q`
- **Done:** SC-2 passes; `research_tools()` length equals the count printed by the test's registry filter.
- **Criteria:** SC-2
- **Interfaces:** Consumes the tool registry (app/tools/registry.py, read-only, existing). Produces `app/research/tools.py`, `app/research/state.py`, `app/research/context.py`.

### Task 1.3 — Skills directory and prompts (wave 1)

- **Files:** apps/api/app/research/skills/dossier-format/SKILL.md, apps/api/app/research/skills/flights/SKILL.md, apps/api/app/research/skills/stays/SKILL.md, apps/api/app/research/skills/day-plans/SKILL.md, apps/api/app/research/skills/entry-and-season/SKILL.md, apps/api/app/research/skills/budget/SKILL.md, apps/api/app/research/skills/proposal/SKILL.md, apps/api/app/prompts/trip_research/v1.md, apps/api/app/prompts/trip_research_grader/v1.md, apps/api/app/prompts/active.yaml, apps/api/tests/research/test_skills_prompts.py
- **Action:** Write the seven skills (frontmatter `name` = directory, `description` ≤ 1024 chars, body ≤ 500 lines; `dossier-format` fixes file paths and the citation rule; `proposal` fixes the JSON schema `{itinerary:[{day,time,place_id,title,notes}], shortlist:[place_id], flights:[offer_id], hotels:[hotel_id], budget_estimate}`); the short main prompt (role, dossier layout, `task()` per dimension, memory update rule, revise = `edit_file`); the grader prompt (rubric text from design §3, "call `validate_proposal` before deciding"). Add `trip_research: 1` and `trip_research_grader: 1` to `active.yaml`. Test parses every SKILL.md and loads both prompts through the registry.
- **Verify:** `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/research/test_skills_prompts.py -q`
- **Done:** SC-3 passes; `registry.active_version("trip_research") == 1`.
- **Criteria:** SC-3
- **Interfaces:** Consumes design.md §3. Produces `app/research/skills/**`, `app/prompts/trip_research/v1.md`, `app/prompts/trip_research_grader/v1.md`.

### Task 1.4 — Seed agent config rows (wave 1)

- **Files:** apps/api/app/db/seed.py, apps/api/app/agents/constants.py, apps/api/tests/research/test_seed_config.py
- **Action:** Seed `trip_research` and `trip_research_grader` with the provider/model of the `planner` row (never NULL — KB `new-agent-config-node-seeds-null-model`); add `"trip_research_grader"` to `FAST_AGENTS`. Do **not** touch `ALL_SUBAGENTS` in this task.
- **Verify:** `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/research/test_seed_config.py -q`
- **Done:** SC-4 passes on a fresh temp DB and on a DB that already holds the planner row.
- **Criteria:** SC-4
- **Interfaces:** Consumes the existing seeding helpers in app/db/seed.py. Produces `app/db/seed.py` rows trip_research and trip_research_grader, `FAST_AGENTS` entry.

### Task 2.1 — Build the deep agent and the grader tool (wave 2)

- **Files:** apps/api/app/research/agent.py, apps/api/app/research/validate.py, apps/api/tests/research/test_agent_build.py, apps/api/tests/research/test_agent_permissions.py, apps/api/tests/research/test_agent_turn.py, apps/api/tests/research/test_agent_revise.py
- **Action:** Test-first. `build_research_agent(*, store, checkpointer, llm=None, grader_llm=None)` per design §2 (CompositeBackend routes, permissions, subagents from `SUBAGENT_TOOLS` with `skills=["/skills/"]` and `TodoListMiddleware()`, `RubricMiddleware(model, tools=[validate_proposal, read_file], max_iterations=2)`, `context_schema`, `state_schema`, `name="trip_research"`, `.with_config(recursion_limit=150)`); register an OpenAI `HarnessProfile` excluding `execute` and disabling the general-purpose subagent. `validate_proposal` (`app/research/validate.py`): reads `/plan/proposal.json` through the backend for the run's namespace and checks every id against places / flight offers / hotels with `session_scope()`; returns `{"valid": bool, "unknown_ids": [...]}`. Tests script `FakeLLM` tool calls for the permission, full-turn and revise scenarios.
- **Verify:** `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/research/test_agent_build.py tests/research/test_agent_permissions.py tests/research/test_agent_turn.py tests/research/test_agent_revise.py -q`
- **Done:** SC-5, SC-6, SC-7, SC-8 pass.
- **Criteria:** SC-5, SC-6, SC-7, SC-8
- **Interfaces:** Consumes `app/research/tools.py`, `app/research/state.py`, `app/research/context.py`, `app/research/skills/**`, `app/prompts/trip_research/v1.md`, `app/prompts/trip_research_grader/v1.md`, and the existing get_agent_llm resolver. Produces `app/research/agent.py`, `app/research/validate.py`.

### Task 2.2 — Progress bus and research SSE event schema (wave 2)

- **Files:** apps/api/app/research/progress.py, apps/api/app/streaming/research_events.py, apps/api/tests/research/test_progress.py
- **Action:** Test-first. `ProgressBus` (`publish`, `subscribe` async iterator with ring-buffer replay of the last 200 events, `close`, `has(run_id)`); event dataclasses `research_start`, `research_phase`, `research_subagent`, `research_tool`, `research_file`, `research_eval`, `research_done`, `research_error` with a `to_sse()` mirror of the chat events' encoding; a `derive_events(v3_event)` mapper from `astream_events` items (tool name + status, subagent name + status, todos, file path only for `write_file`/`edit_file`).
- **Verify:** `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/research/test_progress.py -q`
- **Done:** SC-10 passes.
- **Criteria:** SC-10
- **Interfaces:** Consumes the existing SSE encoding helpers in app/streaming/events.py (read-only). Produces `app/research/progress.py`, `app/streaming/research_events.py`.

### Task 2.3 — Memory seeding and policy hook (wave 2)

- **Files:** apps/api/app/research/memory.py, apps/api/tests/research/test_memory.py
- **Action:** Test-first. `seed_agents_md(store, user_id)`: if `/memory/AGENTS.md` is absent in `("users", uid, "research_memory")`, write it from `search_preferences` (formatted as MIN-65 D2) via `StoreBackend.upload_files`; `GuardedStoreBackend(StoreBackend)` overriding the write path to run `app/memory/guard.py` content rules and reject with a permission-style error message.
- **Verify:** `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/research/test_memory.py -q`
- **Done:** SC-9 passes.
- **Criteria:** SC-9
- **Interfaces:** Consumes the existing search_preferences helper and memory guard (app/memory). Produces `app/research/memory.py`.

### Task 3.1 — Runner, service, lifespan wiring, stale sweep (wave 3)

- **Files:** apps/api/app/research/runner.py, apps/api/app/research/service.py, apps/api/app/core/lifespan.py, apps/api/tests/research/test_runner.py, apps/api/tests/research/test_service.py
- **Action:** Test-first. `run_trip_research(*, run_id, ctx, instruction, agent, bus, session_factory)` (async): `seed_agents_md`, `astream_events(version="v3")` over `{"messages":[HumanMessage], "rubric": ..., "trip_id","user_id","preferences","language"}` or `None` when resuming, `TurnMetricsHandler` in callbacks, `asyncio.timeout(settings.research_timeout_s)`, finalise via `AgentRunRepository.finish/add_steps` on the isolated factory, terminal bus event, never raises. `ResearchService` (`start`, `status`, `latest`, `resume`, `file`, `write_file`, `sweep_stale`) per design §4–5 using `AgentRunRepository` with `kind="research"`, `channel="research"`, thread id `research:{uid}:{trip}`. Lifespan: when `settings.research_enabled`, build `app.state.research_agent` next to the chat graph inside a try/except that logs and leaves it `None`; run `sweep_stale` once.
- **Verify:** `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/research/test_runner.py tests/research/test_service.py -q`
- **Done:** SC-11 and SC-12 pass; the chat lifespan tests in `tests/api/agent/test_agent_chat.py` still collect the same count.
- **Criteria:** SC-11, SC-12
- **Interfaces:** Consumes `app/research/agent.py`, `app/research/progress.py`, `app/research/memory.py`, `settings.research_*`, and the existing AgentRunRepository, TurnMetricsHandler and isolated-session factory pattern. Produces `app/research/runner.py`, `app/research/service.py`, `app.state.research_agent`.

### Task 3.2 — FE research stream parser (wave 3)

- **Files:** apps/web/src/lib/stream/research.ts, apps/web/src/lib/stream/research.test.ts
- **Action:** Test-first. `ResearchEvent` union mirroring `streaming/research_events.py` (8 types), `parseResearchSegment` (unknown → `null`), `readResearchStream` async generator reusing the SSE framing helpers of `parseSSE.ts` without modifying it.
- **Verify:** `cd apps/web && pnpm exec vitest run src/lib/stream/research.test.ts`
- **Done:** SC-16 passes.
- **Criteria:** SC-16
- **Interfaces:** Consumes `app/streaming/research_events.py` (event schema). Produces `apps/web/src/lib/stream/research.ts`.

### Task 4.1 — Research router, rate limit, SSE endpoint (wave 4)

- **Files:** apps/api/app/routers/research.py, apps/api/app/main.py, apps/api/app/schemas/research.py, apps/api/tests/api/research/__init__.py, apps/api/tests/api/research/test_routes_disabled.py, apps/api/tests/api/research/test_routes.py, apps/api/tests/api/research/test_stream.py
- **Action:** Test-first. Routes per design §5 under `CurrentUserDep` + `require_premium`; `research_start` rate limit via `enforce_rate_limit` (`settings.research_daily_limit`/24 h) in the `feedback_rate_limit` dependency shape; the router is included in `main.py` only when `settings.research_enabled` (else every path is 404). SSE endpoint: bus tail when `bus.has(run_id)`, else DB snapshot + 2 s re-poll until terminal, using the same `StreamingResponse` headers as `/agent/stream`. Pydantic schemas for start/status/file bodies.
- **Verify:** `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/api/research -q`
- **Done:** SC-13, SC-14, SC-15 pass.
- **Criteria:** SC-13, SC-14, SC-15
- **Interfaces:** Consumes `app/research/service.py`, `app/research/progress.py`, `app/streaming/research_events.py`. Produces `app/routers/research.py`, `app/schemas/research.py`.

### Task 4.2 — FE API client and stream hook (wave 4)

- **Files:** apps/web/src/lib/api/research.ts, apps/web/src/components/trips/research/useResearchStream.ts, apps/web/src/components/trips/research/useResearchStream.test.tsx
- **Action:** Test-first. Typed client functions (`startResearch`, `getResearch`, `getLatestResearch`, `getResearchFile`, `putResearchFile`) on the **agent** (JWT) client, never the REST client; `useResearchStream(runId)` mirroring `useAgentStream` structure (direct-to-origin `streamBaseUrl()`, JWT header, reducer over `ResearchEvent`).
- **Verify:** `cd apps/web && pnpm exec vitest run src/components/trips/research/useResearchStream.test.tsx`
- **Done:** hook test passes; `pnpm exec tsc --noEmit` exits 0.
- **Criteria:** SC-23
- **Interfaces:** Consumes `apps/web/src/lib/stream/research.ts`. Produces `apps/web/src/lib/api/research.ts`, `apps/web/src/components/trips/research/useResearchStream.ts`.

### Task 5.1 — Supervisor target, prompt v14, copy, suggestions, eval goldens (wave 5)

- **Files:** apps/api/app/agents/supervisor.py, apps/api/app/agents/constants.py, apps/api/app/prompts/supervisor/v14.md, apps/api/app/prompts/active.yaml, apps/api/app/agents/copy.py, apps/api/app/agents/suggestions.py, apps/api/eval/datasets/routing.json, apps/api/tests/agents/test_supervisor_research_routing.py, apps/api/tests/eval/test_research_goldens.py
- **Action:** Test-first. `_Target` and `SupervisorIntent` accept `"research"`; `ALL_SUBAGENTS` += `"research"`, `PREMIUM_ONLY_SUBAGENTS` += `"research"`; prompt v14 = v13 + the research rule and two examples (en/vi), pointer `supervisor: 14`; `SYSTEM_COPY` keys `research_needs_trip`, `research_started`, `research_unavailable`; suggestion keys `research.view_progress` (flow `research`) and `research.start` (flow `planner`); two routing goldens. The routing test replays every v13 example with a scripted `FakeLLM` structured response and asserts the routed target is unchanged.
- **Verify:** `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/agents/test_supervisor_research_routing.py tests/eval/test_research_goldens.py -q`
- **Done:** SC-17 and SC-21 pass; `tests/agents/test_supervisor*.py` existing files pass unchanged.
- **Criteria:** SC-17, SC-21
- **Interfaces:** Consumes the existing supervisor v13 prompt text. Produces `app/prompts/supervisor/v14.md`, `app/agents/constants.py` research entries, `app/agents/copy.py` research keys, `app/agents/suggestions.py` research keys, `eval/datasets/routing.json` research goldens.

### Task 6.1 — Chat node `research` and reflection guard (wave 6)

- **Files:** apps/api/app/research/launcher.py, apps/api/app/agents/graph.py, apps/api/app/agents/nodes.py, apps/api/tests/agents/test_research_node.py, apps/api/tests/agents/test_reflection_research_guard.py
- **Action:** Test-first. `make_research_node(service_factory)` in `app/research/launcher.py`: no LLM; flag off → `system_reply("research_unavailable")`; no `trip_id` → `awaiting_user=True` + `research_needs_trip`; else `ResearchService.start` under `session_scope()` and `research_started`, `current_flow="research"`, appends an `AIMessage` with `additional_kwargs={"research_started": True}`. Register `builder.add_node("research", ...)` in `graph.py` (the existing `for name in SUBAGENTS` loop wires the edge). In `nodes.py` add `_research_started_this_turn(messages)` beside `_booking_committed_this_turn` and short-circuit reflection the same way.
- **Verify:** `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/agents/test_research_node.py tests/agents/test_reflection_research_guard.py -q`
- **Done:** SC-18 and SC-19 pass; `tests/agents/test_reflection*.py` existing files pass unchanged.
- **Criteria:** SC-18, SC-19
- **Interfaces:** Consumes `app/research/service.py`, `app/agents/copy.py` research keys, `app/agents/constants.py` research entries. Produces `app/research/launcher.py`, `app/agents/graph.py` node research, `app/agents/nodes.py` guard _research_started_this_turn.

### Task 6.2 — Web i18n keys and stack-profile note (wave 6)

- **Files:** apps/web/messages/en.json, apps/web/messages/vi.json, techstacks/langgraph.md
- **Action:** Add suggestion translations `suggestions.research.view_progress`, `suggestions.research.start` and the `TripDetail.research.*` strings the tab will use (locked, empty, start, revise, apply, progress labels); append the "documented exception" paragraph to `techstacks/langgraph.md` *Direction* naming `app/research/` and PR link placeholder.
- **Verify:** `cd apps/web && node -e "const en=require('./messages/en.json'),vi=require('./messages/vi.json');for (const k of ['view_progress','start']) { if(!en.suggestions.research?.[k]||!vi.suggestions.research?.[k]) process.exit(1) }; if(!en.TripDetail.research||!vi.TripDetail.research) process.exit(1)"`
- **Done:** both message files hold the keys; `grep -c "app/research" techstacks/langgraph.md` prints ≥ 1.
- **Criteria:** SC-23
- **Interfaces:** Consumes `app/agents/suggestions.py` research keys. Produces `apps/web/messages/en.json`, `apps/web/messages/vi.json`, `techstacks/langgraph.md` paragraph.

### Task 7.1 — Research tab, file viewer, revise, apply flow (wave 7)

- **Files:** apps/web/src/app/trips/[tripId]/page.tsx, apps/web/src/components/trips/research/ResearchTab.tsx, apps/web/src/components/trips/research/FileViewer.tsx, apps/web/src/components/trips/research/ProposalPanel.tsx, apps/web/src/components/trips/research/ResearchTab.test.tsx, apps/web/src/lib/api/schema.d.ts
- **Action:** Test-first. Add tab id `research` (locked state for free tier, hidden when the BE returns 404 for the feature); `ResearchTab` = empty state → start; progress list from `useResearchStream`; file tree + markdown viewer with inline edit (PUT); revise box (POST with instruction); `ProposalPanel` applies items/shortlist through the existing REST client one request per entry with a partial-failure summary. Regenerate `schema.d.ts` with `pnpm gen:api` against a running API with the flag on.
- **Verify:** `cd apps/web && pnpm exec vitest run src/components/trips/research`
- **Done:** SC-24 passes; SC-23 passes.
- **Criteria:** SC-24, SC-23
- **Interfaces:** Consumes `apps/web/src/lib/api/research.ts`, `apps/web/src/components/trips/research/useResearchStream.ts`, `apps/web/messages/en.json`, `apps/web/messages/vi.json`. Produces `apps/web/src/components/trips/research/ResearchTab.tsx`, `apps/web/src/components/trips/research/FileViewer.tsx`, `apps/web/src/components/trips/research/ProposalPanel.tsx`, `apps/web/src/lib/api/schema.d.ts`.

### Task 7.2 — Keyed smoke script, flag default, docs (wave 7)

- **Files:** apps/api/eval/research_smoke.py, apps/api/eval/README.md, apps/api/app/core/config.py, apps/api/Makefile, Makefile
- **Action:** `eval/research_smoke.py` (`--dry-run` lists the seeded trip and exits 0 without a key; with a key runs one research turn, asserts the dossier files exist, `validate_proposal` is valid, cost ≤ `--max-usd`, writes `eval/reports/research-smoke.json`); `make research-smoke` targets; flip `research_enabled` default to `True`; README section.
- **Verify:** `cd apps/api && DATABASE_URL=sqlite:///:memory: OPENAI_API_KEY= ../../.venv/bin/python -m eval.research_smoke --dry-run`
- **Done:** SC-25 passes; SC-20 and SC-22 pass at the end of the wave.
- **Criteria:** SC-25, SC-20, SC-22
- **Interfaces:** Consumes `app/research/service.py`, `app/research/validate.py`. Produces `eval/research_smoke.py`, `apps/api/Makefile` research-smoke target, `settings.research_enabled` default True.

## 5. Risks

- `register_harness_profile("openai", ...)` may not match the app's `ChatOpenAI` instance (`ls_provider` lookup): fall back to `FilesystemMiddleware(tools=[...])` allowlist and an explicit `general-purpose` `SubAgent` override (Task 2.1 checks both paths).
- `InjectedState("preferences")`/`("language")` inside isolated subagents depends on `state_schema` forwarding; if a key is dropped, wrap the two search tools in `app/research/tools.py` with bound closures (no registry change).
- Supervisor v14 could shift existing routing; the replay test (Task 5.1) and the eval-smoke baseline compare at branch finish are the gates; the flag stays off until wave 7.
- `astream_events(v3)` shape with `FakeLLM` is unverified; Task 2.2's mapper is table-driven so the fixture can be adjusted without touching callers.
- Progress bus is per-process (uvicorn `--reload`, multi-worker): SSE snapshot path covers it.

## 6. Status Log

- 2026-09-18 — plan written from design.md v2 (skills/memory/permissions/rubric/thread resume) and §12 non-replacement guarantees; 14 tasks, 7 waves; flag off until Task 7.2.
