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

<not started — intake only. Fill at ship.>

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
  error_type, tool_name, meta JSON (finish_reason, supervisor target/plan shape, reflection
  decision, revision index). Indexed on run_id.
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

<fill at ship>

### Alternatives considered

- Persist full prompts and messages: rejected by the human at intake — it reverses the PII
  decision that #118/#129 just hardened and would put user content behind an HTTP Basic page.
- Content behind an off-by-default flag with retention: deferred; revisit only if pointer-level
  detail proves insufficient in practice.
- Reconstruct the chain from Langfuse instead: rejected — opt-in, external, and the operator
  dashboard should stand on its own data.

### Deviations

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| intake evidence | `python3 .claude/scripts/verify_summary.py --lane agent-run-trace-detail` | 0 | lane/confidence/reason + rollback present | |

### Not auto-verified

- none yet — intake only; every claim above is a code-reading finding, not a re-run behaviour.

### Rollback

- Intake only: `git rm -r specs/agent-run-trace-detail`. Implementation rollback (fill at ship):
  `alembic downgrade -1` from apps/api drops `agent_run_steps` and the `prompt_versions` column,
  plus `git revert <sha>`.

### Harness-Delta

- `check_review_receipt.py` treats any path outside `specs/` as unreviewed code, so committing
  UAT evidence under `screenshots/` turns the receipt stale (hit on agent-turn-metrics). Worth
  exempting documentation paths.
