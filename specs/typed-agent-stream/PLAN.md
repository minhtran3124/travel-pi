---
slug: typed-agent-stream
status: active
owner: Minh Tran
created: 2026-06-27
---

# Typed agent SSE event protocol

## 1. Motivation

The FE will render structured agent activity (tool calls, sub-agent handoffs, HITL
plan-approval cards) in addition to the streamed answer. The current `/agent/stream`
emits only raw `data:<text>` token frames + `reset`/`interrupt` named events + a
`[DONE]` string sentinel — insufficient to drive that UI. Adopt a **fully-typed SSE
protocol** (clean break) where every emission is a named JSON event, informed by the
`chat-agents` review (`specs/streaming-research/`), right-sized to our trip planner.

## 2. Non-goals

- No `astream_events` v3 (beta).
- No `version="v2"` on `astream`: in langgraph 1.2.6 it changes messages-mode emission
  shape and would destabilize the working token stream for no current gain. Stay on v1
  `(namespace, mode, data)` tuples.
- No budget/compression/memory-pressure telemetry, no `deepagents`, no `extract.py`
  final-report guard (chat-shaped replies are legitimately short).
- No transport swap — keep the hand-rolled `sse_response`.

## 3. Success criteria

- `/agent/stream` emits typed events: `start`, `token`, `reset`, `subagent`,
  `tool_call`, `tool_result`, `interrupt`, `done`, `error` (JSON `data`).
- Token text streams as `event: token` / `data: {"content": "..."}` (JSON escapes
  newlines — the per-line markdown split is no longer needed for tokens).
- `[DONE]` string sentinel removed; replaced by `event: done`.
- Tool calls and sub-agent handoffs surface from `stream_mode=["messages","updates"]`.
- HITL interrupt still emits `event: interrupt` before `done`.
- Full BE suite green.

## 4. Tasks

### Task 1.1 — Event taxonomy + mapper package

```xml
<task id="1.1" wave="1">
  <files>apps/api/app/streaming/__init__.py, apps/api/app/streaming/events.py, apps/api/app/streaming/mapper.py</files>
  <action>Create app/streaming/ package. events.py: factory funcs (start, token, reset, subagent, tool_call, tool_result, interrupt, done, error) each returning core.streaming.TypedSSEEvent with json.dumps payloads (compact separators); truncate args_preview to 200 chars. mapper.py: async generator stream_agent_events(graph, stream_input, cfg, conversation_id) consuming graph.astream(stream_mode=["messages","updates"], subgraphs=True) as (ns, mode, data) tuples. Track current_subagent (emit subagent on root change, root=ns[0].split(":",1)[0] in SUBAGENTS), last_msg_id (emit reset), emitted tool_call ids. messages mode: AIMessage chunks with content -> token; skip non-subagent ns and non-AIMessage. updates mode: AIMessage.tool_calls -> tool_call (dedup by id); ToolMessage -> tool_result (status from msg.status). Post-loop: aget_state -> interrupt event if pending, then done. Wrap in try/except: CancelledError -> error(code=cancelled)+re-raise; else error(code=internal).</action>
  <verify>cd apps/api && ../../.venv/bin/python -c "from app.streaming import events, mapper"</verify>
  <done>Package imports; events return TypedSSEEvent; mapper is an async generator.</done>
</task>
```

### Task 1.2 — Transport: drop `[DONE]` terminal

```xml
<task id="1.2" wave="1">
  <files>apps/api/app/core/streaming.py</files>
  <action>Remove the automatic `data: [DONE]\n\n` terminal from sse_response.event_stream (the mapper now emits a typed `done` event). Keep TypedSSEEvent and the str-multiline path intact. Update module docstring wire-contract section.</action>
  <verify>cd apps/api && ../../.venv/bin/python -c "import app.core.streaming"</verify>
  <done>sse_response no longer appends [DONE].</done>
</task>
```

### Task 2.1 — Wire router to mapper

```xml
<task id="2.1" wave="2">
  <files>apps/api/app/routers/agent.py</files>
  <action>Replace the inline tokens() generator in agent_stream with sse_response(stream_agent_events(graph, stream_input, conversation_id=conversation_id, cfg=cfg)). Keep conversation_id derivation and stream_input (resume vs fresh) logic. Remove now-unused inline imports (json, AIMessage if unused, SUBAGENTS moves into mapper).</action>
  <verify>cd apps/api && ../../.venv/bin/python -c "import app.routers.agent"</verify>
  <done>Router delegates to mapper; no inline stream parsing remains.</done>
</task>
```

### Task 2.2 — Tests

```xml
<task id="2.2" wave="2">
  <files>apps/api/tests/api/agent/test_streaming_sse.py, apps/api/tests/api/agent/test_stream_events.py</files>
  <action>Update test_streaming_sse.py: drop [DONE] expectations (plain chunk -> "data: hello\n\n"; remove reconstructed[-1]=="[DONE]" assertion). Add test_stream_events.py: unit-test event factories (shape of token/tool_call/done JSON) and mapper against a fake astream yielding scripted (ns, mode, data) tuples — assert ordered emission of subagent/token/tool_call/tool_result/done and tool dedup.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_streaming_sse.py tests/api/agent/test_stream_events.py -q</verify>
  <done>Both files green.</done>
</task>
```

### Task 3.1 — FE: align with the typed protocol

```xml
<task id="3.1" wave="3">
  <files>apps/web/src/lib/stream/parseSSE.ts, apps/web/src/lib/stream/parseSSE.test.ts, apps/web/src/components/chat/useAgentStream.ts, apps/web/src/components/chat/AgentActivity.tsx, apps/web/src/components/chat/MessageList.tsx, apps/web/src/components/chat/ChatPanel.tsx, apps/web/src/app/globals.css, apps/web/messages/en.json, apps/web/messages/vi.json</files>
  <action>Rewrite parseSSE for the typed protocol (start/token/reset/subagent/tool_call/tool_result/interrupt/done/error; token from {content}; drop [DONE]; skip unknown/malformed). useAgentStream: handle all events, expose `activity` (active subagent + tool list), pin conversation id from `start`, treat in-band `error` via the existing fallback guard; tool_call counts as "received" (server-side mutation). New AgentActivity strip rendered in the streaming bubble via MessageList; ChatPanel passes activity through. Add tp-spin keyframe + activityAria i18n (en/vi).</action>
  <verify>cd apps/web && npx tsc --noEmit && npx vitest run src/lib/stream/parseSSE.test.ts</verify>
  <done>tsc clean; parseSSE tests green; full FE suite green.</done>
</task>
```

## 5. Risks

- **Public-contract change** (hard gate) — authorized by user (FE will adopt new parser).
  Rollback: `git revert <sha>`.
- `updates`-mode message wrapping (Overwrite/Add reducers) — handle list/single coercion.
- Partial tool_calls on streaming chunks — only read tool_calls from `updates` (complete),
  never from `messages` chunks.

## 6. Status Log
- 2026-06-27: plan authored; design confirmed (fully-typed clean break, hand-rolled transport).
- 2026-06-27: FE aligned (Task 3.1). `parseSSE.ts` rewritten for the typed protocol;
  `useAgentStream` handles all events + exposes `activity`; new `AgentActivity` strip in
  the streaming bubble; `tp-spin` CSS + `activityAria` i18n (en/vi). Verify: tsc clean,
  eslint clean, FE vitest 47 passed (parseSSE 17). No e2e SSE mocks existed to update.
- 2026-06-27: implemented. New `app/streaming/{events,mapper}.py`; `core/streaming.py`
  drops `[DONE]`; `routers/agent.py` delegates to `stream_agent_events`. Tests:
  `test_stream_events.py` (new), `test_streaming_sse.py` updated. **Scope addition**
  (auto-correct Rule 1): `tests/api/agent/test_agent_chat.py` 4 integration tests updated
  (`[DONE]` → `event: done`) — broken by the intended contract change. Verify: agent suite
  21 passed; full suite 874 passed (17 pre-existing `.env` OPENAI_API_KEY failures, confirmed
  env-only by re-run with `.env` aside → 18 passed). ruff clean. Rollback: `git revert <sha>`.
