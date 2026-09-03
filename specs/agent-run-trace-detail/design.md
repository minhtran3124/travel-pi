# agent-run-trace-detail — Design

Status: reviewed 2026-09-03 (spec-document-reviewer: 6 issues raised, all addressed below;
intake fork resolved by the human: structure + pointers, no content)
Lane: high-risk · Builds on `specs/agent-turn-metrics` (branch `feat/agent-turn-metrics`)

## 1. Purpose

Today a turn is one flat row: call count, tokens, cost, latency, and a `by_node` map. That answers
"what did it cost" but not "what did it *do*". This adds the ordered call chain — which node ran,
in what order, on which model, under which prompt version, which tools it called and whether they
succeeded — and a detail page that renders it.

Success: clicking a row on `/dashboard/agent-runs` opens a page that shows the turn's chain as a
waterfall, the cost split per model, the tools that ran, and the exact prompt versions used, each
linking to the prompt text already published at `/dashboard/prompts/{name}`.

## 2. Constraints

- **No content.** No message text, no tool arguments, no model output. The turn's row and its
  steps hold structure and pointers only. This is the intake decision and it preserves the PII
  posture from #118/#129.
- Collection stays best-effort: no hook may raise into a reply or an SSE stream.
- Additive schema only; SQLite (`create_all`) and Postgres (Alembic) must agree.
- Writes must not repeat the deadlock from `agent-turn-metrics`: **a background task must never
  write a row the request session has flushed but not committed.** Steps are written on the same
  path (and inside the same commit) as `finish()`.
- No new dependency. The dashboard page stays behind `require_dashboard_access`.

## 3. Why pointers beat stored prompts

Prompts are already versioned on disk (`app/prompts/<name>/v<N>.md`), pinned by `active.yaml`, and
rendered by an existing dashboard at `/dashboard/prompts/{name}?version=v<N>`. Recording
`name -> version` is therefore smaller than the text and diffable through a page that already
exists. Copying prose into the database would add storage, a redaction question, and a second
source of truth for the same string.

Two details make the pointer honest rather than approximately right, and both were wrong in the
first draft:

- **The link must pin the version.** `/dashboard/prompts/{name}` with no query renders the
  *latest* version on disk, not the one that ran. The page already accepts `?version=` (its
  `_parse_version` takes `3` or `v3`), so every link carries it.
- **The snapshot must be taken at graph build, not per turn.** The five sub-agent prompts and
  `communication_style` are read once when the graph is compiled (`_base.py:206`,
  `concierge.py:26`, …), so `active.yaml` can move without the running graph changing. A turn-start
  read of `active.yaml` would therefore record a version the turn did not use. The snapshot is
  taken during `build_graph` and attached to the compiled graph, the same way
  `extract_memory_llm` already is, and the router reads it from there.

## 4. Architecture

### 4.1 Ordered step capture — `app/agents/metrics.py`

`TurnMetricsHandler` gains an ordered `_steps` list (lock-guarded) alongside the existing
counters, plus the three tool hooks it does not implement yet.

A step is **opened at start and closed at end**. `seq` and `offset_ms` are assigned when the step
*begins*, so a node span sorts above the children it brackets; closing only fills `ms`, `status`
and the token/finish fields. Ordering by close time would render every parent below its children.

| Hook | Effect |
| --- | --- |
| `on_chat_model_start` | opens an `llm` step: node + ns from `metadata`, model from `ls_model_name`, keyed by `run_id`. |
| `on_llm_end` | closes it: tokens (incl. cached), `ms`, `finish_reason` from `response_metadata`, `status="ok"`. |
| `on_llm_error` | closes it with `status="error"` and `error_type`. |
| `on_tool_start` | opens a `tool` step: `tool_name` from `serialized.get("name")` falling back to `kwargs.get("name")`, node + ns from **its own `metadata`** (`on_tool_start` carries `metadata` too — `parent_run_id` is *not* usable, because `on_chain_start` registers only the outermost run per namespace, so a tool's immediate parent is normally absent). **`input_str` and `inputs` are ignored on purpose.** |
| `on_tool_end` / `on_tool_error` | closes it with `ms` and `status`. |
| `on_chain_start` | opens a `node` step for the node task it already dedupes by `checkpoint_ns`. |
| `on_chain_end` / `on_chain_error` | closes it. `outputs` is **never read** — it is graph state and carries `messages`. |

Every hook body stays wrapped so it cannot raise. `steps()` returns the ordered list. `snapshot()`
and `public()` are unchanged, so nothing downstream of `agent-turn-metrics` has to change.

**Volume cap.** ReAct loops, reflection revisions and parallel `synthesis_worker` fan-out make the
step count unbounded in principle. `MAX_STEPS_PER_TURN = 200`: once reached the handler stops
opening new steps and increments `steps_dropped`, which the page shows as an explicit note. The
counters and totals stay exact — only the per-step detail truncates.

### 4.2 Prompt attribution — `app/agents/prompt_map.py` (new)

Two independent pieces:

- **`prompt_versions_snapshot()`** — `{name: registry.active_version(name)}` for every registered
  name, evaluated **inside `build_graph`** and attached as `compiled.prompt_versions`. The router
  copies it onto `agent_runs.prompt_versions` per turn. Taken at build time it records what the
  running graph actually baked in; taken per turn it would drift from it the moment `active.yaml`
  changed without a rebuild.
- **`PROMPTS_FOR_NODE`** — a static map to the **list** of prompts composing a step's system
  message. It is keyed on the handler's existing `_node_key(node, ns)`, **not** the bare node
  name: every sub-agent's inner node is literally called `assistant` (`_base.py:235`), so a
  bare-name key collapses all five into one and the identity survives only in the checkpoint
  namespace (`planner/assistant`, `concierge/assistant`, …). A sub-agent resolves to *two* prompts
  (`["concierge", "communication_style"]`) because `_base.py` composes the shared style into each
  one — which is why a step stores a list. Nodes that build no registry prompt (`pii_guardrail`,
  `load_context`, `plan`, `summarize`, `synthesize`, `synthesis_worker`) map to `[]` and render
  with no link. A test asserts the map's keys cover every node key the graph can produce.

### 4.3 Data model

`agent_run_steps` (`UUIDBase`), indexed on `run_id`, ordered by `seq`:

| Column | Type | Notes |
| --- | --- | --- |
| `run_id` | str, idx, not null | the `agent_runs` id |
| `seq` | int, not null | assigned at step **start** |
| `kind` | str, not null | `llm` / `tool` / `node` |
| `node`, `ns` | str null / str null | graph node and checkpoint namespace |
| `model` | str null | LLM steps only |
| `prompts` | JSON null | `[{"name": ..., "version": ...}]`; `[]` when the node builds no prompt |
| `input_tokens`, `output_tokens`, `cached_tokens` | int, default 0 | |
| `cost_usd` | float null | priced per step; None when the model is unpriced |
| `offset_ms` | int, default 0 | start offset from the handler's own monotonic origin |
| `ms` | int, default 0 | duration |
| `status` | str, not null | `ok` / `error` / `open` (never closed) |
| `error_type` | str null | `type(exc).__name__` only — never `str(exc)`, which can quote user input |
| `tool_name` | str null | |
| `meta` | JSON null | strict scalar allowlist, currently `{"finish_reason": str}` only |

One clock throughout: `offset_ms` and `ms` both derive from the handler's `_created` monotonic
origin, so the waterfall needs no wall-clock arithmetic and cannot mix clocks. `agent_runs` gains
`prompt_versions` JSON (nullable). Alembic revision `down_revision = e3b7c5d9a1f4` creates the
table + index and adds the column; `downgrade` reverses both.

**Content boundary.** `meta` accepts only keys on an explicit allowlist with scalar values; there
is no code path from graph state, tool inputs or model output into a step. `on_chain_end`'s
`outputs` and `on_tool_start`'s `inputs` are the two places user content is reachable, and both
are deliberately unread.

### 4.4 Persistence

`AgentRunRepository` gains `add_steps(run_id, steps: list[dict])` (bulk insert, unknown keys
ignored) and `steps_for(run_id)`; `finish(...)` takes an optional `prompt_versions`.

Both call sites write steps where they already write `finish`, so the deadlock this branch's
parent fixed cannot recur — a step write is never issued from a background task against a row the
request session has flushed but not committed:

- **chat:** inside `_finalize`, before its explicit `session.commit()`.
- **stream:** inside `record_agent_run`'s finalizer, on the isolated factory.

### 4.5 Detail page — `GET /dashboard/agent-runs/{id}`

Same router as the list, so `require_dashboard_access` applies automatically (it is declared at
router level). 404 when the id is unknown. Sections:

1. **Header** — status chip, channel/kind, user, flow, started, and the turn totals.
2. **Call chain (waterfall)** — one row per step in `seq` order: kind badge, node (indented when
   `ns` shows a sub-graph), model or tool name, and a bar whose left offset and width come from
   `offset_ms` and `ms` as percentages of the turn's latency, computed server-side. Errors are
   marked; a truncated turn shows the `steps_dropped` note.
3. **Cost by model** — from `by_model`: calls, in/out/cached tokens, cost.
4. **Tools** — name, node, status, ms.
5. **Prompts used** — from `prompt_versions`, each linking to
   `/dashboard/prompts/{name}?version=v{N}` so the reader lands on the version that ran, not
   whatever is latest today.

The list page's `started` cell becomes a link to this page.

## 5. Error behaviour

- Any step hook raising is caught and logged at DEBUG; counters and other steps are unaffected.
- `add_steps` failing is logged; the run row still finishes (steps are supplementary).
- A run with no steps renders the page with an explicit "no steps recorded" note rather than an
  empty table — that is the expected shape for rows created before this change.
- An unknown or malformed id returns 404, never a 500.
- A step whose model is unpriced carries `cost_usd = None`, consistent with the turn total.
- `latency_ms` can be null (a run that never closed). The waterfall falls back to the largest
  `offset_ms + ms` across the steps rather than dividing by None.

## 6. Tests

- `tests/agents/test_turn_metrics_steps.py` — `seq` follows start order so a node step precedes
  its children; an LLM step takes its node from `on_chat_model_start`; a tool step takes its node
  from `on_tool_start`'s own metadata and records status; the volume cap stops at
  `MAX_STEPS_PER_TURN` and counts `steps_dropped` while totals stay exact; a raising hook leaves
  the other steps intact.
- **Content-leak test** — drive the handler with a distinctive marker string as the tool
  `input_str`/`inputs` and as graph-state `outputs`, plus an exception whose message contains it,
  then assert the marker appears in **no** field of **any** step (including `meta` and
  `error_type`). This is the test that enforces the intake decision.
- `tests/agents/test_prompt_map.py` — the map's keys equal the graph's node set exactly; sub-agent
  nodes list their own prompt plus `communication_style`; prompt-less nodes map to `[]`; the
  snapshot covers every registered prompt name.
- `tests/db/test_agent_run_steps_migration.py` — upgrade/downgrade round trip.
- `tests/repositories/test_agent_run_steps_repo.py` — `add_steps` / `steps_for` ordering.
- `tests/api/agent_config/test_agent_run_detail_page.py` — 200 in dev with the chain rendered,
  404 in production without credentials, 404 for an unknown id, and the no-steps case.
- `tests/test_db_models.py` — the new table and column sets.

## 7. Open assumptions

- Node-span steps (`kind="node"`) are recorded alongside their children rather than nested; the
  page indents by namespace instead of building a tree. Ordering by start time is what makes the
  flat list readable as a hierarchy.
- Per-step cost uses the same static price table; a step on an unpriced model contributes `None`
  and the turn total is already `None` in that case.
- `prompt_versions` is captured at graph build, so it reflects what the running graph uses. A
  prompt edit without a rebuild changes neither the agent nor this record — which is the point.
- `summarize` and `synthesize` build their system text outside the registry, so they map to `[]`
  rather than to a fictional prompt name.
