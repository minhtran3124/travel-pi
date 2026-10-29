---
slug: live-bots-dashboard
status: planned
owner: Minh Tran
created: 2026-10-29
github: epic #304 (children #305, #306, #307)
---

# Live Bots Dashboard Implementation Plan

**Goal:** A "Live bots" page under `/dashboard` showing one mascot card per agent turn running right now (chat, stream or research): flow, step, elapsed, tokens, LLM calls, refreshed every 3 s. Follows `apps/api/DESIGN.md` (dark, warm coral), not the demo's light ink look. No change to how runs are written, no schema change, no migration.

**Architecture:** `AgentRunRepository.live_runs(now)` (query) -> a small `live_bots_service` (row -> bot DTO) -> `GET /dashboard/live-bots.json` and server-rendered `GET /dashboard/live-bots` (`live_bots.html`, vanilla JS poller). Both routes sit behind the existing router-level `get_current_dashboard_user` guard. A seed script (`scripts/seed_live_bots.py`) drives the UAT.

**Key conventions:**
- Run tests from `apps/api/` with `../../.venv/bin/python -m pytest <file> -x -q` (use the owner's read-only venv). Related tests only; the full suite runs once in the Final check stage.
- Dashboard test pattern: `tests/api/agent_config/test_agent_runs_dashboard.py` (fresh app + `Settings(dashboard_*)` + `create_session_token`; secret >= 32 bytes).
- Never expose a full `user_id` or email. Escape everything inserted into HTML (Jinja autoescape; in JS use `textContent`, never `innerHTML` with data).
- Look-and-feel reference (mascot SVGs, state faces, stepper, chips): `/tmp/claude-1000/-home-minhtran-Documents-minh-tran-projects-travel-pi/566d19f4-ef76-4f32-b449-ad6c8c48196b/scratchpad/live-bots.html`. Port shapes to dashboard tokens; its numbers are simulated.

## Verified current state (checked in code at github/main)

| Epic claim | Result |
|---|---|
| `agent_runs` has `status`, `current_flow`, `channel`, `started_at`, `llm_calls`, `llm_errors`, tokens (`app/db/models/agent_run.py`) | True. Also `finished_at` (ISO string), `kind`, `created_at` (UUIDBase mixin), `user_id` (plain string, no FK). Timestamps are ISO-8601 **strings**; compare as strings. |
| `status` in running / interrupted / completed / failed | True. Writers: `start()` -> `running`; chat/stream/research finish -> `completed`/`failed`; `sweep_running_before` -> `interrupted` (research only, `app/research/service.py`). |
| `channel` = chat, stream, research | True: `"chat"` (`routers/agent.py:235`), `"stream"` (`:459`), `RESEARCH_CHANNEL="research"` (`research/service.py:38`). `kind` is separate (`turn`/`resume` for chat, `research`). |
| `agent_run_steps` has `tool_name`, `node`, `status`, `error_type` | True, plus `seq`, `kind` (`llm`/`tool`/`node`), `ms`, `offset_ms` (`db/models/agent_run_step.py`). Step status values seen: `ok`, `error`. |
| Repository `app/repositories/agent_run.py` | True. `steps_for(run_id)`, `running_for`, `sweep_running_before` exist; no `live_runs` yet. |
| Routes in `app/routers/dashboard.py` (`/agent-runs`), guard `app/core/dashboard_auth.py` | True. The router has `dependencies=[Depends(get_current_dashboard_user)]`, so new routes are guarded automatically. HTML requests redirect to `/dashboard/login`; JSON requests get 401 (handler in `app/core/errors.py`). Nav tabs live in `app/templates/base.html` (~line 1086). |

### Drift (the epic and issues are optimistic here)

1. **Running rows are mostly empty.** For chat and stream, `finish()` and `add_steps()` run only at turn end (`routers/agent.py` `_finalize`, `streaming/agent_run.py`); research also writes steps at the end (`research/runner.py:214`). While a turn is `running`: `current_flow` is NULL, `llm_calls`/tokens are 0, and **no `agent_run_steps` rows exist**. So flow, current step, stage and live counters cannot be read from the DB for an in-flight run. The epic puts "any change to how runs are written" out of scope, so the plan degrades honestly: bot = `generic` (research channel -> `research`), stage 0, counters 0, with a tooltip explaining. Seeded rows (#307) carry flow and steps so the full UI can be demonstrated. This is the main risk. ASSUMPTION: do not change writers.
2. **`interrupted` is research-only.** Only the research stale sweep sets it. HITL plan approval in chat ends the turn as `completed`. Mapping `interrupted` -> `waiting` stays as the issue says, but real `waiting` bots will be research runs.
3. **`retrying` has no per-step retry signal.** Retries are LangGraph `RetryPolicy` inside a node (`app/agents/retry.py`); a step is recorded `error` only after attempts exhaust. So `retrying` = latest step `error` with a retryable `error_type` while run is still `running`. Rare in real data. Reuse the predicate in `app/agents/retry.py` if cheap, else a small allowlist (timeout, rate limit, connection).
4. **Stage mapping** from graph node names (`agents/graph.py`): 0 classify = `pii_guardrail|load_context|summarize|supervisor`; 1 specialist = `planner|concierge|journal|booking|budget|research|plan`; 2 tools = any `kind="tool"` step; 3 reflection = `reflection|synthesize|synthesis_worker`. Confirm the recorded `node`/`ns` strings against a real recorded run before locking the map.
5. **No research timeout on the row**: `stale` uses `settings.research_timeout_s` (600; `research_stale_minutes`=30 also exists) from `app/core/config.py`, applied to all channels as one documented threshold.
6. `ENVIRONMENT` is `Settings.environment` (`development|production|test`) with `is_production` (`config.py:263`); the seed script uses it.
7. Repo methods open their own `self._session()`; follow that. `status` is indexed; no `(status, started_at)` index needed for a capped query.

## File Structure

| File | Responsibility | Create/Modify |
|---|---|---|
| `app/repositories/agent_run.py` | `live_runs(now, limit=50, grace_s=8)`, latest-step batch lookup, `done_today` count | Modify |
| `app/services/live_bots_service.py` | Row -> bot DTO, stage, state, anonymised label, counts | Create |
| `app/routers/dashboard.py` | `GET /live-bots.json`, `GET /live-bots` | Modify |
| `app/templates/live_bots.html` | Page (extends `base.html`), SVG mascots, stepper, chips, poller | Create |
| `app/templates/base.html` | Nav tab "Live bots" beside Agent Runs | Modify |
| dashboard EN/VI string catalog (locate in #306) | New strings | Modify |
| `scripts/seed_live_bots.py` | Idempotent demo seed, `--clear`, `--animate`, prod refusal | Create |
| `tests/repositories/test_agent_run_live.py` | Repo query tests | Create |
| `tests/services/test_live_bots_service.py` | Mapping tests | Create |
| `tests/api/agent_config/test_live_bots_endpoint.py` | JSON endpoint + auth | Create |
| `tests/api/agent_config/test_live_bots_page.py` | Page render + auth + hooks | Create |
| `tests/scripts/test_seed_live_bots.py` | Idempotency + prod refusal | Create |

## Wave Plan

| Wave | Tasks | Depends on |
|---|---|---|
| 1 | #305 data endpoint | none |
| 2 | #306 page | #305 JSON shape |
| 3 | #307 seed + UAT | #305, #306 |

---

## Task #305: Live-runs data endpoint

- [ ] Failing tests first (SQLite): per-flow bot mapping (planner, concierge, journal, booking, budget, research channel, unknown -> `generic`); `interrupted` -> `waiting`; retryable-error latest step while running -> `retrying`; finished <= 8 s ago included as `done`/`failed`, older excluded; `stale` past `research_timeout_s`; cap 50 newest first; anonymised user label; JSON 401 / HTML redirect without login; `Cache-Control: no-store`.
- [ ] `live_runs(now)`: one query `status IN (running, interrupted) OR finished_at >= now-8s`, `started_at` desc, `limit(50)`; one batched query for the latest step per run (no N+1).
- [ ] DTO: `{id (first 8 chars), bot, state, stage, step_label, elapsed_s, tokens, llm_calls, user_label, channel, stale}`. User label = `user-` + short hash prefix, never the raw id or email.
- [ ] Response `{generated_at, bots, counts:{running,waiting,retrying,done_today}}`; `done_today` = completed since UTC midnight via its own count query (not capped).
- [ ] Route with `Cache-Control: no-store`, `include_in_schema=False`.

**Verify:**
```bash
cd apps/api
../../.venv/bin/python -m pytest tests/repositories/test_agent_run_live.py tests/services/test_live_bots_service.py tests/api/agent_config/test_live_bots_endpoint.py tests/api/agent_config/test_agent_runs_dashboard.py -x -q
../../.venv/bin/ruff check app/repositories/agent_run.py app/services/live_bots_service.py app/routers/dashboard.py
```

## Task #306: Live bots page

- [ ] Failing tests first: logged-in render 200 with hero strip, empty state ("No bots running"), filter chips, polling hook (`/dashboard/live-bots.json`, 3000 ms); no login -> redirect; VI strings with `?lang=vi`.
- [ ] Template extends `base.html`; read `DESIGN.md` first and reuse its tokens/components. Mascot SVGs ported from the demo, each with `role="img"` + `aria-label`; state also as text.
- [ ] Inline JS: 3 s poll, stop when `document.hidden`, pause button, keyed DOM updates (no flicker), client-side elapsed ticker, chips filter, quiet error state keeping last good cards. Data via `textContent` only.
- [ ] CSS: `prefers-reduced-motion` disables sway/shake/typing; `:focus-visible`; one column and no horizontal scroll at 390 px.
- [ ] Nav tab beside Agent Runs.

**Verify:**
```bash
cd apps/api
../../.venv/bin/python -m pytest tests/api/agent_config/test_live_bots_page.py tests/api/agent_config/test_agent_runs_dashboard.py tests/api/agent_config/test_login_template.py -x -q
../../.venv/bin/ruff check app/routers/dashboard.py
```
Then run the app on SQLite, seed, open `/dashboard/live-bots` and look at it at desktop and 390 px.

## Task #307: Seed script and UAT

- [ ] Failing tests first: refuses under `ENVIRONMENT=production` (non-zero exit, nothing written); second run leaves the same row count (ids from `deterministic_uuid("live-bots", ...)`); `--clear` removes only demo rows (tagged by `user_id` / `conversation_id` prefix).
- [ ] Rows in running/interrupted/failed/just-finished states for every bot kind with realistic flow, tools, counters and steps.
- [ ] `--animate`: every few seconds finish some runs and start others; Ctrl-C safe.
- [ ] UAT: local app on SQLite with `DASHBOARD_BASIC_USER/PASSWORD` and a >= 32-byte `DASHBOARD_SECRET_KEY`; seed; log in; desktop and 390 px screenshots per state; one short GIF; publish under `pr-<N>/` on `pr-assets`, embed in the PR body under `## Test recording`.

**Verify:**
```bash
cd apps/api
../../.venv/bin/python -m pytest tests/scripts/test_seed_live_bots.py -x -q
../../.venv/bin/ruff check scripts/seed_live_bots.py
```

## Risks

1. **Real in-flight runs carry little data** (Drift 1): real traffic may show generic bots with zero counters; only seeded data shows the full UI. Follow-up outside this epic: write `current_flow` and steps incrementally.
2. **Polling load**: each open tab queries every 3 s. Query is capped at 50 and `status` is indexed; hidden tabs pause.
3. **Privacy**: tests assert raw `user_id` and email never appear in JSON or HTML.
4. **XSS**: tool and node names come from the DB; autoescape plus `textContent`.
5. **String timestamps**: mixing naive and aware or `Z` vs `+00:00` breaks string compares; normalise to UTC and test both forms.
6. **Style drift**: the demo is light ink; port shapes and behaviour only, verify against `DESIGN.md`.
7. **Test isolation**: each new test builds its own app and DB, as `test_agent_runs_dashboard.py` does.
