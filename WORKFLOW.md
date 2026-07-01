# Travel Agent — Backend Chatbot Workflow

> Review + reference doc for the current backend AI-agent workflow.
> Scope: `apps/api/app/` as it exists on `feat/agent-memory-layers`. Companion to
> `WORKFLOW_DIAGRAM.md` (root, `make diagram` → HTML) and `specs/travel-agent/` /
> `specs/agent-memory-layers/`.
> Last verified: 2026-07-01.

The backend is a **multi-agent LangGraph application**: a supervisor classifies intent and
hands off to one of five specialist ReAct sub-agents, each bound to a focused tool group. The
graph is stateful (checkpointer + long-term store), provider-agnostic (LLM swapped by config),
capability-aware (per-request **mode** × **tier** context), and exposed over HTTP endpoints plus
an MCP server. It carries three long-term memory layers — preferences, procedural instructions,
and episodic past-trip outcomes — read on the way in and written in the background on the way out.

---

## 1. Components at a glance

| Layer | Module | Responsibility |
|---|---|---|
| HTTP entry | `routers/agent.py` | `/agent/chat`, `/agent/stream`, `/agent/manifest`, `/agent/conversations*`; persists turns |
| Auth / quota | `core/auth.py`, `services/quota_service.py` | Optional Supabase JWT (`user_id` = JWT sub); per-tier quota guard |
| Run context | `agents/context.py`, `agents/constants.py`, `enums.py` | `AgentContext` resolved from (tier, mode) → concrete capability flags |
| Graph assembly | `agents/graph.py` | Wires nodes + edges, compiles with checkpointer + store |
| Routing | `agents/supervisor.py` | Structured-output intent → `Command(goto=<subagent>)`; tier-gates targets |
| Cross-cutting nodes | `agents/nodes.py` | `load_context`, `summarize`, `reflection`, `plan_node` (HITL), `extract_memory` |
| Specialists | `agents/subagents/*.py` + `_base.py` | ReAct subgraphs (assistant ⇄ tools), per-request model + tool gating |
| Tools | `tools/registry.py` + `tools/*_tools.py` | Domain tool groups, MCP-style metadata |
| LLM client | `clients/llm.py` | `init_chat_model()` provider-agnostic; per-node `get_agent_llm`; `FakeLLM` for tests |
| State | `agents/state.py` | `TravelAgentState`, `system_with_summary()` |
| Persistence | `agents/checkpointer.py`, `memory/store.py` | Thread checkpoints + long-term semantic store |
| Memory write | `memory/extractor.py`, `agents/nodes.py` | Background post-turn extraction → prefs / procedural / episodes |
| Memory mgmt | `memory/summarizer.py` | Sliding-window history compression |
| Streaming | `streaming/mapper.py`, `streaming/persistence.py`, `core/streaming.py` | Typed SSE taxonomy + isolated-session persistence |
| Retrieval | `rag/*.py` | Hybrid (vector + lexical) destination knowledge |
| Convo record | `repositories/conversation.py` | ORM conversation/message rows |
| Tool surface | `mcp/server.py` | Same tool registry re-exposed as an MCP server |
| Observability | `agents/observability.py` | Optional Langfuse callbacks/metadata |

The compiled graph + checkpointer + store are built **once at startup** in
`core/lifespan.py` and held on `app.state.travel_graph`; `get_travel_graph()`
(`routers/agent.py`) resolves the shared instance per request (tests override it with a
`FakeLLM`-backed graph).

---

## 2. End-to-end request flow

`POST /agent/chat` (`agent_chat`):

1. **Resolve user** — `_effective_user_id()` returns the JWT sub when a valid Supabase token is
   present, else the client-supplied `user_id` (anonymous). A valid token makes the body/query
   `user_id` ignored, blocking id spoofing.
2. **Resolve context** — `_resolve_context()` → `resolve_agent_context(tier, mode)`: **mode** is
   client-chosen (`fast | balanced | deep`); **tier** is resolved server-side from the `users`
   table (anonymous ⇒ `free`). Yields the per-run `AgentContext` (see §3).
3. **Quota guard** — `check_quota(user_id, tier, repo)` raises `QuotaExceededError` (429) before
   any work begins.
4. **Resolve conversation** — reuse `conversation_id` or create one via `ConversationRepository`.
5. **Build thread id** — `user_{uid}_trip_{trip_id or 'none'}_conv_{conversation_id}`; keys the
   checkpointer so a conversation resumes its full state across turns.
6. **Invoke graph** — `graph.ainvoke({messages, user_id, trip_id}, cfg, context=ctx)`. `cfg`
   carries `thread_id`, `recursion_limit`, Langfuse `callbacks`, and trace `metadata`. The user
   turn is persisted (`append_message(role="user")`) before invoke.
7. **Resume path** — when `body.resume` is set, the call is `graph.ainvoke(Command(resume=...),
   cfg, context=ctx)` instead: it resumes a graph paused at the plan-approval `interrupt` (§3).
8. **Extract reply** — pick the last **`AIMessage`** (never a trailing `ToolMessage`); persist the
   assistant turn. On any graph failure a readable `AGENT_ERROR_FALLBACK_MSG` is returned/persisted
   instead of a 500.
9. **Respond** — `ChatResponse(conversation_id, reply, current_flow, interrupt_pending,
   interrupt_payload)`. When an interrupt is pending, `reply=""` and the payload carries the draft
   plan for the client to approve/reject.

`POST /agent/stream` (`agent_stream`) is the same setup, then streams via
`stream_agent_events()` (`streaming/mapper.py`) over `graph.astream(stream_mode=["messages",
"updates"], subgraphs=True)`. It emits a **typed SSE taxonomy** — `start`, `subagent`, `token`
(only the sub-agent assistant's natural-language reply; supervisor/summarizer/reflection chatter
and raw ToolNode JSON are filtered), `tool_call`, `tool_result`, `panel` (side-panel artifacts
like the route drawer), and `interrupt`. The assistant turn is persisted through an **isolated
sessionmaker** bound to the request session's engine (`persist_assistant_turn`), because the SSE
generator outlives the request-scoped session. `session.commit()` runs before streaming to release
the SQLite write lock.

Other endpoints: `GET /agent/conversations` and `/agent/conversations/{id}/messages` (ownership-
scoped history), `POST /agent/conversations/claim` (reassign anonymous history to a logged-in
user), and `GET /agent/manifest` (sub-agent list + every tool with `read_only` / `destructive`
flags from `TOOL_METADATA`).

---

## 3. Graph topology

Assembled in `agents/graph.py`:

```
START
  → load_context        # active-trip snapshot + procedural instructions from store
  → summarize           # compress old turns if history is long
  → supervisor          # classify intent + tier-gate ──Command(goto=…)──┐
                                                                          │
        ┌── planner | concierge | journal | budget ◄────────────────────┤
        │                                                                 │
        │   booking ◄── plan (HITL interrupt) ◄── (target == booking) ◄──┘
        │       ▲                    │                       │
        │       └── approved         └── rejected → END      └── unknown / tier-gated → END
        ▼  (static edge)
   reflection            # critique answer ──Command(goto=current_flow | extract_memory)
        │
        ▼
   extract_memory        # background write (skipped in FAST) → END
```

**Per-run context (`AgentContext`, `agents/context.py`).** The graph is invoked with a frozen,
non-persisted context resolved once from (tier, mode) by `resolve_agent_context`. Nodes/tools just
read its flags:

| Flag | FAST | BALANCED | DEEP | Free-tier ceiling |
|---|---|---|---|---|
| `model` (hint) | FAST | default | DEEP | DEEP → default |
| `allow_reflection` | ✗ | ✓ | ✓ | — |
| `allow_rag` | ✗ | ✓ | ✓ | forced ✗ |
| `allow_memory_write` | ✗ | ✓ | ✓ | — |
| `allow_episodic` | ✓ | ✓ | ✓ | — |
| `max_revisions` | 0 | 1 | 2 | — |
| `allowed_subagents` | all | all | all | excludes `booking` |

Key mechanics:

- **Supervisor** (`make_supervisor`) uses `llm.with_structured_output(SupervisorIntent,
  method="function_calling")` to pick `target_agent`; unknown intent → graceful fallback + `goto=END`.
  On success it sets `current_flow=target`. **Tier gate:** if `ctx.allowed_subagents` excludes the
  target, it degrades gracefully (`BOOKING_UPGRADE_MSG` for free users hitting `booking`) instead of
  routing. Booking is routed through the **`plan`** node first (`next_node = "plan" if target ==
  "booking" else target`).
- **`plan_node` (HITL, now wired)** — a human-in-the-loop `interrupt()` gate before the one
  destructive tool (`book_hotel`). It surfaces the draft plan and pauses; the client resumes with
  `Command(resume={"approved": True|False})`. Approved → `goto=booking` and sets `plan_approved=True`
  (so `extract_memory` records `outcome="approved"`); rejected → cancels to `END`.
  `destinations=("booking", "__end__")`.
- **Sub-agent → reflection** is a static edge; **supervisor → sub-agent/plan** and
  **reflection → sub-agent/extract_memory** are dynamic `Command(goto=...)` handoffs (no static
  edge), so `supervisor` declares `destinations=(*SUBAGENTS, "plan", "__end__")` and `reflection`
  declares `destinations=(*SUBAGENTS, "extract_memory")`.
- **Reflection** (`make_reflection_node`) is a bounded self-correction loop reading
  `ctx.allow_reflection` and `ctx.max_revisions` (fallback `DEFAULT_MAX_REVISIONS = 1`). When
  reflection is disabled (FAST) or the revision cap is reached, it goes straight to
  `extract_memory`. Otherwise a model judges the last answer `REVISE`/`OK`; on `REVISE` it appends
  "improve your previous answer", bumps `revisions`, and loops back to `current_flow`; on `OK` it
  proceeds to `extract_memory`.
- **`extract_memory`** (`make_extract_memory_node`) always runs before `END` on the accept path,
  but is a **no-op when `ctx.allow_memory_write` is False** (FAST) or when there is no `user_id` /
  store. See §6.
- **`agent_recursion_limit`** (default 25) is LangGraph's hard backstop against runaway cycles.

### Sub-agent ReAct loop (`subagents/_base.py`)

Each specialist is its own compiled `StateGraph`:

```
START → assistant ──tools_condition──→ tools → assistant → ... → END
                         (no tool calls) ─────────────────────→ END
```

`assistant` resolves its chat model **per request** from `ctx.model` (via the graph's
`resolver_for(name)`), then `bind_tools` on the domain tools — **filtered by context**: the RAG
tool is dropped when `allow_rag` is False, and the episodic `recall_past_trips` tool is dropped when
`allow_episodic` is False. It calls the model with `system_with_summary(state, system)`. `ToolNode`
runs tool calls with `handle_tool_errors`, mapping `ToolException` → `ToolMessage(status="error")`
so the model self-corrects. The parent's checkpointer/store propagate into these nested nodes.

---

## 4. Sub-agents and their tools

Tool groups defined in `tools/registry.py`. Model tier is per-node: nodes in `FAST_AGENTS`
(`summarize`, `journal`, `budget`, `reflection`, `extract_memory`) default to the cheap
`fast_llm_model`; everything else (supervisor, planner, concierge, booking) defaults to the main
`llm_model`. Per-node overrides live in `settings.agent_llm_configs` (see §5).

| Sub-agent | Model | Tools | Purpose |
|---|---|---|---|
| **planner** | full | trip, place, flight, hotel, weather, routing, **episodes** | End-to-end trip planning; recalls past trips |
| **concierge** | full | place, weather, routing, tip, **RAG** | Recommendations + destination knowledge |
| **journal** | fast | trip, memory | Notes + user-preference capture/recall |
| **booking** | full | flight, hotel | Quotes + guarded `book_hotel` (destructive, HITL-gated) |
| **budget** | fast | expense, `get_trip_budget` | Expense tracking / budget |

**Tool inventory** (`tools/*_tools.py`):

- **trip**: `get_trip_summary`, `get_trip_budget`, `list_trip_places`, `add_place_to_trip`*, `add_itinerary_item`*
- **place**: `search_places`, `nearby_places`, `resolve_place`, `parse_nl_query`, `list_place_categories`
- **flight**: `search_flights`
- **hotel**: `search_hotels`, `book_hotel`†
- **weather**: `get_weather`, `get_packing`, `get_air_quality`
- **routing**: `get_route`, `get_city_route`
- **tip**: destination tips lookup
- **expense**: `add_expense`*, `list_expenses`, `expense_summary`
- **memory**: `save_user_preference`*, `get_user_preferences`
- **episodes**: `recall_past_trips` (gated by `allow_episodic`)
- **rag**: `search_destination_knowledge` (gated by `allow_rag`)

`*` = write (`readOnly=False`), `†` = destructive (irreversible side effect). Flags live in
`TOOL_METADATA` (`registry.py`) and surface through `/agent/manifest` and the MCP server. Each tool
opens its own `session_scope()` for DB access and maps domain errors to `ToolException`.

---

## 5. LLM client

`clients/llm.py` — the agent layer never imports a provider SDK. Models are built via
`init_chat_model(name, model_provider=settings.llm_provider, api_key=…)`, so switching provider is a
settings change. Importing the module has no side effects (no network, no key validation).

- **`get_llm()` / `get_fast_llm()`** — the base builders (main vs `fast_llm_model` tier).
- **`get_agent_llm(agent_name, model=…)`** — per-node builder used by the graph. Resolves
  `settings.agent_llm_configs[agent_name]` (provider/model/temperature/extra overrides), falling
  back to the node's tier default (`FAST_AGENTS` membership). The `model` argument is the semantic
  `ModelHint` from `AgentContext.model`: `None` → per-agent default, `FAST` → force fast tier,
  `DEEP` → force main tier (no separate "strong" model configured yet).
- `llm_provider`: `openai` (default) | `anthropic` | `google_genai`; optional `llm_base_url`.
- `llm_model` default `gpt-4.1`; `fast_llm_model` default `gpt-4.1-mini`.
- API key passed **explicitly from settings** (never env leakage); absent key → client raises on
  first use, not at import.
- `FakeLLM` scripts deterministic responses (incl. tool calls + structured output) so the full graph
  runs in tests with zero network. In `build_graph`, injected `llm`/`fast_llm` fakes bypass
  `get_agent_llm` entirely, so tests stay deterministic regardless of `ctx.model`.

---

## 6. State & memory

**`TravelAgentState`** (`agents/state.py`, extends `MessagesState`): `user_id`, `trip_id`,
`current_flow`, `summary`, `revisions`, `trip_context`, `instructions`, `plan_approved`.
`system_with_summary()` folds `instructions` (highest weight) + `trip_context` + `summary` into a
single leading `SystemMessage` at each model call (kept out of `messages` so providers that require
one leading system message stay happy).

**Short-term (per-thread)** — `agents/checkpointer.py`: `AsyncPostgresSaver` in production, degrades
to `MemorySaver`. Snapshots full state after each node, keyed by `thread_id` → enables multi-turn
resume (and holds the pending HITL interrupt).

**Long-term (cross-session)** — `memory/store.py`: `PostgresStore` + pgvector, degrades to
`InMemoryStore` with fake embeddings. Both carry a semantic index over each value's `text` field.
Memory is namespaced per user as **`("users", user_id, kind)`**, with three structured kinds
(`MemoryKind`):

| Kind | Written by | Read by | Default recall |
|---|---|---|---|
| `prefs` | `journal` tool `save_user_preference` (hot path) · `extract_memory` (background) | `journal` `get_user_preferences` | 5 |
| `procedural` | `extract_memory` | `load_context` → system prompt | 10 |
| `episodes` | `extract_memory` (`outcome="approved"` when the plan passed the HITL gate, else `"proposed"`) | `planner` tool `recall_past_trips` | 3 |

`store.py` exposes per-kind helpers (`upsert_*` / `search_*` / `get_instructions`) plus a unified
`search_memory` / `search_memory_typed` dispatcher and typed dataclasses (`Preference`,
`Instruction`, `Episode`). Both backends are opened once in `core/lifespan.py`.

**Background extraction** — `extract_memory` (§3) runs after each accepted turn when
`allow_memory_write` is True. It calls `extract_memories(messages, llm)` (`memory/extractor.py`) and
upserts the parsed preferences / instructions / episodes. It is **best-effort**: any error is
swallowed so a failed extraction never breaks the reply.

**History compression** — `memory/summarizer.py`: when `should_summarize()` (default threshold 20
messages) the `summarize` node compresses old turns into `summary` and drops them from `messages`,
keeping the last few turns.

---

## 7. RAG, MCP, observability

- **RAG** (`rag/*.py`): hybrid retrieval (vector similarity + lexical, Reciprocal Rank Fusion) over
  destination knowledge; OpenAI embeddings + pgvector in prod, deterministic fakes + in-memory in
  dev/test (1536 dims). Reached only through the concierge's `search_destination_knowledge` tool,
  which is filtered out when `allow_rag` is False (FAST mode / free tier).
- **MCP** (`mcp/server.py`): re-exposes the same tool registry as an MCP server with
  readOnly/destructive annotations; filters out `InjectedStore`-dependent tools.
- **Observability** (`agents/observability.py`): optional Langfuse `CallbackHandler` + trace
  metadata grouped by `user_id` / `trip_id`; disabled by default (no network in CI). Handler is
  built once and cached per settings combination.

---

## 8. Configuration (`core/config.py`)

| Setting | Default | Drives |
|---|---|---|
| `llm_provider` | `openai` | Which SDK `init_chat_model` builds |
| `llm_model` | `gpt-4.1` | Main-tier nodes (supervisor, planner, concierge, booking) |
| `fast_llm_model` | `gpt-4.1-mini` | `FAST_AGENTS` nodes (summarize, reflection, journal, budget, extract_memory) |
| `agent_llm_configs` | `{}` | Per-node provider/model/temperature overrides (`AgentLLMConfig`) |
| `llm_base_url` | None | Optional custom endpoint (proxy/self-host) |
| `embedding_model` | `text-embedding-3-small` | RAG + long-term store index |
| `openai/anthropic/google_api_key` | None | Provider auth; None ⇒ `FakeLLM` behavior on first use |
| `agent_recursion_limit` | 25 | LangGraph cycle backstop |
| `summarize_threshold` | 20 | History compression trigger |
| `langfuse_enabled` + keys | off | Tracing |

Per-request **mode** (`ChatMode`) and **tier** (`Tier`) are not settings — they are resolved at
request time into `AgentContext` (§3). Tier comes from the `users` table; mode from the client body.

---

## 9. Observations / gaps (for review)

- **Reflection critic is coarse** — a single `REVISE`/`OK` verdict from a fast model with no rubric;
  bounded to `max_revisions` (0 in FAST, 1 BALANCED, 2 DEEP). Cheap but low-signal.
- **`user_id` trust boundary** — authenticated requests bind `user_id` to the verified JWT sub, but
  **anonymous** callers still supply their own `user_id`, which keys both the checkpoint thread and
  the long-term memory namespace. Anonymous history can therefore be addressed by anyone who knows
  the id (the `claim` endpoint exists to migrate it to a real account on login).
- **Conversation persisted twice** — `ConversationRepository` rows *and* the checkpointer both store
  turns; they can drift (e.g. a failed `ainvoke` persists the fallback reply but the checkpoint may
  hold different state).
- **Memory extraction is unverified LLM output** — `extract_memory` writes whatever the extractor
  parses, with no human review and no dedup beyond key-overwrite; a noisy turn can persist
  low-value preferences/instructions. Best-effort by design, but worth a quality pass.
