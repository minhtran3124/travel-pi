---
slug: agent-run-trace-detail
status: shipped
owner: Minh Tran
created: 2026-09-03
---

# agent-run-trace-detail — Per-step call chain and a run detail page

**Base:** `feat/agent-turn-metrics` (`de438f0`). **Branch:** `feat/agent-run-trace-detail`.
Decisions in `design.md` (reviewed); version-matched evidence in `research-brief.md`.

## Global Constraints

- Every `Verify` / SC check is one pipe-free command under 60s from `apps/api`, run with every
  credential set to EMPTY (an unset var loses to `.env`, a set one wins) and a tmp SQLite URL:
  `env OPENAI_API_KEY= ANTHROPIC_API_KEY= GOOGLE_API_KEY= ORS_API_KEY= LANGFUSE_ENABLED=false
  DATABASE_URL=sqlite:///$(mktemp -d)/x.db ../../.venv/bin/python -m pytest … -q`.
  Never the whole suite; never move `apps/api/.env`.
- **No user content may reach a step row.** `on_tool_start`'s `input_str`/`inputs` and
  `on_chain_end`'s `outputs` are the two reachable sources and both stay unread; `meta` takes a
  scalar allowlist; `error_type` is `type(exc).__name__`, never `str(exc)`.
- **No background task may write a row the request session has flushed but not committed** — that
  deadlocked the parent branch. Steps are written where `finish()` already is.
- Additive schema only; the ORM columns and the migration must agree exactly so SQLite
  `create_all` and Postgres Alembic produce the same shape.
- Metrics collection stays best-effort: no hook may raise into a reply or an SSE stream.
- Same-wave tasks share no files. Stage and commit as SEPARATE commands.

## 1. Motivation

See `design.md` §1. A turn is currently one flat row plus a `by_node` map: it answers what a turn
cost but not what it did — which node ran in what order, under which prompt version, and which
tools succeeded.

## 2. Non-goals

Message text, tool arguments, model output, any user content; retention/rotation; changing the
list page's existing columns; the `usage` API/SSE contract; a nested tree view.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|------|-------------------------|-----------------------|------------|
| SC-1 | Steps are ordered by start, so a node step precedes the children it brackets; LLM steps take their node from `on_chat_model_start` and tool steps from `on_tool_start`'s own metadata | `cd apps/api && env OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/sc1.db ../../.venv/bin/python -m pytest tests/agents/test_turn_metrics_steps.py -q` | exit 0 |
| SC-2 | No user content reaches any step: a marker string passed as tool input, graph output and exception message appears in no field of any step | `cd apps/api && env OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/sc2.db ../../.venv/bin/python -m pytest tests/agents/test_step_content_leak.py -q` | exit 0 |
| SC-3 | The step count is capped and the overflow counted, while the turn totals stay exact | `cd apps/api && env OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/sc3.db ../../.venv/bin/python -m pytest tests/agents/test_turn_metrics_steps.py -k cap -q` | exit 0 |
| SC-4 | Prompt attribution keys on `<node>/assistant`, so the five sub-agents stay distinct, and prompt-less nodes map to an empty list | `cd apps/api && env OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/sc4.db ../../.venv/bin/python -m pytest tests/agents/test_prompt_map.py -q` | exit 0 |
| SC-5 | `prompt_versions` is captured at graph build and exposed on the compiled graph, so it reflects what the graph baked in rather than the current `active.yaml` | `cd apps/api && env OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/sc5.db ../../.venv/bin/python -m pytest tests/agents/test_prompt_versions_snapshot.py -q` | exit 0 |
| SC-6 | `agent_run_steps` and `agent_runs.prompt_versions` exist with the documented shape and the migration round-trips | `cd apps/api && env OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/sc6.db ../../.venv/bin/python -m pytest tests/test_db_models.py tests/db/test_agent_run_steps_migration.py -q` | exit 0 |
| SC-7 | The repository stores and returns steps in `seq` order and `finish` records `prompt_versions` | `cd apps/api && env OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/sc7.db ../../.venv/bin/python -m pytest tests/repositories/test_agent_run_steps_repo.py -q` | exit 0 |
| SC-8 | A real turn on both channels persists its steps alongside the run row | `cd apps/api && env OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/sc8.db ../../.venv/bin/python -m pytest tests/api/agent/test_agent_run_steps_wiring.py -q` | exit 0 |
| SC-9 | The detail page renders the chain in dev, 404s in production and on an unknown id, and links each prompt to its recorded version | `cd apps/api && env OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/sc9.db ../../.venv/bin/python -m pytest tests/api/agent_config/test_agent_run_detail_page.py -q` | exit 0 |

## 4. Tasks

### Task 1.1 — Ordered step capture in the handler (wave 1)

- **Files:** apps/api/app/agents/metrics.py, apps/api/tests/agents/test_turn_metrics_steps.py, apps/api/tests/agents/test_step_content_leak.py
- **Action:** Add a lock-guarded ordered `_steps` list per design.md §4.1. Open a step at start
  (assigning `seq` and `offset_ms` from the handler's `_created` monotonic origin) and close it at
  end (filling `ms`, `status`, tokens, `finish_reason`). `on_chat_model_start` opens an `llm` step
  with node/ns from its `metadata`; `on_llm_end`/`on_llm_error` close it. NEW `on_tool_start`
  opens a `tool` step with the name from `serialized.get("name")` falling back to
  `kwargs.get("name")` and node/ns from **its own** `metadata`; NEW `on_tool_end`/`on_tool_error`
  close it via a `run_id`-keyed map (`on_tool_error` carries neither name nor metadata, so the map
  is mandatory). `on_chain_start` opens a `node` step for the task it already dedupes;
  `on_chain_end`/`on_chain_error` close it and MUST NOT read `outputs`. Add
  `MAX_STEPS_PER_TURN = 200` and a `steps_dropped` counter; totals stay exact when capped. Add
  `steps()`. Do not change `snapshot()`/`public()`. Every hook stays exception-swallowing.
  The leak test drives a marker string through tool `input_str`/`inputs`, chain `outputs` and an
  exception message, then asserts it appears in no field of any step.
- **Criteria:** SC-1, SC-2, SC-3
- **Interfaces:** Consumes: langchain-core 1.4.8 callback hooks (installed). Produces: `apps/api/app/agents/metrics.py` (`steps()`, tool hooks, cap), `apps/api/tests/agents/test_step_content_leak.py`.
- **Verify:** `cd apps/api && env OPENAI_API_KEY= ANTHROPIC_API_KEY= GOOGLE_API_KEY= ORS_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/t11.db ../../.venv/bin/python -m pytest tests/agents/test_turn_metrics_steps.py tests/agents/test_step_content_leak.py tests/agents/test_turn_metrics.py -q`
- **Done:** steps are ordered by start, tools resolve their node, the cap holds, and no marker string survives into a step.

### Task 1.2 — Prompt map and build-time snapshot (wave 1)

- **Files:** apps/api/app/agents/prompt_map.py, apps/api/tests/agents/test_prompt_map.py
- **Action:** New module with `PROMPTS_FOR_NODE: dict[str, list[str]]` keyed on the handler's
  `_node_key` form (`planner/assistant`, `concierge/assistant`, … plus root nodes `supervisor`,
  `reflection`, `plan`, `load_context`, `pii_guardrail`, `summarize`, `synthesize`,
  `synthesis_worker`). Each sub-agent maps to `[<own name>, "communication_style"]`; nodes that
  build no registry prompt map to `[]`. Add `prompt_versions_snapshot(registry)` returning
  `{name: active_version}` for every registered name, and `prompts_for(node_key, snapshot)`
  returning `[{"name", "version"}]`. Tests: the map covers every node key the graph can produce
  (derive the node set from `build_graph`, not a hardcoded list); the five sub-agents are distinct
  and do not collapse onto `assistant`; prompt-less nodes give `[]`; the snapshot covers every
  registry name.
- **Criteria:** SC-4
- **Interfaces:** Consumes: the existing prompt registry API and the graph's node set. Produces: `apps/api/app/agents/prompt_map.py` (`PROMPTS_FOR_NODE`, `prompt_versions_snapshot`, `prompts_for`).
- **Verify:** `cd apps/api && env OPENAI_API_KEY= ANTHROPIC_API_KEY= GOOGLE_API_KEY= ORS_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/t12.db ../../.venv/bin/python -m pytest tests/agents/test_prompt_map.py -q`
- **Done:** SC-4 passes and no sub-agent shares a key with another.

### Task 1.3 — `agent_run_steps` model, migration, repository (wave 1)

- **Files:** apps/api/app/db/models/agent_run_step.py, apps/api/app/db/models/agent_run.py, apps/api/app/db/models/__init__.py, apps/api/alembic/versions/b2d9f4a7c1e8_add_agent_run_steps.py, apps/api/app/repositories/agent_run.py, apps/api/tests/test_db_models.py, apps/api/tests/db/test_agent_run_steps_migration.py, apps/api/tests/repositories/test_agent_run_steps_repo.py
- **Action:** `AgentRunStep(UUIDBase)` with the design §4.3 columns, indexed on `run_id`; add
  `prompt_versions` (JSON, nullable) to `AgentRun`; register the model in `models/__init__.py`.
  Alembic revision `b2d9f4a7c1e8` (`down_revision = "e3b7c5d9a1f4"`) creates the table + index and
  adds the column; `downgrade` reverses both. `AgentRunRepository` gains
  `add_steps(run_id, steps)` (bulk insert, unknown keys ignored, empty list is a no-op) and
  `steps_for(run_id)` (ordered by `seq`); `finish(...)` accepts an optional `prompt_versions`.
  Tests: table + column sets exact; migration upgrade→downgrade round trip copying
  `tests/db/test_rate_limit_migration.py`'s pattern; repo store/read ordering and the no-op case.
- **Criteria:** SC-6, SC-7
- **Interfaces:** Consumes: the existing UUID base model, the session-or-factory repo base, and the current Alembic head. Produces: `apps/api/app/db/models/agent_run_step.py`, `apps/api/alembic/versions/b2d9f4a7c1e8_add_agent_run_steps.py`, `apps/api/app/repositories/agent_run.py` (`add_steps`, `steps_for`).
- **Verify:** `cd apps/api && env OPENAI_API_KEY= ANTHROPIC_API_KEY= GOOGLE_API_KEY= ORS_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/t13.db ../../.venv/bin/python -m pytest tests/test_db_models.py tests/db/test_agent_run_steps_migration.py tests/repositories/test_agent_run_steps_repo.py -q`
- **Done:** SC-6 and SC-7 pass; `alembic heads` prints exactly one head (`b2d9f4a7c1e8`).

### Task 2.1 — Attach the snapshot to the graph and wire step persistence (wave 2)

- **Files:** apps/api/app/agents/graph.py, apps/api/app/routers/agent.py, apps/api/app/streaming/agent_run.py, apps/api/tests/agents/test_prompt_versions_snapshot.py, apps/api/tests/api/agent/test_agent_run_steps_wiring.py
- **Action:** In `build_graph`, evaluate `prompt_versions_snapshot(registry)` once and attach it as
  `compiled.prompt_versions`, mirroring how `extract_memory_llm` is attached — the sub-agent
  prompts are read at build time, so a per-turn read of `active.yaml` would record a version the
  turn did not use. In `agent_chat._finalize`, before the existing explicit `session.commit()`,
  price each step, call `repo.add_steps(run_id, metrics.steps())` and pass
  `prompt_versions=getattr(graph, "prompt_versions", None)` to `finish`. In `record_agent_run`'s
  finalizer, do the same on the isolated factory. Both calls are inside the existing best-effort
  guards; no step write may be issued from a background task. Tests: the compiled graph exposes a
  snapshot covering every registry name; a chat turn and a stream turn each leave ordered step
  rows and a populated `prompt_versions` alongside the run row.
- **Criteria:** SC-5, SC-8
- **Interfaces:** Consumes: `apps/api/app/agents/metrics.py` (1.1), `apps/api/app/agents/prompt_map.py` (1.2), `apps/api/app/repositories/agent_run.py` (1.3). Produces: `apps/api/app/agents/graph.py` (`compiled.prompt_versions`), `apps/api/app/routers/agent.py` (step persistence), `apps/api/app/streaming/agent_run.py` (step persistence).
- **Verify:** `cd apps/api && env OPENAI_API_KEY= ANTHROPIC_API_KEY= GOOGLE_API_KEY= ORS_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/t21.db ../../.venv/bin/python -m pytest tests/agents/test_prompt_versions_snapshot.py tests/api/agent/test_agent_run_steps_wiring.py tests/api/agent/test_agent_runs.py -q`
- **Done:** SC-5 and SC-8 pass and the existing agent-run tests stay green.

### Task 3.1 — The detail page (wave 3)

- **Files:** apps/api/app/routers/dashboard.py, apps/api/app/templates/agent_run_detail.html, apps/api/app/templates/agent_runs.html, apps/api/tests/api/agent_config/test_agent_run_detail_page.py
- **Action:** Add `GET /dashboard/agent-runs/{run_id}` on the same router (the guard is declared at
  router level, so it applies automatically); 404 on an unknown id via the existing NotFound
  handling. Load the run and its steps, compute each bar's left offset and width as percentages of
  the turn span server-side — using `latency_ms`, falling back to `max(offset_ms + ms)` when it is
  null — and render `agent_run_detail.html`: header with the run totals, the waterfall in `seq`
  order (kind badge, node indented when `ns` shows a sub-graph, model or tool name, bar, errors
  marked, a `steps_dropped` note when truncated), cost-by-model, tools, and the prompts used with
  each link carrying `?version=v{N}` so the reader lands on the version that ran. Make the list
  page's `started` cell link here. Tests: 200 in dev with chain rows present, 404 in production
  without credentials, 404 for an unknown id, the no-steps case renders its note, and a prompt
  link contains `?version=`.
- **Criteria:** SC-9
- **Interfaces:** Consumes: `apps/api/app/repositories/agent_run.py` (1.3), plus the existing dashboard guard and prompt page (both already shipped). Produces: `apps/api/app/templates/agent_run_detail.html`, `apps/api/app/routers/dashboard.py` (`agent_run_detail_page`).
- **Verify:** `cd apps/api && env OPENAI_API_KEY= ANTHROPIC_API_KEY= GOOGLE_API_KEY= ORS_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/t31.db ../../.venv/bin/python -m pytest tests/api/agent_config/test_agent_run_detail_page.py tests/api/agent_config/test_agent_runs_dashboard.py tests/api/agent_config/test_dashboard_auth.py -q`
- **Done:** SC-9 passes and the existing dashboard tests stay green.

## 5. Risks

- `finish_reason` is absent offline (FakeLLM has no `response_metadata`), so tests assert the field
  is optional rather than always present.
- `on_tool_end` may carry a `ToolMessage(status="error")` that a future per-tool
  `handle_tool_error` would hide from `on_tool_error`; the step would read `ok`. Noted, not
  handled — no tool sets that today.
- Hooks fire from several threads (sync node callables run via `run_in_executor`), so the seq
  counter and the open-step maps must stay lock-guarded.

## 6. Status Log

- 2026-09-03 — intake complete; the human resolved the one material fork (structure + pointers,
  no content). Design review and Deep research corrected four premises before any code: the
  prompt page renders the LATEST version unless the link pins one; the prompt snapshot must be
  taken at graph build, since sub-agent prompts are read when the graph compiles; every
  sub-agent's inner node is literally `assistant`, so attribution keys on the namespace-qualified
  key; and steps must be ordered at start or a node bar renders below its own children. Committed
  as 5a7ac67 (PLAN held back until ship).

- 2026-09-03 — wave 1: e5188ad (1.1 step capture + tool hooks + cap + leak test), 4033fd7 (1.2
  prompt map + build snapshot), 6c6ad61 (1.3 model, migration b2d9f4a7c1e8, repository).
  Controller re-verify 106 passed, one alembic head, ruff clean. Review: spec pass, quality
  needs_fixes — the `prompt_versions` repo tests pinned a list shape no producer emits, the leak
  test stopped at the handler, and steps could strand as `open`. All three fixed in 37a5a9a.

- 2026-09-03 — wave 2: 74cc359 wires both channels and attaches the build-time snapshot to the
  compiled graph; also widened `prompt_versions` from list to dict on the model and repository,
  which the JSON column had been hiding. 560 passed.

- 2026-09-03 — wave 3: fd05dcb adds the detail page. 619 passed.

- 2026-09-03 — live UAT on the real stack (docker Postgres, a genuine Supabase token, real
  OpenAI). It proved the chain end to end: the parallel `synthesis_worker` fan-out renders as
  overlapping bars and a real `resolve_date` ToolException was captured as an error step. It also
  disproved a claim the branch had accepted: the multi-intent specialist does NOT sit in the
  checkpoint namespace, so per-step prompt attribution is blank there while single-intent turns
  attribute correctly. f3d2b1d corrects the comment and relabels the page's prompts table, which
  had claimed the whole registry snapshot was "prompts used".
  Separately, `alembic upgrade head` failed on Postgres with `DuplicateTable` because four
  repositories call `create_all` on any backend — the deep review's schema-ownership item,
  recorded as a Harness-Delta rather than fixed here.

- 2026-09-03 — SHIPPED. verify_summary --check: SC-1..SC-9 all re-run green; receipt at
  `.review-receipt.json`.
