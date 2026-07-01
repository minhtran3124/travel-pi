# Travel Agent — Backend Chatbot Workflow

> Reference for the backend AI-agent workflow. Scope: `apps/api/app/` on
> `feat/agent-memory-layers`. Diagrams: `WORKFLOW_DIAGRAM.md` (`make diagram` → HTML).
> Last verified: 2026-07-01.

A **multi-agent LangGraph app**: a supervisor routes intent to one of five ReAct sub-agents, each
with a focused tool group. Stateful (checkpointer + long-term store), provider-agnostic (LLM by
config), capability-aware (per-request **mode × tier**), with three memory layers (prefs /
procedural / episodes) read on the way in and written in the background on the way out.

---

## 1. Components

| Module | Responsibility |
|---|---|
| `routers/agent.py` | Endpoints: `/agent/chat`, `/stream`, `/manifest`, `/conversations*`; persists turns |
| `core/auth.py`, `services/quota_service.py` | Optional Supabase JWT (`user_id` = sub); per-tier quota (429) |
| `agents/context.py`, `agents/constants.py`, `enums.py` | `AgentContext`: (tier, mode) → capability flags |
| `agents/graph.py` | Wires nodes/edges; compiles with checkpointer + store |
| `agents/supervisor.py` | Structured-intent routing; tier-gates targets |
| `agents/nodes.py` | `load_context`, `summarize`, `reflection`, `plan_node` (HITL), `extract_memory` |
| `agents/subagents/*.py` + `_base.py` | ReAct subgraphs; per-request model + tool gating |
| `tools/registry.py` + `tools/*_tools.py` | Domain tool groups + MCP-style metadata |
| `clients/llm.py` | `init_chat_model()`; per-node `get_agent_llm`; `FakeLLM` in tests |
| `agents/state.py` | `TravelAgentState`, `system_with_summary()` |
| `agents/checkpointer.py`, `memory/store.py` | Thread checkpoints + long-term semantic store |
| `memory/extractor.py`, `memory/summarizer.py` | Background extraction + history compression |
| `streaming/*.py`, `core/streaming.py` | Typed SSE events + isolated-session persistence |
| `rag/*.py`, `mcp/server.py`, `agents/observability.py` | Retrieval · MCP tool surface · Langfuse |

Graph + checkpointer + store are built **once** in `core/lifespan.py`, held on
`app.state.travel_graph`, resolved per request by `get_travel_graph()` (tests inject a `FakeLLM` graph).

---

## 2. Request flow

`POST /agent/chat`:

1. **User** — JWT sub if authenticated, else client `user_id` (anonymous). Auth ignores body `user_id` (anti-spoof).
2. **Context** — `resolve_agent_context(tier, mode)`: mode from client, tier server-side (anon ⇒ `free`).
3. **Quota** — `check_quota()` → 429 if a free user is over the daily limit.
4. **Conversation** — get-or-create row; thread id `user_{uid}_trip_{trip}_conv_{cid}` keys the checkpointer.
5. **Invoke** — `graph.ainvoke({messages, user_id, trip_id}, cfg, context=ctx)`; user turn persisted first.
6. **Reply** — last `AIMessage` (never a trailing `ToolMessage`); persist it. Graph failure → `AGENT_ERROR_FALLBACK_MSG`, not a 500.
7. **Response** — `ChatResponse(conversation_id, reply, current_flow, interrupt_pending, interrupt_payload)`.

- **HITL resume**: `body.resume` set → `graph.ainvoke(Command(resume=...), ...)` continues a graph paused at plan approval.
- **`/agent/stream`**: same setup, then `stream_agent_events()` over `graph.astream`. Emits typed SSE — `start`, `subagent`, `token` (sub-agent reply only), `tool_call`, `tool_result`, `panel` (side-panel artifacts), `interrupt`. Persisted via an isolated sessionmaker (the generator outlives the request session).
- **Other**: `GET /conversations`, `/conversations/{id}/messages` (ownership-scoped), `POST /conversations/claim` (anon → account), `GET /manifest`.

---

## 3. Graph topology (`agents/graph.py`)

```
START → load_context → summarize → supervisor ──Command(goto)──┐
                                                                │
    planner | concierge | journal | budget ◄───────────────────┤
        │                                                       │
        │   booking ◄── plan (HITL) ◄── target==booking ◄───────┤
        │       └ rejected → END                unknown/gated → END
        ▼ (static edge)
   reflection ──Command(goto: current_flow=REVISE | extract_memory=OK)──→ extract_memory → END
```

**Per-run `AgentContext`** (frozen, not persisted; resolved from tier × mode):

| Flag | FAST | BALANCED | DEEP | Free ceiling |
|---|---|---|---|---|
| `model` hint | FAST | default | DEEP | DEEP→default |
| `allow_reflection` | ✗ | ✓ | ✓ | — |
| `allow_rag` | ✗ | ✓ | ✓ | forced ✗ |
| `allow_memory_write` | ✗ | ✓ | ✓ | — |
| `allow_episodic` | ✓ | ✓ | ✓ | — |
| `max_revisions` | 0 | 1 | 2 | — |
| `allowed_subagents` | all | all | all | no `booking` |

- **supervisor** — structured `SupervisorIntent` → `current_flow=target`. Unknown or tier-gated target → graceful `END` (`BOOKING_UPGRADE_MSG` for free+booking). Booking routes via `plan` first. `destinations=(*SUBAGENTS, "plan", "__end__")`.
- **plan_node (HITL, wired)** — `interrupt()` before the one destructive tool (`book_hotel`). Resume `{approved}`: yes → `booking` + `plan_approved=True`; no → `END`.
- **reflection** — reads `allow_reflection` / `max_revisions`. Disabled or cap reached → `extract_memory`; else judge `REVISE`/`OK`: `REVISE` loops to `current_flow`, `OK` → `extract_memory`. `destinations=(*SUBAGENTS, "extract_memory")`.
- **extract_memory** — always on the accept path; **no-op when `allow_memory_write=False`** (FAST) or no user/store. → `END`.
- Handoffs supervisor→sub-agent and reflection→next are dynamic `Command(goto)`; sub-agent→reflection is a static edge. `agent_recursion_limit=25` backstops cycles.

**Sub-agent ReAct loop** (`subagents/_base.py`): `START → assistant ⇄ tools → END`. `assistant` resolves its model per request from `ctx.model`, `bind_tools` on domain tools **filtered by context** (drop RAG if `!allow_rag`, drop `recall_past_trips` if `!allow_episodic`), and prompts with `system_with_summary`. `ToolNode` maps `ToolException` → `ToolMessage(status="error")` for self-correction.

---

## 4. Sub-agents & tools

Model tier: `FAST_AGENTS` (`summarize`, `journal`, `budget`, `reflection`, `extract_memory`) → `fast_llm_model`; rest → `llm_model`. Per-node overrides via `settings.agent_llm_configs`.

| Sub-agent | Model | Tool groups |
|---|---|---|
| **planner** | full | trip, place, flight, hotel, weather, routing, episodes |
| **concierge** | full | place, weather, routing, tip, rag |
| **journal** | fast | trip, memory |
| **booking** | full | flight, hotel (`book_hotel`† HITL-gated) |
| **budget** | fast | expense, `get_trip_budget` |

| Group | Tools |
|---|---|
| trip | `get_trip_summary`, `get_trip_budget`, `list_trip_places`, `add_place_to_trip`*, `add_itinerary_item`* |
| place | `search_places`, `nearby_places`, `resolve_place`, `parse_nl_query`, `list_place_categories` |
| flight / hotel | `search_flights` · `search_hotels`, `book_hotel`† |
| weather | `get_weather`, `get_packing`, `get_air_quality` |
| routing / tip | `get_route`, `get_city_route` · destination tips |
| expense | `add_expense`*, `list_expenses`, `expense_summary` |
| memory / episodes | `save_user_preference`*, `get_user_preferences` · `recall_past_trips` (gated `allow_episodic`) |
| rag | `search_destination_knowledge` (gated `allow_rag`) |

`*` write · `†` destructive. Flags in `TOOL_METADATA` → surface via `/manifest` + MCP. Each tool opens its own `session_scope()` and maps errors to `ToolException`.

---

## 5. LLM client (`clients/llm.py`)

- No provider SDK imported directly; models built via `init_chat_model()` → switching provider is a settings change. No import-time side effects.
- `get_llm()` / `get_fast_llm()` — base builders. `get_agent_llm(name, model)` — per-node: resolves `agent_llm_configs[name]`, falls back to tier default (`FAST_AGENTS`); `model` = `ModelHint` (`FAST`/`DEEP`/`None`) from context.
- `llm_provider`: `openai` (default) | `anthropic` | `google_genai`; optional `llm_base_url`. Defaults `gpt-4.1` / `gpt-4.1-mini`. Key passed explicitly from settings.
- `FakeLLM` — deterministic (tool calls + structured output), zero network; injected fakes bypass `get_agent_llm`.

---

## 6. State & memory

**`TravelAgentState`** (extends `MessagesState`): `user_id`, `trip_id`, `current_flow`, `summary`, `revisions`, `trip_context`, `instructions`, `plan_approved`. `system_with_summary()` folds `instructions` + `trip_context` + `summary` into one leading system message.

- **Short-term** (`checkpointer.py`): `AsyncPostgresSaver` → `MemorySaver`. Snapshots state per node by `thread_id`; holds the pending HITL interrupt.
- **Long-term** (`store.py`): `PostgresStore` + pgvector → `InMemoryStore`, semantic index on each value's `text`. Namespaced `("users", user_id, kind)`:

| Kind | Written by | Read by | Recall |
|---|---|---|---|
| `prefs` | `save_user_preference` (hot) · `extract_memory` | `get_user_preferences` | 5 |
| `procedural` | `extract_memory` | `load_context` → prompt | 10 |
| `episodes` | `extract_memory` (`approved` if plan passed HITL, else `proposed`) | `recall_past_trips` | 3 |

  Helpers: `upsert_*` / `search_*`, unified `search_memory[_typed]`, dataclasses `Preference`/`Instruction`/`Episode`.
- **Extraction** — `extract_memory` runs post-turn when `allow_memory_write`; calls `extract_memories()`, upserts results. Best-effort (errors swallowed).
- **Compression** — `summarize` node compresses old turns into `summary` once history > `summarize_threshold` (20).

---

## 7. RAG · MCP · observability

- **RAG** (`rag/*.py`): hybrid vector + lexical (RRF) over destination knowledge; OpenAI embeddings + pgvector prod, fakes + in-memory dev/test (1536 dim). Only via concierge's `search_destination_knowledge`, gated by `allow_rag`.
- **MCP** (`mcp/server.py`): same registry re-exposed with readOnly/destructive flags; drops `InjectedStore` tools.
- **Observability** (`observability.py`): optional Langfuse callbacks + trace metadata by `user_id`/`trip_id`; off by default.

---

## 8. Config (`core/config.py`)

| Setting | Default | Drives |
|---|---|---|
| `llm_provider` / `llm_model` / `fast_llm_model` | `openai` / `gpt-4.1` / `gpt-4.1-mini` | Provider + main/fast tiers |
| `agent_llm_configs` / `llm_base_url` | `{}` / None | Per-node overrides · custom endpoint |
| `embedding_model` | `text-embedding-3-small` | RAG + store index |
| `*_api_key` | None | Provider auth (None ⇒ raises on first use) |
| `agent_recursion_limit` / `summarize_threshold` | 25 / 20 | Cycle backstop · compression trigger |
| `langfuse_enabled` + keys | off | Tracing |

**mode** (`ChatMode`) and **tier** (`Tier`) are per-request, not settings → resolved into `AgentContext` (§3).

---

## 9. Gaps (for review)

- **Coarse reflection** — single `REVISE`/`OK` from a fast model, no rubric.
- **Anon `user_id` trust** — anonymous callers supply their own id, which keys the thread + memory namespace (the `claim` endpoint migrates it on login).
- **Double persistence** — `ConversationRepository` rows + checkpointer can drift on failure.
- **Unverified memory writes** — `extract_memory` persists parsed LLM output with no review, dedup only by key-overwrite.
