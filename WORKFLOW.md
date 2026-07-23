# Travel Agent — Backend Chatbot Workflow

> Reference for the current backend AI-agent workflow under `apps/api/app/`.
> Companion diagrams: `WORKFLOW_DIAGRAM.md` (not updated in this pass).
> Last verified against implementation: 2026-07-21.

A **multi-agent LangGraph app**: a supervisor classifies one or more travel intents and hands work
to five focused ReAct sub-agents. The graph is stateful (thread checkpointer + cross-thread store),
provider-agnostic, tier-aware, and configured per node from the database. User preferences,
standing instructions, and past-trip episodes are loaded before routing; durable signals are
extracted in a post-response background task, outside the answer graph.

---

## 1. Components

| Module | Responsibility |
|---|---|
| `routers/agent.py` | `/agent/chat`, `/stream`, `/manifest`, `/conversations*`; turn persistence, quota/context resolution, background extraction scheduling |
| `core/auth.py`, `services/quota_service.py` | Optional Supabase JWT (`user_id` = subject); server-resolved tier and free-tier quota |
| `agents/context.py`, `agents/constants.py`, `enums.py` | Frozen per-run `AgentContext`; sub-agent inventory, tier ceiling, ledger/reflection limits |
| `agents/graph.py` | Wires the parent graph and subgraphs; compiles with the process-lifetime checkpointer/store |
| `agents/supervisor.py` | Structured routing, ordered task ledger, language detection, raw slot extraction, and tier gating |
| `agents/nodes.py` | `load_context`, `summarize`, `dispatch_next`, `reflection`, and booking `plan_node` (HITL) |
| `agents/subagents/*.py`, `_base.py` | Five hand-built ReAct subgraphs; model/tool gating, retries, private clarification tool |
| `agents/state.py` | `TravelAgentState`; reducers and system-context/date/language injection |
| `tools/registry.py`, `tools/*_tools.py` | Domain tool groups and MCP-style read-only/destructive metadata |
| `clients/llm.py`, `core/llm_providers.py` | Provider profiles, `init_chat_model()`, per-node DB overrides, and `FakeLLM` |
| `agents/checkpointer.py`, `memory/store.py` | Thread checkpoints and namespaced long-term memory |
| `memory/extractor.py`, `memory/extraction_runner.py` | Last-exchange extraction and best-effort background writes |
| `memory/summarizer.py` | Tool-pair-safe rolling history compression |
| `streaming/*.py`, `core/streaming.py` | Typed SSE mapping, panels, suggestions, and isolated-session persistence |
| `mcp/server.py`, `agents/observability.py` | MCP tool surface and optional Langfuse callbacks |

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
5. **Persist input** — save a new user turn before graph execution (except retry/resume). A null
   request `trip_id` is omitted from graph input so it does not erase a checkpointed active trip.
6. **Invoke** — `graph.ainvoke(input, cfg, context=ctx)` or `Command(resume=...)` for HITL resume.
7. **Reply** — assemble the accepted user-facing `AIMessage` content, excluding tool-call messages
   and reflection-superseded drafts; fall back to `AGENT_ERROR_FALLBACK_MSG` on failure/empty output.
8. **Memory** — if no HITL interrupt is pending, schedule `run_memory_extraction()` after the
   response using the final messages/state and `graph.extract_memory_llm`.
9. **Response** — return `ChatResponse(conversation_id, reply, trip_id, current_flow, suggestions,
   interrupt_pending, interrupt_payload)`.

`POST /agent/stream` performs the same identity/context/quota/conversation setup, commits the user
turn before streaming, then calls `graph.astream(..., stream_mode=["messages", "updates"],
subgraphs=True)`. It emits typed events (`start`, `subagent`, `reset`, `token`, `tool_call`,
`tool_result`, `panel`, `interrupt`, `done`, `error`) and persists the assistant turn through an
isolated sessionmaker because the generator outlives the request session. After the stream drains,
the mapper places the final graph state in a sink; a Starlette `BackgroundTask` extracts memory
unless an interrupt is pending.

Other endpoints list conversations/messages, claim anonymous conversations after login, and expose
the tool/sub-agent manifest.

---

## 3. Parent graph topology (`agents/graph.py`)

```text
START → load_context → summarize → supervisor
                                      │
                                      ├─ unknown / tier-gated ───────────────→ END
                                      ├─ booking → plan (interrupt)
                                      │               ├─ rejected ───────────→ END
                                      │               └─ approved → booking ─┐
                                      └─ primary specialist ──────────────────┤
                                                                             ▼
                                                                      dispatch_next
                                                ┌─ queued specialist ←───────┤
                                                └─ queue empty/abandoned → reflection
                                                                              │
                                                current_flow ← REVISE ─────────┤
                                                                    OK/cap/off → END

AFTER RESPONSE (outside LangGraph): background memory extraction → Store
```

### Supervisor

`SupervisorIntent` contains:

- `target_agent`: primary `planner | concierge | journal | booking | budget`;
- optional ordered `plan` follow-ons (legacy `secondary_agent` remains supported);
- dominant conversation `language`;
- optional raw `slots` for destination, origin, date text, party/room counts, budget, cabin, area.

The model extracts raw mentions; Python normalizes dates/counts/budget into `trip_facts` (the
“LLM parses, code computes” rule). The task ledger is capped at four total specialist runs, removes
invalid/tier-gated entries, and never queues `booking` because booking must enter through HITL.

### Dispatch, clarification, reflection, and HITL

- **`dispatch_next`** is pure code. It pops the next `pending_flows` entry or routes to reflection.
  If any specialist calls the private `needs_clarification` tool, `awaiting_user=True`; the remaining
  ledger is abandoned for that turn.
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
| `allowed_subagents` | Free excludes `booking`; premium → unrestricted | Supervisor and ledger gate |
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
| **planner** | Trip CRUD/create, places, flight search, hotel availability, weather/climate, routing, episodic recall, date resolution |
| **concierge** | Places, weather/climate, routing, local tips, hotel browse/search, travel-knowledge RAG, date resolution |
| **journal** | Trip/journal writes and preference memory tools |
| **booking** | Flight/hotel search and booking, cancellations, date resolution; only reachable through HITL |
| **budget** | Expense writes/lists/summaries and trip budget |

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

- identity/routing: `user_id`, `trip_id`, `current_flow`, `language`;
- conversation quality: `summary`, `revisions`, `awaiting_user`;
- injected context: `trip_context`, `profile`, `instructions`, `preferences`;
- working plan: merge-reduced `trip_facts`, ordered `pending_flows`, `plan_approved`.

`system_with_summary()` folds profile, standing instructions, active trip, rolling summary, known
trip facts, and preferences into one leading system message. `trip_facts` are thread-scoped working
memory; they are not long-term preference memory.

### Short-term memory

`AsyncPostgresSaver` persists graph state by `thread_id`; development/tests may use `MemorySaver`.
The checkpointer also holds pending HITL interrupts. The `summarize` node compresses history after
`summarize_threshold` (default 20), keeps at least the last five messages, and never splits an
assistant tool call from its `ToolMessage` result.

### Long-term memory

`PostgresStore` with a semantic index is the durable backend; local/test or degraded paths use an
indexed `InMemoryStore`. Values are namespaced as `("users", user_id, kind)` and stamped with
`updated_at`:

| Kind | Write path | Read path |
|---|---|---|
| `prefs` | Hot `save_user_preference`; background extractor | `load_context` direct/full read (up to 8 non-profile prefs), profile exact-key read, memory tools |
| `procedural` | Background extractor | `load_context` → standing instructions (up to 10) |
| `episodes` | Background extractor; approved outcome when HITL passed | Planner's semantic `recall_past_trips` (up to 3) |

Reserved preference keys `name`, `gender`, and `travel_group` form the injected profile. Helpers
provide keyed upsert, search, and typed `Preference`/`Instruction`/`Episode` results.

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
- **MCP** — re-exposes registry tools with read-only/destructive annotations and omits tools that
  require `InjectedStore`.
- **Observability** — optional Langfuse callbacks and non-PII trace metadata (`user_id`, `trip_id`);
  disabled by default and fail-open.

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
| `agent_recursion_limit` / `summarize_threshold` | `25` / `20` | Graph cycle guard / compression trigger |
| `agent_free_daily_turn_limit` | `20` | Free-tier quota |
| `agent_config_poll_interval_seconds` | `5` | Cross-process config refresh polling |
| `agent_timezone` | `Asia/Ho_Chi_Minh` | Fallback date grounding zone |
| `langfuse_enabled` | `false` | Tracing |

---

## 9. Known gaps

- **Unverified memory writes** — an LLM extraction is key-upserted without provenance, confidence,
  conflict review, or user-facing view/edit/delete controls.
- **Non-durable extraction worker** — in-process background work can be lost on process termination
  and may not finish before an immediate next turn.
- **Coarse reflection** — one fast-model `REVISE` check, no per-criterion rubric.
- **Anonymous identity trust** — anonymous callers choose the id that scopes thread and memory; the
  claim endpoint migrates it only after login.
- **Double persistence** — SQL conversation/messages and LangGraph checkpoints can drift when one
  persistence path succeeds and the other fails.
- **Bounded planning** — the supervisor ledger runs at most four specialists in one turn and does
  not queue booking; this is a deliberate safety/recursion boundary, not an open-ended planner.
