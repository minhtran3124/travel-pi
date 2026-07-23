# fix-trip-id-persist-across-turns — Summary

Lane: high-risk
Confidence: high
Reason: Bug fix with a fully verified root cause (empirically reproduced via direct LangGraph state-merge testing) and a narrow, additive fix. Touches a public response contract (`ChatResponse.trip_id`, `done` SSE event field) — additive-only, non-breaking. Lane bumped to high-risk solely to satisfy `hooks/risk-corroboration.sh`'s `auth` hard-gate, which its own `\bsession\b` keyword match trips on the two new `session.commit()` calls added to `agent_chat` (the sync handler's pre-existing `session: SessionDep` DB-session parameter, matching the same pattern already present in the neighboring `/agent/stream` handler) — a DB session, not an authentication session. No login/JWT/password/cookie/oauth code is touched anywhere in this diff; narrowing this explicitly per `rules/orchestration.md`'s escalation guidance rather than fighting or bypassing the gate.
Flags: public-contract (additive field only), auth (false positive — see Reason)
Affects: apps/api/app/routers/agent.py, app/schemas/agent.py, app/streaming/events.py, app/streaming/mapper.py, app/tools/_base.py (unrelated debug-print cleanup only, no behavior change)
Input-type: bug fix (found via ce-code-review of PR #94, confirmed by an external Codex review comment on the same PR)

### Intent

A GitHub Codex review comment on PR #94 (feat/agent-trip-context) flagged: "When a chat starts outside an existing trip page, the web client sends `trip_id: null` on every normal follow-up... this update only stores the new ID in the current graph state... so the next turn overwrites the checkpoint's active `trip_id` with `None`." User asked for a new PR to fix this issue.

### What changed

**Root cause (verified directly, not just from the review comment):** `/agent/chat` and `/agent/stream` both passed `"trip_id": body.trip_id` unconditionally into `graph.ainvoke`/`astream` input on every turn. `TravelAgentState.trip_id` has no reducer, so LangGraph's per-channel state merge treats an explicit `None` in the invocation input as an overwrite — confirmed empirically (`langgraph.prebuilt.tool_node.ToolNode._func` / a direct `MemorySaver` repro script) that omitting a channel key from the input leaves the checkpointed value untouched, while passing `None` explicitly clobbers it. Since the web client (`useAgentStream.ts`) has no way to learn a `trip_id` the `create_trip` tool set mid-conversation, it keeps sending `trip_id: null`, silently discarding the trip on the very next turn.

**Fix:**
1. New `_turn_input()` helper in `app/routers/agent.py` builds the graph-invocation input, including the `trip_id` key **only when the client supplied one** — letting a `create_trip`-set checkpoint value survive turns where the client doesn't know about it. Used by both `/agent/chat` and `/agent/stream`.
2. `ChatResponse.trip_id` (new, additive field) and the `done` SSE event's `trip_id` field (new) surface the post-turn active trip back to the client, so it can eventually persist it client-side too (defense in depth / future UX).
3. **Separate bug found while writing the regression test:** the sync `/agent/chat` handler's request-scoped DB session held an open (uncommitted) SQLite transaction while `create_trip`'s own `session_scope()` tried to write to the same file, raising `sqlite3.OperationalError: database is locked` — silently converted to a generic "temporarily unavailable" tool error by the existing fault-tolerance `graceful_fallback` handler. Fixed by adding `session.commit()` before each `graph.ainvoke()` call in `agent_chat`, mirroring the pattern the streaming handler already used for exactly this reason. Harmless on Postgres.

### Rationale

Omitting the key (rather than passing an explicit default) is the minimal fix that lets LangGraph's own per-channel merge semantics do the work — no new state-reset logic, no client changes required for correctness (the client-side `ChatResponse.trip_id`/`done.trip_id` surfacing is additive UX, not required for the persistence fix itself). Verified this exact mechanism directly before implementing (see Verify table) rather than assuming from the review comment's description.

### Alternatives considered

- Update `Conversation.trip_id` on every turn (DB-level bookkeeping) instead of/alongside the checkpoint fix — deferred; out of scope for this fix (a separate, secondary staleness of `Conversation.trip_id` after conversation creation was noticed but not touched, since it's used for conversation-list grouping, not agent working memory, and isn't part of the reported bug).
- Have the client always resend the last-known `trip_id` — rejected because the actual web client has no path today to learn a create_trip-created id at all (that's the bug); the server-side fix is required regardless, and doesn't depend on any client change.

### Deviations

- Rule 1 — Fixed the SQLite "database is locked" bug in `agent_chat` (missing `session.commit()` before `graph.ainvoke`) discovered while writing the regression test — an obvious pre-existing bug blocking the test from passing, not part of the originally-scoped fix but required to prove it. `app/routers/agent.py`.
- Rule 1 — Updated 2 exact-shape tests (`test_done_factory_shape`, `test_done_factory_empty_suggestions` in `tests/api/agent/test_stream_events.py`) that assert `_payload(ev) == {...}` on the `done` event — a known repo hazard (docs/solutions: adding a field to a shared SSE event factory breaks cross-directory exact-shape tests) — updated in the same commit per that pattern.

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| LangGraph merge-semantics repro (omit vs explicit None) | ad hoc `MemorySaver` script | 0 | Confirmed: omitted key -> checkpoint value persists; explicit `None` -> overwritten |
| New regression test (2-turn HTTP flow) | `pytest tests/api/agent/test_agent_chat.py -k trip_id_persists -q` | 0 | 1 passed; reproduces the exact bug end-to-end via `/agent/chat` |
| Affected suites | `pytest tests/api/agent/ tests/streaming/ tests/agents/test_state.py tests/agents/test_retry.py tests/tools/test_trip_tools.py tests/tools/test_tool_registry.py tests/mcp/test_mcp_server.py -q` | 0 | 208 passed |
| Full suite (SQLite) | `DATABASE_URL=sqlite:///:memory: pytest -q` | 1* | 1695 passed; *6 pre-existing failures unrelated to this diff (env-key leak into config/embeddings/routing tests + the documented `test_flight_tools_dates` tz-skew flake) |
| Lint / format | `ruff check` + `ruff format --check` on all touched files | 0 | Clean |

### Rollback

- `git revert <sha>` — additive-only schema/event field + a router-internal helper + one added `session.commit()`; no DB migration, no removed functionality.

### Harness-Delta

- none
