# Travel Agent — Backend Chatbot Workflow

> Reference for the current backend AI-agent workflow under `apps/api/app/`.
> Companion diagrams: `WORKFLOW_DIAGRAM.md`.
> Last verified against implementation: 2026-09-21.

A **multi-agent LangGraph app**: a supervisor classifies one or more travel intents and hands work
to five focused ReAct sub-agents. The graph is stateful (thread checkpointer + cross-thread store),
provider-agnostic, tier-aware, and configured per node from the database. Every turn enters through
a PII guardrail; user preferences, standing instructions, and past-trip episodes are loaded before
routing; durable signals are extracted in a post-response background task, outside the answer graph.
Long-term memory is treated as untrusted data — guarded at the store layer and wrapped in
`<traveller_memory>` tags in the prompt.

---

## 1. Components

| Module | Responsibility |
|---|---|
| `routers/agent.py` | `/agent/chat`, `/stream`, `/manifest`, `/conversations*`, `/conversations/claim`; turn persistence, quota/context resolution, per-turn metrics, background extraction scheduling |
| `routers/feedback.py` | `POST /agent/feedback` — rate a completed assistant reply (thumbs), keyed to `agent_runs` |
| `core/auth.py`, `services/quota_service.py` | Optional Supabase JWT (`user_id` = subject); server-resolved tier and free-tier quota |
| `agents/context.py`, `agents/constants.py`, `enums.py` | Frozen per-run `AgentContext`; sub-agent inventory, tier ceiling, task-fan-out/reflection limits |
| `agents/guardrails.py` | Pre-model PII guardrail node (Luhn-checked credit-card masking) and `redact_pii` |
| `agents/graph.py` | Wires the parent graph and subgraphs; compiles with the process-lifetime checkpointer/store |
| `agents/supervisor.py` | Structured routing, a deduplicated parallel `tasks` list with per-task queries, language detection, raw slot extraction, and tier gating |
| `agents/nodes.py` | `load_context`, `summarize`, `route_tasks`, `synthesize`, `reflection`, and booking `plan_node` (HITL) |
| `agents/subagents/*.py`, `_base.py`, `synthesis_worker.py` | Five hand-built ReAct subgraphs plus the fan-out worker; model/tool gating, retries, private clarification tool |
| `agents/state.py` | `TravelAgentState`; reducers and system-context/date/language injection, `<traveller_memory>` wrapping |
| `tools/registry.py`, `tools/*_tools.py` | Domain tool groups and MCP-style read-only/destructive metadata |
| `clients/llm.py`, `core/llm_providers.py` | Provider profiles, `init_chat_model()`, per-node DB overrides, and `FakeLLM` |
| `agents/checkpointer.py`, `memory/store.py`, `memory/guard.py` | Thread checkpoints, namespaced long-term memory + store-layer poisoning guard and fact-age markers |
| `memory/extractor.py`, `memory/extraction_runner.py` | Last-exchange extraction and best-effort background writes |
| `memory/summarizer.py` | Tool-pair-safe rolling history compression (count + token budget triggers) |
| `streaming/*.py`, `core/streaming.py` | Typed SSE mapping, panels, suggestions, isolated-session persistence, and per-turn `agent_runs` metrics |
| `mcp/server.py`, `agents/observability.py`, `agents/metrics.py` | MCP tool surface, optional Langfuse callbacks, and the turn-metrics handler |

Graph, checkpointer, and store are created once in `core/lifespan.py` and held on `app.state`.
`routers.agent.get_travel_graph()` delegates to `resolve_travel_graph()`, which rebuilds only when
the DB-backed agent-config generation changes and reuses the existing checkpointer/store. Tests
override this dependency with a `FakeLLM` graph.

---

## 2. Request flow

`POST /agent/chat`:

1. **Identity** — authenticated requests use the JWT subject and ignore the body `user_id`;
   anonymous requests use the client-supplied id.
2. **Context** — resolve tier server-side, the reflection enabled flag from `AgentConfigCache`, and
   the client IANA timezone (invalid/missing → configured fallback). There is no request `mode`.
3. **Quota** — `check_quota()` raises 429 when a free user exceeds the daily turn limit.
4. **Conversation** — get or create the SQL conversation; compose checkpointer thread id
   `user_{uid}_trip_{trip|none}_conv_{conversation_id}`.
5. **Persist input** — mask credit-card PII (`redact_pii`) and save a new user turn before graph
   execution (except retry/resume). A null request `trip_id` is omitted from graph input so it does
   not erase a checkpointed active trip; the signed-in account email rides the input as
   `account_email` (offered for booking, never asked blind).
6. **Invoke** — `graph.ainvoke(input, cfg, context=ctx)` or `Command(resume=...)` for HITL resume.
7. **Reply** — assemble the accepted user-facing `AIMessage` content, excluding tool-call messages
   and reflection-superseded drafts; fall back to `AGENT_ERROR_FALLBACK_MSG` on failure/empty output.
8. **Memory** — if no HITL interrupt is pending, schedule `run_memory_extraction()` after the
   response using the final messages/state and `graph.extract_memory_llm`.
9. **Response** — return `ChatResponse(conversation_id, assistant_message_id, agent_run_id, reply,
   trip_id, current_flow, suggestions, interrupt_pending, interrupt_payload, usage)`. A best-effort
   `agent_runs` row (started up front, finalized in `_finalize`) records per-turn metrics; `usage`
   is its client-facing subset.

`POST /agent/stream` performs the same identity/context/quota/conversation setup, commits the user
turn before streaming, then calls `graph.astream(..., stream_mode=["messages", "updates"],
subgraphs=True)`. It emits typed events (`start`, `subagent`, `reset`, `token`, `tool_call`,
`tool_result`, `panel`, `interrupt`, `done`, `error`) and persists the assistant turn through an
isolated sessionmaker because the generator outlives the request session. After the stream drains,
the mapper places the final graph state in a sink; a Starlette `BackgroundTask` extracts memory
unless an interrupt is pending.

Other endpoints list conversations/messages (with per-message feedback and rateability), claim
anonymous conversations after login, expose the tool/sub-agent manifest, and accept a thumbs rating
on a completed reply (`POST /agent/feedback`, keyed to the reply's `agent_run`).

---

## 3. Parent graph topology (`agents/graph.py`)

```text
START → pii_guardrail → load_context → summarize → supervisor → route_tasks
                                                    │
                          ┌─ no tasks / tier-gated ─┴──────────────────────→ END
                          ├─ booking (tasks[0]) → plan (interrupt)
                          │                          ├─ rejected ──────────→ END
                          │                          └─ approved → booking ─┐
                          ├─ one task → single specialist ───────────────────┤
                          └─ many tasks → Send(synthesis_worker) × N          │
                                             └─ all workers → synthesize ─────┤
                                                                             ▼
                                                                        reflection
                                                current_flow ← REVISE ────────┤
                                                                   OK/cap/off → END

AFTER RESPONSE (outside LangGraph): background memory extraction → Store
```

There is one dispatch model: **parallel, independent slices**. `route_tasks` reads the supervisor's
deduplicated `tasks` list — a single task goes straight to its specialist, `booking` detours through
the HITL `plan` node, and two or more tasks fan out to parallel `synthesis_worker` instances (one per
task, via `Send`) that converge on `synthesize`. Every specialist (and `synthesize`) edges directly
to `reflection`. A **dependent chain** (e.g. flights → hotel → places → weather → itinerary, all
planner-owned tools) is routed to that **single specialist**, whose own ReAct loop is the sequential
executor and sees its own tool results — there is no cross-specialist ordered ledger.

### Supervisor

`SupervisorIntent` contains:

- `target_agent`: primary `planner | concierge | journal | booking | budget`;
- optional `plan` of **additional, independent** specialists whose slice does not depend on the
  primary's result — each runs in parallel and sees only this message. There is no legacy
  `secondary_agent` field (dropped in supervisor v11); a malformed `plan` entry is coerced or dropped
  by a `before` validator rather than failing the turn;
- optional `task_queries`: one self-contained restatement per specialist, in `[target, *plan]`
  order, so each fanned-out worker gets its own slice of the message (aligned positionally, else the
  worker falls back to the last user message);
- dominant conversation `language`;
- optional raw `slots` for destination, origin, date text, party/room counts, budget, cabin, area.

The model extracts raw mentions; Python normalizes dates/counts/budget into `trip_facts` (the
“LLM parses, code computes” rule). `tasks` is deduplicated by agent (primary first, order preserved),
capped at `MAX_LEDGER_STEPS` (4) total specialist runs, strips invalid/tier-gated entries, and never
includes `booking` because booking must enter through HITL.

### Dispatch, clarification, reflection, and HITL

- **`route_tasks`** is pure code: it maps the `tasks` list to a single specialist, the booking HITL
  `plan` node, or parallel `synthesis_worker` fan-out. **`synthesize`** merges the workers' structured
  `task_results` into one answer. If any specialist calls the private `needs_clarification` tool,
  `awaiting_user=True` and reflection ends the turn early.
- **`reflection`** skips review while awaiting the traveller, when disabled, or after the single
  revision cap. Otherwise it judges `REVISE`/accept: `REVISE` adds an internal `SystemMessage` and
  returns to `current_flow`; accepted answers end the graph.
- **`plan_node`** interrupts before the booking specialist. Resume with `{approved: true}` reaches
  booking and sets `plan_approved=True`; rejection ends with a cancellation message.
- There is **no `extract_memory` graph node**. Reflection terminal paths go directly to `END`.

### Per-run `AgentContext`

The frozen context is not checkpointed and has no user-selectable mode:

| Field | Source/default | Effect |
|---|---|---|
| `tier` | Server-side user row; anonymous/unknown → `free` | Selects the sub-agent ceiling |
| `allowed_subagents` | Free excludes `booking`; premium → unrestricted | Supervisor and task-list gate |
| `allow_reflection` | DB `agent_config[reflection].enabled`; default true | Enables the judge loop |
| `allow_memory_write` | true | Gates post-turn extraction |
| `allow_episodic` | true | Keeps/removes `recall_past_trips` from planner tools |
| `max_revisions` | 1 | Bounds reflection |
| `response_style` | default | Reserved response-style capability |
| `timezone` | Request IANA zone; configured fallback | Grounds relative dates |

### Specialist ReAct subgraph

Each specialist is `START → assistant ⇄ tools → END`. The assistant resolves its DB/env-backed
model, injects shared style + profile/preferences/instructions/trip context/summary/trip facts,
grounds today's date, pins the supervisor-detected reply language, and binds only active tools.
Every specialist also receives the private `needs_clarification` tool; it is not registered in the
public manifest/MCP surface. `ToolNode` converts logic/tool faults into model-visible error messages,
while configured graph retry policies own transient LLM/tool retries. The parent recursion limit is
25.

---

## 4. Sub-agents and tool domains

Model defaults: nodes in `FAST_AGENTS` (`summarize`, `journal`, `budget`, `reflection`,
`extract_memory`, `date_resolution`) use `fast_llm_model`; all other nodes use `llm_model`. A DB
`agent_config` row may override provider/model/base URL/temperature/max tokens per node.

| Sub-agent | Main responsibilities / registered tool groups |
|---|---|
| **planner** | Trip CRUD/create/list, places, flight search, hotel availability, weather, climate, routing, episodic recall, date resolution |
| **concierge** | Places, weather, climate, routing, local tips, visa lookup, hotel browse + availability, travel-knowledge RAG, date resolution |
| **journal** | Trip tools and preference memory tools (`save_user_preference`, `get_user_preferences`) |
| **booking** | Flight/hotel search and booking, flight/hotel cancellation, date resolution; only reachable through HITL |
| **budget** | Expense writes/lists/summaries, trip budget read/set, and budget estimation |

`TOOLS_BY_DOMAIN` is the binding source of truth; `ALL_TOOLS` is de-duplicated from it. Metadata
marks writes and destructive booking/cancellation tools for `/manifest` and MCP. Tools remain thin
service adapters, open their own `session_scope()` when needed, and map domain errors to
`ToolException`.

---

## 5. LLM resolution

- Models are created only through LangChain `init_chat_model()`; runtime code imports no provider
  SDK directly.
- `llm_provider` selects a profile (`openai`, `anthropic`, `google_genai`, `clinepass`, `claude`)
  that owns its SDK, key field, optional gateway URL, and reference model list.
- `get_agent_llm(name)` resolves DB per-node overrides through `AgentConfigCache`, then falls back to
  global provider and the node's main/fast default. Sub-agent model instances are memoized for the
  compiled graph's life; a config generation change rebuilds the graph.
- SDK retries are disabled (`max_retries=0`) because the graph owns retry policy.
- Defaults are `gpt-5` and `gpt-5-mini`; `FakeLLM` scripts normal and structured responses for
  zero-network graph tests.

---

## 6. State and memory

`TravelAgentState` extends `MessagesState` and carries:

- identity/routing: `user_id`, `trip_id`, `account_email`, `current_flow`, `language`;
- conversation quality: `summary`, `revisions`, `awaiting_user`;
- injected context: `trip_context`, `profile`, `instructions`, `preferences`;
- working plan: merge-reduced `trip_facts`, the deduplicated `tasks` list, `task_results`, `plan_approved`.

`system_with_summary()` folds profile, account email, standing instructions, active trip, rolling
summary, known trip facts, and preferences into one leading system message. The three memory-derived
blocks (`profile`, `instructions`, `preferences`) are each wrapped in `<traveller_memory kind=…>`
tags, preceded once by `MEMORY_PREAMBLE`, so stored memory is marked as untrusted data rather than
instructions (memory-poisoning hardening, PR #214). `trip_facts` are thread-scoped working memory;
they are not long-term preference memory.

### Short-term memory

`AsyncPostgresSaver` persists graph state by `thread_id`; development/tests may use `MemorySaver`.
The checkpointer also holds pending HITL interrupts. `should_summarize` fires on either trigger:
the message count exceeds `summarize_threshold` (default 20) **or** the estimated token footprint
(chars/4, including tool-call args) exceeds `summarize_token_budget` (default 12000) × 0.85 — the
token branch is floored to fire only above five messages. The `summarize` node keeps at least the
last five messages, never splits an assistant tool call from its `ToolMessage` result, returns early
without an LLM call when nothing is removable, merges a fresh compression with the previous rolling
summary, and caps the stored summary at 1800 characters.

### Long-term memory

`PostgresStore` with a semantic index is the durable backend; local/test or degraded paths use an
indexed `InMemoryStore`. Values are namespaced as `("users", user_id, kind)` and stamped with
`updated_at`:

| Kind | Write path | Read path |
|---|---|---|
| `prefs` | Hot `save_user_preference`; background extractor | `load_context` reads **all** non-profile prefs (no cap since PR #218), profile exact-key read, memory tools |
| `procedural` | Background extractor | `load_context` → **all** standing instructions (no cap since PR #218) |
| `episodes` | Background extractor; approved outcome when HITL passed | Planner's semantic `recall_past_trips` (top 3) |

Reserved preference keys `name`, `gender`, and `travel_group` (`PROFILE_KEYS`) form the injected
profile; instructions are constrained to a 6-key canonical allowlist on write. Helpers provide keyed
upsert, search, and typed `Preference`/`Instruction`/`Episode` results, plus `list_memory` /
`delete_memory` (a management surface — no route wired yet).

Every read passes through `memory/guard.py` at the store layer: a blocklisted or bad-shape row is
dropped (logged by kind/key/reason, never text) and a survivor carries the guard's normalized text,
so a row poisoned before the guard existed is neutralized on read without a migration. Episode
payloads are limited to `text`/`city`/`outcome`/`trip_id` (PR #214).

**Fact-age markers (PR #216).** `format_age` renders each row's `updated_at` as a month-granularity
`(recorded …)` marker: instructions use a coarse vocabulary (in the last month / 1-11 months ago /
over a year ago), preferences a finer one (in the last month / 1-3 / 4-8 / 9-15 months ago / over a
year ago). A missing, unparseable, or future timestamp yields no marker. The prompt's staleness rule
treats only `recorded in the last month` as fresh; any other marker (or none) must be confirmed with
the traveller before acting on it.

### Background extraction

`run_memory_extraction()` is outside the graph and best-effort:

1. Skip when writes are disabled, identity/store is missing, or a HITL interrupt is pending at the
   router/stream adapter.
2. Serialize the exchange beginning at the last `HumanMessage`.
3. Ask the configured fast extraction model for durable `preferences`, `instructions`, and
   `episodes` using the active versioned prompt.
4. Parse defensively and key-upsert extracted records; `plan_approved` forces episode outcome
   `approved`.
5. Log and swallow extraction/write failures so they never break the delivered reply.

The current FastAPI/Starlette background task is in-process and eventually consistent; it is not a
durable job queue.

---

## 7. Streaming, MCP, and observability

- **Streaming** — one canonical `astream` call maps subgraph messages/updates into typed SSE.
  `reset` removes a superseded reflection draft; panel artifacts are localized before emission;
  final state drives suggestions, language, trip id, interrupt, and the memory-extraction sink.
- **MCP** — re-exposes registry tools with read-only/destructive annotations and omits any tool the
  unauthenticated surface cannot safely serve: destructive booking/cancellation tools, tools needing
  an injected `store`/`tool_call_id`, and `list_trips` by name (its injected `user_id` would become a
  caller-supplied arg) (PR #129).
- **Observability** — optional Langfuse callbacks and non-PII trace metadata (`user_id`, `trip_id`);
  disabled by default and fail-open.

### Per-turn metrics

- **What** — a `TurnMetricsHandler` callback (attached beside the Langfuse handler) records per turn:
  LLM call count, input/output/cached tokens, a USD cost estimate (`app/core/pricing.py`), and
  turn + per-node wall-clock latency. Best-effort — it never raises into the reply path.
- **Where** — one `agent_runs` row per turn (running → completed/interrupted/failed, plus
  `by_model` / `by_node` breakdowns and separate `background_*` columns for memory extraction); the
  client-facing subset rides the `usage` object on `ChatResponse` and the `done` SSE event.
- **Depends on** `stream_usage=True` (OpenAI SDK profile only) so `invoke`/`stream` return
  `usage_metadata`; without it token counts are zero. Browse the rows at `/dashboard/agent-runs`.

---

## 8. Configuration

| Setting | Default | Drives |
|---|---|---|
| `llm_provider` | `openai` | Provider profile / endpoint |
| `llm_model` / `fast_llm_model` | `gpt-5` / `gpt-5-mini` | Global main/fast model fallbacks |
| DB `agent_config` | seeded rows | Per-node enabled/provider/model/base URL/temperature/max tokens |
| `llm_base_url` | `None` | Global one-off gateway fallback |
| `embedding_model` | `text-embedding-3-small` | Long-term semantic index |
| provider API keys | `None` | Real LLM access; tests inject `FakeLLM` |
| `agent_recursion_limit` / `summarize_threshold` | `25` / `20` | Graph cycle guard / message-count compression trigger |
| `summarize_token_budget` | `12000` | Token ceiling for the OR branch of `should_summarize` (× 0.85) |
| `agent_free_daily_turn_limit` | `20` | Free-tier quota |
| `agent_config_poll_interval_seconds` | `5` | Cross-process config refresh polling |
| `agent_timezone` | `Asia/Ho_Chi_Minh` | Fallback date grounding zone |
| `langfuse_enabled` | `false` | Tracing |

---

## 9. Known gaps

- **Unverified memory writes** — an LLM extraction is key-upserted without provenance, confidence, or
  conflict review. A store-layer guard (blocklist + key allowlist + `<traveller_memory>` wrapping,
  PR #214) and month-granularity fact-age markers (PR #216) now bound the blast radius, but there is
  still no user-facing view/edit/delete surface: `list_memory`/`delete_memory` exist without a route.
- **Non-durable extraction worker** — in-process background work can be lost on process termination
  and may not finish before an immediate next turn.
- **Coarse reflection** — one fast-model `REVISE` check, no per-criterion rubric.
- **Anonymous identity trust** — anonymous callers choose the id that scopes thread and memory; the
  claim endpoint migrates it only after login.
- **Double persistence** — SQL conversation/messages and LangGraph checkpoints can drift when one
  persistence path succeeds and the other fails.
- **Bounded planning** — the supervisor's parallel `tasks` list runs at most four specialists in one
  turn and never includes booking; this is a deliberate safety/recursion boundary, not an open-ended
  planner. A dependent chain is executed inside one specialist's own ReAct loop, not fanned out.
