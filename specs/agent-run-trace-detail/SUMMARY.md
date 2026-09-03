# agent-run-trace-detail — Summary

Lane: high-risk
Confidence: high
Reason: the block-mode hard gate `data-loss/migration` fires (a new `agent_run_steps` table plus an additive `prompt_versions` column on `agent_runs`, with an Alembic revision), and `public-contract` fires on the new `GET /dashboard/agent-runs/{id}` route. Plus flags data model, existing behavior (the turn handler starts recording per-step rows on every request) and multi-domain (agents/metrics, db, repositories, routers, templates, tests). The one material fork — whether to persist message/tool content — was resolved by the human at intake, so confidence is high.
Flags: data model, public contract, existing behavior, multi-domain
Affects: apps/api/app/agents/metrics.py (per-step capture + tool hooks), app/db/models/agent_run_step.py + agent_run.py (new column), alembic (new revision), app/repositories/agent_run.py, app/routers/dashboard.py + templates/agent_run_detail.html, app/prompts/registry.py (read-only use), tests/{agents,api/agent_config,db,repositories}
Input-type: change request
Route: high-risk — design.md → research-brief.md → PLAN.md → branch `feat/agent-run-trace-detail` (off `feat/agent-turn-metrics`, since `agent_runs` exists only there) → subagent-driven-development
Escalate: no (content-vs-structure fork resolved at intake)

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> hiện tại thì chỉ có log dc llm calls, tokens, cost, latency. Toi muốn log nhiều hơn vd như
> prompt system là gì, chain gọi ntn, ... Hiện tại ở dashboard chỉ có view dạng list, hãy suy nghĩ
> và update với việc click to view detail với nhiều thông tin quan trọng hợn, chi tiết hơn
>
> (human, intake fork — how much to store) "Cấu trúc + con trỏ, không nội dung": record per-step
> structure (which node, which model, which prompt name + version, tokens/cost/ms per call, which
> tool ran and its status, finish_reason, the reflection decision) and link out to
> `/dashboard/prompts` to read the exact system prompt text that was used. Do NOT persist message
> text, tool arguments or model output — the PII posture from #118/#129 stays as it is.

## What changed

A turn now records its ordered call chain, and the dashboard renders it.

- **Capture:** `TurnMetricsHandler` opens a step when work starts and closes it when it ends, so a
  node span sorts above the children it brackets. It gains the three tool hooks it never had; a
  tool's node comes from `on_tool_start`'s own metadata, because the chain map holds only the
  outermost run per namespace. Capped at 200 steps with a dropped counter, and steps whose close
  hook never fires are swept to `unfinished` at turn close.
- **Attribution:** a static node→prompts map keyed on the namespace-qualified node key (every
  sub-agent's inner node is literally `assistant`, so a bare-name key would collapse all five),
  plus a `prompt_versions` snapshot taken **at graph build** — the sub-agent prompts are read when
  the graph compiles, so a per-turn read of `active.yaml` would record a version the turn never used.
- **Storage:** `agent_run_steps` (kind, node, ns, model, prompts, tokens, cost, offset/duration,
  status, tool name, meta) plus `agent_runs.prompt_versions`, written where `finish()` already is
  on both channels — never from a background task, which is what deadlocked the parent branch.
- **The page:** `/dashboard/agent-runs/{id}` renders the chain as a waterfall with cost by model,
  the tools that ran, and the prompt versions, each link carrying `?version=` so it opens the
  version that ran rather than the latest.

Five tasks over three waves, each independently reviewed.

### Intake findings

- **The prompt text does not need storing.** Prompts already live in a versioned registry
  (`app/prompts/<name>/v<N>.md` + `active.yaml`) and a dashboard already renders them at
  `/dashboard/prompts/{name}`. Recording `name -> version` per run is a stable pointer that is
  smaller than the text, diffable, and cannot drift from what actually shipped. This satisfies
  "prompt system là gì" without copying prose into the database.
- **Node → prompt mapping is static and knowable**: every node resolves its prompt through
  `registry.get("<name>")` (`supervisor.py:232`, `nodes.py:218`, `subagents/*.py`), so a step can
  be attributed to a prompt without new plumbing in each node.
- **The chain is already observable**: `TurnMetricsHandler` receives `langgraph_node` and
  `langgraph_checkpoint_ns` on chain hooks and already dedupes per task. `on_tool_start` /
  `on_tool_end` / `on_tool_error` exist on `BaseCallbackHandler` and are not used yet — they are
  what turns the current flat `by_node` map into an ordered call chain including tools.
- **`prompt_versions` was already anticipated**: `specs/user-feedback-v1/DESIGN.md` §3.1 lists it
  as a column on `agent_runs`. Adding it here keeps that design converging rather than forking.
- The existing `by_node` JSON stays as the cheap roll-up; the new table is the ordered detail.

### Scope

In:
- `agent_run_steps` table: run_id, seq, kind (`llm` | `tool` | `node`), node, ns, model,
  prompt_name, prompt_version, input/output/cached tokens, cost_usd, started_at, ms, status,
  error_type, tool_name, meta JSON. Indexed on run_id.
  **Narrowed during design, deliberately:** `meta` ships with `finish_reason` only. The intake
  wording also named the reflection decision, the supervisor target/plan shape and the revision
  index, but the only hook that could supply them is `on_chain_end(outputs)` — and `outputs` is
  graph state carrying `messages`. Reading it to obtain a scalar would open exactly the content
  path this spec exists to keep shut, so those fields were dropped rather than smuggled in.
- `agent_runs.prompt_versions` JSON: the active name→version snapshot for the turn.
- `TurnMetricsHandler` records ordered steps and gains the three tool hooks; still never raises.
- `GET /dashboard/agent-runs/{id}`: header with the run's totals, a waterfall of the call chain
  with per-step timing bars, a per-model cost table, the tool list with statuses, and the prompt
  versions used — each linking to `/dashboard/prompts/{name}`. Rows on the list page link here.
- Tests: step capture (incl. tool hooks and ordering), migration round trip, repository, the
  detail route behind the dashboard guard (200 dev / 404 prod), and an empty/unknown id path.

Out: message text, tool arguments, model output, any user content; retention/rotation policy;
changing the existing list page's columns; the `usage` SSE/API contract.

### Rationale

Prompts are already versioned on disk and already rendered by a dashboard page, so a
name→version pointer is smaller than the text, diffable, and cannot become a second source of
truth — while still answering "what system prompt was this running under" in one click. Storing
the prose would have reversed the PII decision that #118/#129 had just hardened, for no
information the pointer does not already carry.

### Alternatives considered

- Persist full prompts and messages: rejected by the human at intake — it reverses the PII
  decision that #118/#129 just hardened and would put user content behind an HTTP Basic page.
- Content behind an off-by-default flag with retention: deferred; revisit only if pointer-level
  detail proves insufficient in practice.
- Reconstruct the chain from Langfuse instead: rejected — opt-in, external, and the operator
  dashboard should stand on its own data.

### Deviations

- Rule 1 (task 3.1): the detail route loads the run via `session.get` rather than adding a
  repository method, since the repository had no `get()` and it sat outside that task's file set.
- Rule 3 (controller): wave-1 review fixes — the `prompt_versions` repo tests asserted a list
  shape no producer emits; the leak test stopped at the handler and now follows the write path;
  stranded open steps are swept at turn close.
- Rule 1 (controller, post-UAT): a code comment claimed the multi-intent specialist sits in the
  middle namespace segment. A live turn disproved it — the specialist is absent entirely — so the
  comment and the page's prompts table were corrected to say what is actually known.

Carry-over Minor findings (non-blocking):
- `synthesis_worker/*` steps carry no prompt pointer; recovering it needs `state["task"]` plumbed
  out to the callback.
- `on_tool_end` may carry a `ToolMessage(status="error")` that a future per-tool
  `handle_tool_error` would hide; no tool sets one today.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| step ordering and attribution | `cd apps/api && env OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/s1.db ../../.venv/bin/python -m pytest tests/agents/test_turn_metrics_steps.py -q` | 0 | seq at start; llm/tool node resolution; sweep | SC-1 |
| no user content in a step | `cd apps/api && env OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/s2.db ../../.venv/bin/python -m pytest tests/agents/test_step_content_leak.py -q` | 0 | marker absent from handler steps AND the stored row | SC-2 |
| step cap | `cd apps/api && env OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/s3.db ../../.venv/bin/python -m pytest tests/agents/test_turn_metrics_steps.py -k cap -q` | 0 | truncates while totals stay exact | SC-3 |
| prompt map keys | `cd apps/api && env OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/s4.db ../../.venv/bin/python -m pytest tests/agents/test_prompt_map.py -q` | 0 | node set derived from the real graph; sub-agents distinct | SC-4 |
| build-time snapshot | `cd apps/api && env OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/s5.db ../../.venv/bin/python -m pytest tests/agents/test_prompt_versions_snapshot.py -q` | 0 | exposed on the compiled graph | SC-5 |
| schema and migration | `cd apps/api && env OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/s6.db ../../.venv/bin/python -m pytest tests/test_db_models.py tests/db/test_agent_run_steps_migration.py -q` | 0 | column sets exact; up/down round trip | SC-6 |
| repository | `cd apps/api && env OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/s7.db ../../.venv/bin/python -m pytest tests/repositories/test_agent_run_steps_repo.py -q` | 0 | seq order; prompt_versions as a mapping | SC-7 |
| both channels persist steps | `cd apps/api && env OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/s8.db ../../.venv/bin/python -m pytest tests/api/agent/test_agent_run_steps_wiring.py -q` | 0 | chat and stream | SC-8 |
| detail page and guard | `cd apps/api && env OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/s9.db ../../.venv/bin/python -m pytest tests/api/agent_config/test_agent_run_detail_page.py -q` | 0 | 200 dev / 404 prod / 404 unknown / version-pinned links | SC-9 |

### Not auto-verified

- Per-step prompt attribution on the multi-intent path — reached truth by live observation, and
  the answer is negative: the namespace is `synthesis_worker:<uuid>|assistant:<uuid>` with no
  specialist segment, so those steps carry no prompt pointer. Disclosed in the code comment, the
  page's column and the UAT README rather than papered over.
- Cost per step against real provider billing — reached provenance (same static price table as the
  parent spec, verified 2026-09-03); not reconciled against an invoice.
- The Postgres path for the new migration — exercised once by hand during the live UAT (and it
  surfaced the `create_all` collision below); CI runs it on every push.

### Rollback

- `cd apps/api && ../../.venv/bin/alembic downgrade e3b7c5d9a1f4` drops `agent_run_steps` and the
  `prompt_versions` column (both additive; no existing data is altered), then
  `git revert de438f0..f3d2b1d` or drop the branch before merge.

### Harness-Delta

- `check_review_receipt.py` treats any path outside `specs/` as unreviewed code, so committing
  UAT evidence under `screenshots/` turns the receipt stale (hit on agent-turn-metrics). Worth
  exempting documentation paths.
- Four repositories call `Base.metadata.create_all` on *any* backend, so booting the app before
  running migrations pre-creates a new table on Postgres and `alembic upgrade head` then fails
  with `DuplicateTable`. Hit during this spec's live UAT; it is the deep review's "schema
  ownership split" item, and it belongs to the project rather than to this branch.
