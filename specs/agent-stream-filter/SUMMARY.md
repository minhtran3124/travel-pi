# agent-stream-filter — Summary

Lane: normal
Confidence: high
Reason: Filters /agent/stream to emit only the user-facing sub-agent answer + a unique thread per anonymous stream (REVIEW.md C4); changes client-visible streaming behavior (existing endpoint) but no skill-listed hard gate fires.
Flags: existing-behavior, public-contract
Affects: app/routers/agent.py (/agent/stream SSE client-visible behavior)
Input-type: change request

> `Lane` drives ceremony; `Confidence` drives interruption. No hard gate; the fix is unambiguous
> (filter by node, verified empirically) — PROCEED. Independent of C2/C3; only touches agent.py
> (last changed by C1, already on feat/travel-agent-foundation), so branched off the feature branch.

### Intent

> continue with C4

Context: **C4** in `specs/travel-agent/REVIEW.md` — "`/agent/stream` leaks internal node output
(router/summarizer/reflection) to the user". `agent_stream` streams `stream_mode="messages"` and
yields `chunk.content` for **every** model call, discarding metadata — so the summarizer text and
the reflection critic's `OK`/`REVISE` verdict interleave with the answer. Also: anonymous streams
collapse onto `conv_stream`, colliding all unnamed sessions on one `thread_id`.

## What changed

`app/routers/agent.py` `agent_stream`: the SSE generator now emits a chunk only when
`metadata["langgraph_node"]` is one of the `SUBAGENTS` (planner/concierge/journal/booking/budget) —
suppressing the supervisor, summarizer, and reflection nodes that messages-mode would otherwise
leak. Empirically confirmed the answer streams under the sub-agent node name (e.g. `concierge`)
while the reflection verdict streams under `reflection`. Anonymous streams (no `conversation_id`)
now get a unique `thread_id` (`stream-<uuid>`) instead of a shared `stream` thread.

### Rationale

Minimal, correct fix at the SSE seam — filter by node rather than reshape the graph. Matches the
LangGraph streaming guidance (filter `(chunk, metadata)` on `langgraph_node`).

### Alternatives considered

- Tag the user-facing models and filter by `tags` — equivalent; node-name filter is simpler and
  needs no change to the sub-agent builders.
- Full conversation persistence for `/stream` (like `/chat`) — out of scope; unique thread id is
  the minimal collision fix.

### Deviations

- Rule 1 — Strengthened `tests/api/agent/test_agent_chat.py::test_stream_emits_sse_events` to assert
  the answer streams and the reflection verdict (`OK`) does NOT. In-scope (regression guard for C4).

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Lint (app) | `ruff check app` | 0 | clean |
| Full suite (SQLite) | `.venv/bin/pytest -q` | 0 | 848 passed |
| Stream guard | `.venv/bin/pytest tests/api/agent -q` | 0 | answer present, "OK" verdict suppressed |

### Rollback

- `git revert <sha>` (reversible — SSE filter + thread-id; no schema/contract shape change)

### Harness-Delta

- none
