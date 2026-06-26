# Travel Agent — Backend Chatbot Workflow

> Review + reference doc for the current backend AI-agent workflow.
> Scope: `apps/api/app/` as it exists on `feat/monorepo-fe`. Companion to
> `WORKFLOW_DIAGRAM.md` (root) and `specs/travel-agent/PLAN.md` / `REVIEW.md`.
> Last verified: 2026-06-26.

The backend is a **multi-agent LangGraph application**: a supervisor classifies intent and
hands off to one of five specialist ReAct sub-agents, each bound to a focused tool group. The
graph is stateful (checkpointer + long-term store), provider-agnostic (LLM swapped by config),
and exposed over three HTTP endpoints plus an MCP server.

---

## 1. Components at a glance

| Layer | Module | Responsibility |
|---|---|---|
| HTTP entry | `routers/agent.py` | `/agent/chat`, `/agent/stream`, `/agent/manifest`; persists conversation turns |
| Graph assembly | `agents/graph.py` | Wires nodes + edges, compiles with checkpointer + store |
| Routing | `agents/supervisor.py` | Structured-output intent → `Command(goto=<subagent>)` |
| Cross-cutting nodes | `agents/nodes.py` | `load_context`, `summarize`, `reflection`, `plan_node` (HITL) |
| Specialists | `agents/subagents/*.py` + `_base.py` | ReAct subgraphs (assistant ⇄ tools) |
| Tools | `tools/registry.py` + `tools/*_tools.py` | Domain tool groups, MCP-style metadata |
| LLM client | `clients/llm.py` | `init_chat_model()` provider-agnostic; `FakeLLM` for tests |
| State | `agents/state.py` | `TravelAgentState`, `system_with_summary()` |
| Persistence | `agents/checkpointer.py`, `memory/store.py` | Thread checkpoints + long-term semantic store |
| Memory mgmt | `memory/summarizer.py` | Sliding-window history compression |
| Retrieval | `rag/*.py` | Hybrid (vector + lexical) destination knowledge |
| Convo record | `repositories/conversation.py` | ORM conversation/message rows |
| Tool surface | `mcp/server.py` | Same tool registry re-exposed as an MCP server |
| Observability | `agents/observability.py` | Optional Langfuse callbacks/metadata |

The compiled graph + checkpointer + store are built **once at startup** in
`core/lifespan.py` and held on `app.state.travel_graph`; `get_travel_graph()`
(`routers/agent.py:35`) resolves the shared instance per request (tests override it with a
`FakeLLM`-backed graph).

---

## 2. End-to-end request flow

`POST /agent/chat` (`routers/agent.py:68`):

1. **Resolve conversation** — reuse `conversation_id` or create one via
   `ConversationRepository` (`:73`).
2. **Persist user turn** — `repo.append_message(role="user")` (`:77`).
3. **Build thread id** — `user_{user_id}_trip_{trip_id}_conv_{conversation_id}` (`:53`); this
   keys the checkpointer so a conversation resumes its full state across turns.
4. **Invoke graph** — `graph.ainvoke({messages, user_id, trip_id}, config)` (`:81`). `config`
   carries `thread_id`, `recursion_limit`, Langfuse `callbacks`, and trace `metadata` (`:57`).
5. **Extract reply** — last message content (`:89`), persist assistant turn (`:90`).
6. **Respond** — `ChatResponse(conversation_id, reply, current_flow)`.

`POST /agent/stream` (`:100`) is the same invocation via `graph.astream(..., stream_mode="messages")`,
but filters tokens to **only sub-agent nodes** (`meta["langgraph_node"] in SUBAGENTS`, `:123`) so
supervisor/summarizer/reflection internals never leak into the SSE feed. Anonymous streams get a
unique `stream-<uuid>` thread to avoid checkpoint collisions (`:108`). Wrapped by
`sse_response()` (`core/streaming.py`).

`GET /agent/manifest` (`:132`) returns the sub-agent list + every tool with `read_only` /
`destructive` flags from `TOOL_METADATA`.

---

## 3. Graph topology

Assembled in `agents/graph.py:50-75`:

```
START
  → load_context        # inject active-trip snapshot (best-effort)
  → summarize           # compress old turns if history is long
  → supervisor          # classify intent  ──Command(goto=subagent | END)──┐
                                                                            │
        ┌───────────────────────────────────────────────────────────────┘
        ▼
   [ planner | concierge | journal | booking | budget ]   # ReAct subgraph
        │  (static edge)
        ▼
   reflection            # critique answer ──Command(goto=subagent | END)──→ END
```

Key mechanics:

- **Supervisor** (`supervisor.py:37`) uses `llm.with_structured_output(SupervisorIntent)` to pick
  `target_agent`; unknown intent → graceful fallback message + `goto=END` (`:41`). On success it
  sets `current_flow=target` so reflection knows where to loop back.
- **Sub-agent → reflection** is a static edge (`graph.py:71`); **supervisor → sub-agent** and
  **reflection → sub-agent/END** are dynamic `Command(goto=...)` handoffs (no static edge), which
  is why both nodes declare `destinations=(*SUBAGENTS, "__end__")`.
- **Reflection** (`nodes.py:71`) is a bounded self-correction loop: `_MAX_REVISIONS = 1`. A fast
  LLM judges the last answer `REVISE`/`OK`; on `REVISE` it appends "improve your previous answer",
  bumps `revisions`, and loops back to `current_flow`; otherwise `goto=END`. The counter guarantees
  the loop runs at most once.
- **`agent_recursion_limit`** (default 25) is LangGraph's hard backstop against runaway cycles.
- **`plan_node`** (`nodes.py:92`) is a human-in-the-loop `interrupt()` checkpoint for plan/booking
  approval — defined but **not currently wired into the compiled graph**.

### Sub-agent ReAct loop (`subagents/_base.py`)

Each specialist is its own compiled `StateGraph`:

```
START → assistant ──tools_condition──→ tools → assistant → ... → END
                         (no tool calls) ─────────────────────→ END
```

`assistant` (`_base.py:34`) invokes `llm.bind_tools(tools)` with the domain system prompt +
rolling summary. `ToolNode` runs tool calls, mapping `ToolException` → `ToolMessage(status="error")`
so the model self-corrects. The parent's checkpointer/store propagate into these nested nodes.

---

## 4. Sub-agents and their tools

Tool groups defined in `tools/registry.py:23-29`. Model tier per sub-agent set in `graph.py:56-60`
(`llm` = full reasoning model, `fast_llm` = cheap model).

| Sub-agent | Model | Tools | Purpose |
|---|---|---|---|
| **planner** | full | trip, place, flight, hotel, weather | End-to-end trip planning |
| **concierge** | full | place, weather, **RAG** | Recommendations + destination knowledge |
| **journal** | fast | trip, memory | Notes + user-preference capture/recall |
| **booking** | full | flight, hotel | Quotes + guarded `book_hotel` (destructive) |
| **budget** | fast | expense, `get_trip_budget` | Expense tracking / budget |

**Tool inventory** (`tools/*_tools.py`):

- **trip**: `get_trip_summary`, `get_trip_budget`, `list_trip_places`, `add_place_to_trip`*, `add_itinerary_item`*
- **place**: `search_places`, `nearby_places`, `resolve_place`, `parse_nl_query`, `list_place_categories`
- **flight**: `search_flights`
- **hotel**: `search_hotels`, `book_hotel`†
- **weather**: `get_weather`, `get_packing`, `get_air_quality`
- **expense**: `add_expense`*, `list_expenses`, `expense_summary`
- **memory**: `save_user_preference`*, `get_user_preferences`
- **rag**: `search_destination_knowledge`

`*` = write (`readOnly=False`), `†` = destructive (irreversible side effect). Flags live in
`TOOL_METADATA` (`registry.py:38-55`) and surface through `/agent/manifest` and the MCP server.
Each tool opens its own `session_scope()` for DB access and maps domain errors to `ToolException`.

---

## 5. LLM client

`clients/llm.py` — the agent layer never imports a provider SDK. `get_llm()` /
`get_fast_llm()` call `init_chat_model(name, model_provider=settings.llm_provider, api_key=...)`,
so switching provider is a settings change.

- `llm_provider`: `openai` (default) | `anthropic` | `google`
- `llm_model`: full reasoning model (default `gpt-4.1`) — supervisor, planner, concierge, booking
- `fast_llm_model`: cheap model (default `gpt-4.1-mini`) — summarize, reflection, journal, budget
- API key passed **explicitly from settings** (never env leakage); absent key → client raises on
  first use, not at import.
- `FakeLLM` (`:59`) scripts deterministic responses (incl. tool calls + structured output) so the
  full graph runs in tests with zero network.

---

## 6. State & memory

**`TravelAgentState`** (`agents/state.py`, extends `MessagesState`): `user_id`, `trip_id`,
`current_flow`, `summary`, `revisions`, `messages`. `system_with_summary()` re-injects the rolling
`summary` into each node's system prompt.

**Short-term (per-thread)** — `agents/checkpointer.py`: `AsyncPostgresSaver` in production,
degrades to `MemorySaver`. Snapshots full state after each node, keyed by `thread_id` → enables
multi-turn resume.

**Long-term (cross-session)** — `memory/store.py`: `PostgresStore` + pgvector, degrades to
`InMemoryStore` with fake embeddings. Holds user preferences / trip facts, addressable by
`(namespace, key)`, semantically searchable. Both opened once in `core/lifespan.py`.

**History compression** — `memory/summarizer.py`: when `should_summarize()` (default threshold 20
messages) the `summarize` node compresses old turns into `summary` and drops them from `messages`,
keeping the last few turns.

---

## 7. RAG, MCP, observability

- **RAG** (`rag/*.py`): hybrid retrieval (vector similarity + lexical, Reciprocal Rank Fusion) over
  destination knowledge; OpenAI embeddings + pgvector in prod, deterministic fakes + in-memory in
  dev/test (1536 dims). Reached only through the concierge's `search_destination_knowledge` tool.
- **MCP** (`mcp/server.py`): re-exposes the same tool registry as an MCP server with
  readOnly/destructive annotations; filters out `InjectedStore`-dependent tools.
- **Observability** (`agents/observability.py`): optional Langfuse `CallbackHandler` + trace
  metadata grouped by `user_id`/`trip_id`; disabled by default (no network in CI).

---

## 8. Configuration (`core/config.py`)

| Setting | Default | Drives |
|---|---|---|
| `llm_provider` | `openai` | Which SDK `init_chat_model` builds |
| `llm_model` | `gpt-4.1` | Full-reasoning sub-agents + supervisor |
| `fast_llm_model` | `gpt-4.1-mini` | Routing-tier nodes + summarize/reflection |
| `embedding_model` | `text-embedding-3-small` | RAG + long-term store index |
| `openai/anthropic/google_api_key` | None | Provider auth; None ⇒ `FakeLLM` |
| `agent_recursion_limit` | 25 | LangGraph cycle backstop |
| `summarize_threshold` | 20 | History compression trigger |
| `langfuse_enabled` + keys | off | Tracing |

---

## 9. Observations / gaps (for review)

- **`plan_node` HITL is dead code** — defined in `nodes.py:92` but not added to the compiled graph;
  there is no approval gate before `book_hotel` (the one destructive tool). If guarded booking is a
  requirement, this is the missing wiring.
- **Reflection critic is coarse** — a single `REVISE`/`OK` verdict from a fast model with no
  rubric; bounded to 1 revision. Cheap but low-signal.
- **No auth on `/agent/*`** — consistent with the mock-backend posture, but `user_id` is
  caller-supplied and trusted for both checkpoint threads and the long-term memory namespace.
- **Conversation persisted twice** — `ConversationRepository` rows *and* the checkpointer both
  store turns; they can drift (e.g. a failed `ainvoke` leaves the user row without a reply).
