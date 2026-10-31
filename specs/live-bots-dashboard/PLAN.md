---
slug: live-bots-dashboard
status: shipped
owner: Minh Tran
created: 2026-10-29
github: epic #304 (children #312 #313 #314 #315 #316, theme #310 via PR #311)
---

# Live Instances Dashboard Implementation Plan

**Goal:** An **Instances** page (URL `/dashboard/bots`) under `/dashboard` that shows the chatbot **containers** running right now as big mascot cards, and inside each card the **agents** working on the turns that container is serving, with the phase each agent is in. Refreshed every 3 s. Follows `apps/api/DESIGN.md` (default theme LIGHT, dark and Nightfall stay selectable).

## The model (confirmed by the owner)

| Term | Meaning |
|---|---|
| **Instance** | One container (`api-1`, `api-2`, `worker`). Several gunicorn/uvicorn processes in one container are the same instance. An instance serves many conversations at once. The UI says "instance" (ticket #344) so "bot" stays free for chatbot personas; code identifiers keep `bot` (see ADR 0002). |
| **Agent** | A graph participant inside a turn: the supervisor, then specialists (planner, concierge, journal, booking, budget; research), up to 3 in parallel. |
| **Phase** | classify -> specialist -> tools -> reflection. |

The page draws one mascot card per **instance**, never one per agent run. Agents appear as small mascots inside their instance's "agents at work" area, grouped by turn, each with a phase stepper. The earlier version of this plan (one card per `agent_runs` row, no schema change) is superseded and wrong.

## Architecture (no database writes in the chat path)

```
chat/stream/research turn --callback--> LiveRegistry (in memory, per process)
                                              | snapshot()
 heartbeat task (own session, off-loop, ~3 s) v
                        bot_heartbeats  (one row per instance_id + pid)
                                              |
 bots_service.aggregate()  (group by instance_id, merge processes)
                                              |
 GET /dashboard/bots.json  <--poll 3 s--  GET /dashboard/bots (Jinja page)
```

- Identity: `app/core/instance.py` (`BOT_INSTANCE_ID` > `RENDER_INSTANCE_ID` > hostname; role `web` default or `worker`).
- The registry is fed by a LangChain `BaseCallbackHandler` added to the graph config. It only touches memory.
- The registry snapshot rides inside the heartbeat row (`snapshot` JSON), so live phases need no other storage.

## Verified current state (checked in code on this branch, base `github/main` 2f65b5ee)

| Claim | Result |
|---|---|
| `agent_runs` has no instance column | True (`app/db/models/agent_run.py`; no `instance`/`host` field). No migration touches it. |
| `agent_run_steps` are written only when a turn finishes | True. Chat: `_finalize` in `app/routers/agent.py` (~244-290) calls `finish()` then `add_steps()` then `session.commit()`; stream: `app/streaming/agent_run.py`; research: `app/research/runner.py` at end. While a turn runs the row has `current_flow` NULL, zero counters, no steps. Live phases are stored nowhere. |
| Graph node names | Confirmed in `app/agents/graph.py`: `pii_guardrail`, `load_context`, `summarize`, `supervisor`, `plan` (HITL gate before booking), `planner`, `concierge`, `journal`, `booking`, `budget`, `research` (launcher, off unless `research_enabled`), `synthesis_worker`, `synthesize`, `reflection`. Edges: START -> pii_guardrail -> load_context -> summarize -> supervisor -> (route_tasks) -> one specialist, or `plan`, or `Send("synthesis_worker", ...)` xN -> synthesize -> reflection. Every specialist -> reflection. |
| `agents/metrics.py` hooks | `TurnMetricsHandler` is a per-turn `BaseCallbackHandler` (`run_inline = True`, `raise_error = False`, thread lock). It already reads `metadata["langgraph_node"]`, `["langgraph_checkpoint_ns"]`, `["specialist"]` in `on_chain_start`, `on_chat_model_start`, `on_tool_start`; tool name from `serialized["name"]`. The new registry handler reuses exactly these seams and the same swallow-everything discipline. |
| Config seams | Chat and stream both use `_config()` (`routers/agent.py:100`, called at 242 and 466) with `"callbacks": callbacks() + [metrics]`. Research builds its own config in `app/research/runner.py:291` with `"callbacks": [metrics]`. So the registry handler is added in `_config()` and in the research runner config (two places, not three). |
| Dashboard plumbing | `app/routers/dashboard.py` router has `dependencies=[Depends(get_current_dashboard_user)]` (line 57), so new routes are guarded automatically; HTML requests redirect to `/dashboard/login`, JSON gets 401. `base.html` already carries a `daylight` theme block; PR #311 makes it the server-rendered default. Nav tabs and the lang switcher (`?lang=`, `supported_languages`) live in `base.html`. |
| Schema creation | Lifespan runs `Base.metadata.create_all` on SQLite only (`app/core/lifespan.py:39`); Postgres is Alembic-only, latest revisions are in `alembic/versions/`. |

### Drift (what the epic and issues claim vs the code)

1. **Outdated: the worker, Redis and gunicorn landed in PR #302.** Original finding, kept for history: **No Arq worker, no Redis, no gunicorn on this base.** #312 says "start the heartbeat from the Arq worker startup" and the epic talks of a `worker` bot and gunicorn processes. On `github/main` the image runs a single `uvicorn app.main:app` (`apps/api/Dockerfile` CMD); `grep -rniE "arq|redis|gunicorn"` over Dockerfile, compose files, requirements, `app/` finds nothing. Research runs in-process: `app/research/launcher.py` does `asyncio.create_task` in the web process. The multi-process, worker and Redis topology exists only on the unmerged `github/feat/prod-deploy-sim` line. Decision (ASSUMPTION): implement the web heartbeat now; make the heartbeat starter a reusable function `start_heartbeat(role)` so a worker entrypoint calls it once that topology lands; support `BOT_ROLE=worker` and test it, but do not invent a worker process. On this base, research agents therefore show inside the `web` instance that launched them. The (instance, pid) key and the merge-per-instance aggregation already handle multi-process containers.
2. **Parallel specialists are not nodes named after the specialist.** In multi-intent turns they run as `synthesis_worker` nodes (via `Send`) and the specialist identity comes from `metadata["specialist"]`, not `langgraph_node`. Single-intent turns run the node named `planner`/`concierge`/... directly. The mapping must read `specialist` first, then fall back to the node name.
3. **Phase mapping, concrete.** classify = `pii_guardrail|load_context|summarize|supervisor`; specialist = the named specialist nodes, `research`, `synthesis_worker`, `synthesize`, `plan`; tools = any `on_tool_start` (phase back to specialist at `on_tool_end`); reflection = `reflection`. Supervisor is itself an agent in the classify phase. Sub-agents are ReAct subgraphs, so one specialist alternates specialist <-> tools several times in a turn.
4. **Namespace dedupe.** `TurnMetricsHandler` dedupes chain starts by `checkpoint_ns` because subgraphs re-emit them; the registry handler must do the same (key by `run_id`, ignore starts whose node is already open for that ns) or one agent shows up twice.
5. **HITL resume.** A `resume` turn is a new HTTP request and a new registry turn; the registry does not carry state across them (the old `interrupted` status exists only for research).
6. **Heartbeat DB handles.** The engine uses SQLAlchemy defaults (`app/db/engine.py`: `pool_pre_ping`, default QueuePool, no explicit sizing); the pool budget work (`DB_LOCK_POOL_SIZE`) is also only on `feat/prod-deploy-sim`. The heartbeat takes one pooled connection for about a millisecond per beat, never holds it between beats.
7. **`ENVIRONMENT`** is `Settings.environment` with `is_production` (`app/core/config.py:263`), usable for the seed-script refusal.

## Tasks

Waves: 1 = #312 (+ PR #311 merged first or in parallel, independent), 2 = #313 and #314 (parallel; both need only #312), 3 = #315 (needs #314 JSON shape and #311), 4 = #316 (needs all).

### #312 Instance identity and heartbeat

- [ ] Failing tests first (SQLite): identity precedence (`BOT_INSTANCE_ID` > `RENDER_INSTANCE_ID` > hostname), role default and `BOT_ROLE=worker`; upsert idempotency (same `(instance_id, pid)` twice = one row, `last_seen` moves); `list_live(since)` window; `prune(before)`; task start/stop removes its row; a raising DB call is logged and swallowed and the loop keeps beating.
- [ ] `app/core/instance.py`; model `app/db/models/bot_heartbeat.py` (`instance_id`, `pid`, `role`, `host`, `started_at`, `last_seen`, `snapshot` JSON; PK `(instance_id, pid)`; ISO-string timestamps like the other tables; import it in `app/db/models/__init__.py` so `create_all` sees it); Alembic revision after the current head (check `alembic heads` first).
- [ ] `BotHeartbeatRepository` (`upsert`, `list_live`, `prune`) in `app/repositories/`, own short session per call like the other repositories.
- [ ] Heartbeat task in `lifespan` (started after the engine/schema step, cancelled and row deleted on shutdown); own session; DB calls via `asyncio.to_thread`; snapshot from a provider hook defaulting to `{}`.
- [ ] Settings `bot_heartbeat_enabled` (default true, off in the test settings so `make test` stays zero-config) and `bot_heartbeat_interval_seconds` (3).

Verify:
```bash
cd apps/api
../../.venv/bin/python -m pytest tests/core/test_instance.py tests/repositories/test_bot_heartbeat.py tests/core/test_heartbeat_task.py -x -q
../../.venv/bin/ruff check app/core app/db app/repositories
```
Migration: `alembic upgrade head` then `downgrade -1` on a scratch Postgres if Docker is up; otherwise state it was not run and rely on the SQLite `create_all` test.

### #313 Live agent-phase registry

- [ ] Failing tests first: handler fed recorded fake events (node starts with `langgraph_node`/`specialist`/ns metadata, tool start/end); two parallel specialists via `synthesis_worker`; turn removed on success, error and `asyncio.CancelledError`; snapshot size cap (turns and agents); no message text or full ids in the snapshot; a turn through the handler performs zero DB writes (engine event listener counts statements).
- [ ] `app/agents/live_registry.py`: thread-safe, `start_turn/finish_turn/set_phase/set_tool`, `snapshot()` -> `{turns:[{run_id (short), conv (short label), kind, started_at, agents:[{agent, phase, tool, since}]}]}`.
- [ ] Callback handler (same file or `app/agents/live_handler.py`), `raise_error = False`, every hook wrapped in try/except, no DB, no logging of payloads.
- [ ] Wire into `_config()` in `app/routers/agent.py` (chat + stream) and the research runner config; always `finish_turn` in the existing `finally` paths, not only in `_finalize`.
- [ ] Register `snapshot` as the heartbeat provider from #312.

Verify:
```bash
cd apps/api
../../.venv/bin/python -m pytest tests/agents/test_live_registry.py tests/agents/test_metrics.py tests/api -k "agent" -x -q   # narrow to agent router tests, not the whole suite
../../.venv/bin/ruff check app/agents app/routers/agent.py app/research
```

### #314 Instances data endpoint

- [ ] Failing tests first: two processes of one instance merge into one instance; `online` <= 10 s, `stale` <= 60 s, older dropped; role mapping; empty list; JSON 401 and HTML redirect without login; `Cache-Control: no-store`; no full ids or message text.
- [ ] `app/services/bots_service.py` and `GET /dashboard/bots.json` (`include_in_schema=False`) returning `{generated_at, bots:[{id, name, role, status, processes, uptime_s, turns:[{conv, kind, agents:[{agent, phase, tool, elapsed_s}]}], agent_count}], counts}`.
- [ ] `counts` = instances online, busy, agents working, turns in flight, matching the hero strip.

Verify:
```bash
cd apps/api
../../.venv/bin/python -m pytest tests/services/test_bots_service.py tests/api/agent_config/test_bots_endpoint.py tests/api/agent_config/test_agent_runs_dashboard.py -x -q
../../.venv/bin/ruff check app/services/bots_service.py app/routers/dashboard.py
```

### PR #311 Default light theme (issue #310)

Already open and independent; confirm it is merged or rebase onto it before #315. Verify: `pytest tests/api/agent_config/test_dashboard_default_theme.py`.

### #315 Instances page

- [ ] Failing tests first: logged-in render 200 with hero strip, empty state ("No instances reporting") server-rendered, filter chips, polling hook for `/dashboard/bots.json` at 3000 ms; no login = redirect; `?lang=vi` strings.
- [ ] Route `GET /dashboard/bots`, `app/templates/bots.html` extending `base.html`, nav entry beside Agent runs. Read `apps/api/DESIGN.md` first; use tokens only (paper palette by default, correct in dark and Nightfall).
- [ ] One card per instance: large mascot (online, busy, stale/greyed), name, role badge, uptime, process count; "agents at work" area with a mini mascot per agent (planner pin, concierge bell, journal pencil, booking ticket, budget coin, research magnifier, supervisor), phase stepper, tool name, elapsed; agents of one turn grouped. SVG shapes ported from the demo file `/tmp/claude-1000/-home-minhtran-Documents-minh-tran-projects-travel-pi/566d19f4-ef76-4f32-b449-ad6c8c48196b/scratchpad/live-bots.html`; its numbers and one-card-per-run layout are NOT the model.
- [ ] JS: 3 s poll, pause when `document.hidden`, pause button, keyed DOM updates, client elapsed ticker, role and agent-kind chips, quiet error state keeping the last good cards, `textContent` only. Offline instances grey out then disappear (server drops after 60 s).
- [ ] A11y: `role="img"` + `aria-label`, state as text not only faces, `:focus-visible`, `prefers-reduced-motion`; one column and no horizontal scroll at 390 px.

Verify:
```bash
cd apps/api
../../.venv/bin/python -m pytest tests/api/agent_config/test_bots_page.py tests/api/agent_config/test_agent_runs_dashboard.py -x -q
../../.venv/bin/ruff check app/routers/dashboard.py
```
Then run the app on SQLite, seed, and look at `/dashboard/bots` at desktop and 390 px in light, plus one in dark.

### #316 Demo seed script and UAT

- [ ] Failing tests first: refuses under `ENVIRONMENT=production` (non-zero exit, nothing written); second run leaves the same row count; `--clear` removes only demo rows.
- [ ] `apps/api/scripts/seed_bots.py`: instances `api-1`, `api-2` (two processes each), `worker`; snapshots covering every agent kind and phase, tagged demo; `--animate` moves agents through phases and occasionally takes a bot offline; `--clear`.
- [ ] UAT: SQLite app with `DASHBOARD_BASIC_USER/PASSWORD` and a >= 32-byte `DASHBOARD_SECRET_KEY`; screenshots desktop and 390 px (light) plus one dark, one short GIF; publish under `pr-<N>/` on `pr-assets` and embed in the PR body under `## Test recording`.

Verify:
```bash
cd apps/api
../../.venv/bin/python -m pytest tests/scripts/test_seed_bots.py -x -q
../../.venv/bin/ruff check scripts/seed_bots.py
```

## Files

| File | Change |
|---|---|
| `app/core/instance.py` | Create (#312) |
| `app/db/models/bot_heartbeat.py`, `app/db/models/__init__.py`, `alembic/versions/<new>_add_bot_heartbeats.py` | Create/Modify (#312) |
| `app/repositories/bot_heartbeat.py` | Create (#312) |
| `app/core/lifespan.py`, `app/core/config.py` | Modify: heartbeat start/stop, two settings (#312) |
| `app/agents/live_registry.py` | Create (#313) |
| `app/routers/agent.py` (`_config`), `app/research/runner.py` (config) | Modify: add handler, finish turn in `finally` (#313) |
| `app/services/bots_service.py` | Create (#314) |
| `app/routers/dashboard.py` | Modify: `/bots.json`, `/bots` (#314, #315) |
| `app/templates/bots.html`, `app/templates/base.html` (nav), EN/VI dashboard strings | Create/Modify (#315) |
| `scripts/seed_bots.py` | Create (#316) |
| `tests/...` per task above | Create |

## Risks

1. **Chat-path overhead.** The handler runs inline (`run_inline`) on the event loop for every chain/tool event. Keep it O(1) with a plain lock and dict updates, no I/O, no formatting of payloads; cap turns and agents per snapshot; a test asserts zero DB statements. Raise nothing into the turn.
2. **Heartbeat write rate.** 3 s interval x (4 web processes + 1 worker) = about 1.7 upserts/s total. One tiny row per process, upsert by primary key, no index beyond the PK plus `last_seen`. Prune old rows opportunistically in the same task, not per request. Interval is a setting.
3. **Extra pooled connection.** Each beat borrows a connection for about a millisecond and returns it; never held between beats and never taken from a request session. With the default pool it cannot starve requests; revisit once the pool-budget work from `feat/prod-deploy-sim` lands (count the heartbeat in the per-process budget).
4. **Migration.** New table only, no change to existing tables; downgrade drops it. Postgres is Alembic-only, so a missing migration would break the heartbeat on Postgres while SQLite tests stay green: the heartbeat task must tolerate a missing table (log once, retry) so a deploy ordering slip cannot take the API down.
5. **Event-loop blocking.** All heartbeat DB calls go through `asyncio.to_thread` (sync SQLAlchemy). A slow DB must delay only the heartbeat, never a chat turn; shutdown cancels the task with a short timeout.
6. **Drift on this base** (see Drift 1): no worker process exists yet, so the `worker` instance is demo/seed-only until the production topology merges. Real research agents appear under the web bot.
7. **Stale registry entries.** A turn that never reaches `finally` (hard kill) disappears with the process, since its heartbeat stops and the instance goes stale then drops; also expire registry turns older than a ceiling (for example 15 min) to guard leaks.
8. **Privacy / XSS.** Short labels only (`conv` = a short hash prefix, never the full id, user id, email or text); Jinja autoescape plus `textContent`; tests assert raw ids and message text never appear in JSON or HTML.
9. **Style drift.** The demo is a different look; port shapes and behaviour only and check against `DESIGN.md` tokens in all three themes.
