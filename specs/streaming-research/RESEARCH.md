# Streaming Architecture Research — `chat-agents` vs `travel-pi`

> Deep review of how the sibling repo `chat-agents` handles backend streaming,
> graph construction, and the event/chunk-mapping layer — benchmarked against
> the official LangGraph streaming docs and our current `travel-pi` implementation.
>
> Date: 2026-06-27 · Sources: `chat-agents@feat/sandboxes`, `travel-pi@v3`,
> docs.langchain.com/oss/python/langgraph (streaming + event-streaming).

---

## 1. Executive summary

`chat-agents` runs a **mature, event-typed SSE protocol**: a dedicated
`app/streaming/` package translates raw multi-mode LangGraph stream items into a
**named, JSON-shaped event taxonomy** (token deltas, tool calls, sub-agent
lifecycle, file artifacts, budget/compression telemetry, HITL plan pauses). It
uses `sse-starlette`'s `EventSourceResponse`, consumes **four stream modes at
once** (`values`, `messages`, `updates`, `custom`), and centralises mapping in a
`ChunkMapper` class with extensive dedup/edge-case handling.

`travel-pi` runs a **lean token-only SSE stream**: `graph.astream(stream_mode="messages",
subgraphs=True)` with inline filtering, emitting raw `data: <text>` token frames plus
two named events (`reset`, `interrupt`) and a `[DONE]` sentinel. No typed event
taxonomy, no tool/sub-agent lifecycle events, no `ChunkMapper`.

Both build the graph once and share it; both use `AsyncPostgresSaver` (degrading to
`MemorySaver`). Neither uses the newer `astream_events` v3 protocol.

**Bottom line:** our core mechanics are sound and aligned with the docs. The gap is
**richness of the event protocol**, not correctness. Adopting a typed event layer is
worthwhile *only if the frontend needs to render tool/sub-agent activity* — otherwise
it's speculative complexity.

---

## 2. `chat-agents` backend streaming

### 2.1 Endpoints & wire format

Three streaming endpoints, all returning `sse_starlette.sse.EventSourceResponse`
(media type `text/event-stream; charset=utf-8`):

| Endpoint | File:line |
|---|---|
| `POST /conversations/{conv_id}/messages` (chat) | `app/chat/router.py:127-209` |
| `POST /research` | `app/research/router.py:112-274` |
| `POST /research/{thread_id}/decide` (HITL resume) | `app/research/router.py:277-321` |

Every event is a `{"event": "<name>", "data": "<json-string>"}` dict, serialised by
`EventSourceResponse` to:

```
event: <name>\r\n
data: <json_string>\r\n\r\n
```

Factory helper `_sse(event, data)` in both `events.py:19-21` and `chat_events.py:5-6`.

### 2.2 Stream modes

- **Chat:** `stream_mode=["messages", "updates"]`, `subgraphs=True`, `version="v2"`
  (`chat/router.py:152-165`).
- **Research:** `stream_mode=["values", "messages", "updates", "custom"]`,
  `subgraphs=True`, `version="v2"` (`research/router.py:80-87`).
- **Reject drain:** `stream_mode=["updates"]` discarded silently (`router.py:343-350`).

### 2.3 Generator pipeline

Chat (`chat/router.py:136`): `astream` → branch on `chunk["type"]`:
`"messages"` → filter `AIMessageChunk` by `_parent_specialist()` (parses
`langgraph_checkpoint_ns`, only `{responder, researcher, clarifier}`) → emit
`chat.text_delta`; `"updates"` → emit `chat.specialist_active`. Post-loop: DB persist +
`chat.message_complete`.

Research (`research/router.py:47-109`): delegates each `(mode, chunk)` to
`ChunkMapper.process()`. Per-chunk token accounting accumulates `cumulative_tokens`;
exceeding `settings.MAX_TOKENS_PER_RUN` emits `budget_exceeded` and returns early.

### 2.4 Cancellation / error handling

- Chat: catches `asyncio.CancelledError` → `chat.error(code="cancelled")` then re-raises;
  other exceptions → `chat.error(code="internal")` (`chat/router.py:200-208`).
- Research: `async with asyncio.timeout(RESEARCH_TIMEOUT_S)` → `error("timeout")`;
  `RateLimitError` → `error("rate_limited")`; else `error("internal")`; `finally`
  always emits `stream_end` (`research/router.py:167-272`).
- No heartbeat/keepalive configured (`sse_starlette` `ping=N` not set). No explicit
  buffering/batching — yielded token-by-token. `quant_compute` uses `mode="custom"` to
  keep large base64 PNGs out of model context.

### 2.5 Graph construction & init

Two independent compiled graphs:

**Chat graph** (`app/chat/service/graph.py`): supervisor/multi-agent.
`START → supervisor → {responder→END, researcher→supervisor (loop), clarifier→END}`,
all `Command`-driven. State = `ChatState(MessagesState)` + `routing_decision`,
`awaiting_clarification`. Cached via `@functools.lru_cache(maxsize=8)` keyed on domain
(`graph.py:141`).

**Research graph** (`app/research/service/research_graph.py`): linear with HITL.
`START → plan → {rejected→END, research→END}`. `plan` calls `interrupt(...)`; `research`
is a `deepagents.create_deep_agent` subgraph (internal researcher + critic). State =
`ResearchGraphState(TypedDict, total=False)`. Cached via `@lru_cache(maxsize=15)`.

**Checkpointer/store** (`app/stores/memory_store.py:63-86`): `AsyncPostgresSaver` +
`AsyncPostgresStore` (schema `langstore`), opened in `lifespan_stores()`. Both graphs
`compile(checkpointer=get_checkpointer(), store=get_store())`. `thread_id` = fresh
`uuid4().hex` (research) or conversation UUID (chat).

### 2.6 The `app/streaming/` package — event model

**`events.py`** — research/deep-agent taxonomy (~20 events):
`stream_start`, `stream_end`, `stream_paused`, `text_delta`, `todo_updated`,
`file_saved`, `tool_call_started`, `tool_call_completed`, `subagent_started`,
`subagent_completed`, `reflection_logged`, `compression_observed`, `memory_pressure`,
`budget_exceeded`, `token_breakdown`, `plan_pending`, `plan_rejected`, `memory_updated`,
`error`. Typed literals: `AgentRole = {main, researcher, critic}`,
`ErrorReason = {timeout, internal, rate_limited, empty_report}`. Previews truncated
(args 300, result 300, file preview 500, reflection 2000 chars).

**`chat_events.py`** — parallel `chat.*` set: `message_started`, `text_delta`,
`message_complete` (finish_reason stop|cancelled|max_tokens), `specialist_active`,
`thinking_started`, `error`.

**`chunk_mapper.py`** — `ChunkMapper.process(mode, chunk, *, ns=())` (`:139`) dispatches:
- `messages`: only `ai`/`AIMessageChunk`; tracks `usage_metadata` per role via
  `_resolve_role(meta["lc_agent_name"])`; non-empty content → `text_delta`; skips `plan`
  namespace; tool calls *logged but not emitted here*.
- `updates` (`_handle_updates :193`): `__interrupt__` → plan pending; `todos` →
  `todo_updated`; `files` → `file_saved` (or `memory_updated` for `/memories/*`);
  AIMessage `tool_calls` → `tool_call_started` (+`subagent_started` for `task`,
  `reflection_logged` for `think_tool`); ToolMessage → `tool_call_completed`
  (+`subagent_completed`). Heavy dedup via `_emitted_tool_starts`, `_emitted_reflections`,
  `_active_subagents`.
- `values` (`_handle_values_snapshot :382`): tiktoken estimate → `compression_observed`
  + peak tracking for `memory_pressure`.
- `custom` `kind=="quant_artifact"` → `file_saved` with `content_b64`/`mime`.

**`extract.py`** — `extract_final_report(state, min_chars=500)`: last message must be a
complete `AIMessage` (no pending tool_calls, ≥500 chars) else `None`.

**`__init__.py`** — empty; consumers import submodules directly.

Edge cases (from tests): dedup of todos/files/tool starts/completions/reflections;
orphan ToolMessage skipped; `Overwrite`/`Add` channel wrappers unwrapped via `_as_list`;
non-string file content coerced; role always `"main"` in updates mode; empty reflection
dropped; parent/child tool tracking via `parent_id`.

---

## 3. Official LangGraph reference (docs.langchain.com, v1.x)

- Two APIs: **`astream(stream_mode=...)`** (pull, per-step) and **`astream_events(version="v3")`**
  (push, protocol events — beta since v1.2.0, now preferred for new code).
- `version="v2"` of `astream` yields a unified `StreamPart` dict:
  `{"type", "ns", "data"}`. Modes: `values` (full state), `updates`
  (`{node: changed}`), `messages` (`(AIMessageChunk, metadata)` tuple — token streaming),
  `custom` (user payload via `get_stream_writer()`), plus `debug/checkpoints/tasks`.
- `messages` mode metadata carries `langgraph_node`, `tags`, `run_id` — filter tokens by
  node/tag; suppress a node with `.with_config({"tags": ["nostream"]})`.
- Multiple modes → pass a list, branch on `chunk["type"]`.
- Subgraphs: `subgraphs=True`, inspect `chunk["ns"]` (`[]` root, `["node:task_id"]` sub).
- Custom data: `get_stream_writer()` (sync / Py≥3.11) or `writer: StreamWriter` param
  (async, Py<3.11) → consume via `stream_mode="custom"`.
- v3 protocol: `ProtocolEvent {seq, method, params{namespace, timestamp, data}}` with
  projections `stream.messages`, `.values`, `.output`, `.subgraphs`, `.interrupts`.
  Older callback `astream_events(version="v2")` (`on_chat_model_stream` etc.) still works
  but is superseded.
- **No official SSE tutorial** in OSS docs — the documented path is LangGraph Platform /
  Agent Server. Self-hosted FastAPI wrapping `astream` in a `StreamingResponse` /
  `EventSourceResponse` with `data: <json>\n\n` is the community-standard pattern (what
  both our repos do).

---

## 4. `travel-pi` current state

| Aspect | Current implementation |
|---|---|
| Endpoints | `POST /agent/chat` (`ainvoke`, JSON), `POST /agent/stream` (SSE), `GET /agent/manifest` — `app/routers/agent.py` |
| Stream call | `graph.astream(stream_input, cfg, stream_mode="messages", subgraphs=True)` (`agent.py:154-158`) — **no `version="v2"`**, single mode |
| Wire format | `data: <text>\n\n` token frames; named `event:` for `reset`/`interrupt`; `data: [DONE]\n\n` terminal (`app/core/streaming.py`) |
| Filtering | inline in `tokens()`: namespace root ∈ `SUBAGENTS` and `isinstance(chunk, AIMessage)` |
| Graph | `START → load_context → summarize → supervisor → {plan, planner, concierge, journal, booking, budget} → reflection → (loop\|END)`; supervisor = structured-output router; 5 ReAct subgraphs; `revisions` self-correction loop (`app/agents/graph.py:81-90`) |
| State | `MessagesState` + `user_id, trip_id, current_flow, summary, revisions, trip_context` (`app/agents/state.py:15-26`) |
| Init | built once in `core/lifespan.py:74` → `app.state.travel_graph`; DI via `get_travel_graph(request)` |
| Checkpointer | `AsyncPostgresSaver` (Postgres) / `MemorySaver` (SQLite/test) — `app/agents/checkpointer.py` |
| HITL | `/agent/chat` supports `Command(resume=...)`; stream emits `interrupt` named event |

**Does NOT exist:** typed event taxonomy, `ChunkMapper`/event module, tool-call or
sub-agent lifecycle events, `updates`/`values`/`custom` modes, `astream_events`,
budget/compression telemetry, `sse-starlette`, heartbeat/ping.

---

## 5. Side-by-side

| Dimension | `chat-agents` | `travel-pi` |
|---|---|---|
| SSE transport | `sse-starlette` `EventSourceResponse` | hand-rolled `StreamingResponse` + `data:` framing |
| Event protocol | ~26 typed named events, JSON payloads | raw token text + `reset`/`interrupt`/`[DONE]` |
| Stream modes | 4 at once (`values,messages,updates,custom`) | 1 (`messages`) |
| `version="v2"` | yes | no (uses legacy tuple unpack `ns, (chunk, _meta)`) |
| Mapping layer | `app/streaming/` package + `ChunkMapper` | inline filter in router |
| Tool/sub-agent visibility | full lifecycle events | none (tokens only) |
| Telemetry | budget, compression, memory pressure, token breakdown | none |
| Graph build/share | `lru_cache` module singleton | `app.state` + DI |
| Checkpointer | AsyncPostgresSaver + AsyncPostgresStore | AsyncPostgresSaver (no Store) |
| Cancellation | explicit `CancelledError` re-raise + `error` event | (verify — inline) |
| Final-report guard | `extract.py` (≥500 chars, no pending tools) | n/a |

---

## 6. Recommendation — should we update?

See `COMPARISON.md` for the full reasoning. Headline:

1. **Adopt now (low cost, clear value):** add `version="v2"` to our `astream` call for
   forward-compat with the unified `StreamPart` API; this is the documented current form.
2. **Adopt if the FE needs it (medium cost):** a typed event layer (a small
   `app/streaming/events.py` + light mapper) *only* if the web UI is going to render tool
   calls / sub-agent activity / HITL plan approval as distinct UI affordances. Otherwise
   it's complexity our token-only stream doesn't need.
3. **Consider:** `sse-starlette` for built-in ping/keepalive and cleaner framing; a
   `done`/`error` typed terminal event instead of the `[DONE]` string sentinel.
4. **Do NOT adopt yet:** `astream_events` v3 (beta), `deepagents`, budget/compression
   telemetry, multi-graph split — these solve problems we don't have.
