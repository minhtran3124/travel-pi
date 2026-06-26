---
slug: agent-stream-filter
status: shipped
owner: Minh Tran
created: 2026-06-26
---

# Filter /agent/stream to the user-facing answer (REVIEW.md C4)

## 1. Motivation

`specs/travel-agent/REVIEW.md` **C4**: `/agent/stream` uses `stream_mode="messages"` and yields
`chunk.content` for every model call, discarding metadata — so the summarizer text and the
reflection critic's `OK`/`REVISE` verdict leak into the SSE feed. Anonymous streams also share one
`thread_id` (`…_conv_stream`), colliding unnamed sessions.

## 2. Non-goals

- Full conversation persistence for `/stream` (mirroring `/chat`) — only the thread collision is fixed.
- Reworking the graph or sub-agent builders — the fix lives at the SSE seam.

## 3. Success criteria

- The SSE feed contains only the active sub-agent's answer; supervisor/summarizer/reflection output
  is suppressed.
- Anonymous streams get a unique `thread_id`.
- A test asserts the answer streams and the reflection verdict does not; suites green.

## 4. Tasks (one wave)

### Task 1.1 — Filter the stream by node + unique anonymous thread

```xml
<task id="1.1">
  <files>app/routers/agent.py</files>
  <action>In agent_stream, keep `(chunk, meta)` and emit only when meta["langgraph_node"] in SUBAGENTS (suppress supervisor/summarize/reflection). Give anonymous streams a unique thread (`stream-<uuid>`) instead of the shared "stream" id.</action>
  <verify>.venv/bin/pytest tests/api/agent -q</verify>
  <done>Answer streams; internal-node output suppressed; no shared anonymous thread.</done>
</task>
```

### Task 1.2 — Regression guard

```xml
<task id="1.2">
  <files>tests/api/agent/test_agent_chat.py</files>
  <action>Strengthen test_stream_emits_sse_events: assert the concierge answer is present and the reflection critic's "OK" verdict is absent from the SSE text.</action>
  <verify>.venv/bin/pytest tests/api/agent/test_agent_chat.py -q</verify>
  <done>Test fails before the filter, passes after.</done>
</task>
```

## 5. Risks

- Node-name filter could over-suppress if a sub-agent were renamed — mitigated: `SUBAGENTS` is the
  single source of truth for both routing and the filter. Empirically verified node names
  (`concierge` for the answer, `reflection` for the leak) before implementing.

## 6. Status Log

- 2026-06-26 — implemented + verified. ruff clean; `pytest -q` 848 passed (SQLite); stream guard
  asserts the leak is closed. Branch `fix/agent-stream-filter` off `feat/travel-agent-foundation`
  (independent PR; only touches agent.py).
