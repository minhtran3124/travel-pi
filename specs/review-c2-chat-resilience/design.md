# review-c2-chat-resilience — Design

Status: approved by the user in-session (2026-09-04). Parent: `specs/review-c-web-experience/`
(E001-A slice 2 of 4; #109 split out to `review-c2b-fix-gh-109` during this brainstorming — see
Decisions §D0). Source: Travel-Pi Deep Review §3.C item 11.

## Agreed purpose, constraints, approach

Close three gaps in `useAgentStream.ts`'s resilience: no way to stop an in-progress stream, a
pending HITL interrupt that is lost on reload, and a failed history-claim that can silently and
**permanently** forfeit a user's pre-login conversations. Side-panel persistence across a reload
is **explicitly out of scope** — documented as a known limitation, not fixed, per the user's
decision below. No new dependency; two files gain a data-model-adjacent BE change (a response
shape change, not a schema/migration).

## Problem

- `useAgentStream.ts:192` holds an `abortRef`, but nothing in the UI ever calls `.abort()` —
  `ChatComposer.tsx` and `ChatPanel.tsx` have no Stop affordance, confirmed by grep.
- The pending-interrupt snapshot exists only in React state (`useState<InterruptState | null>` at
  line 182). A reload restores `messages` via `fetchConversationMessages` but never checks whether
  the graph checkpoint is still paused at an `interrupt()` call, so the user has no way to resume
  it — they can only start a new turn, which is not what the graph's checkpoint is waiting for.
- The legacy-claim step (lines ~216–226) wraps `fetchClaim` in `try { } catch { }` and unconditionally
  clears `LEGACY_ANON_STORAGE_KEY` afterward, regardless of outcome. A **transient** failure (network
  blip, 5xx) is indistinguishable from a genuine 403 (the id belongs to a registered account) — both
  permanently forfeit the claim, since the key is gone on the next load.

## Decisions (WHAT)

| # | Decision | Consequence |
|---|---|---|
| D0 | GitHub issue #109 (clarification re-streams ~3×) is **out of scope**, split to `review-c2b-fix-gh-109`. It reproduces in the BE LangGraph `awaiting_user`/reflection path — a different subsystem, root cause, and debugging method than the three items below. | Recorded in both specs' SUMMARY.md. |
| D1 | **Stop**: the hook exposes `stop(): void`. It sets a new `userStoppedRef` before calling `abortRef.current?.abort()`. The `catch` block's `if (controller.signal.aborted) return;` in `send`/`retry`/`resume` is **unchanged** — it correctly short-circuits before `setError` regardless of why the signal aborted, so a deliberate stop never shows an error. Only the sibling `finally` block's guard changes, from `if (!controller.signal.aborted) { ...reset... }` to `if (!controller.signal.aborted \|\| userStoppedRef.current) { ...reset... }`, so a deliberate stop still resets `isStreaming`, stamps `elapsedMs`, and (unless an interrupt already fired) calls `onTurnComplete` — the unmount-cleanup abort (`userStoppedRef.current` stays `false`) still skips that block exactly as today. `userStoppedRef` resets to `false` at the end of the reset block so a later unmount-abort is unaffected. | Fixes a real pre-existing bug: today, aborting for **any** reason leaves `isStreaming` stuck `true` forever, because the whole `finally` state-reset block is skipped whenever `controller.signal.aborted` is true — including the deliberate case a Stop button would trigger. The `catch` block needs no change; only the `finally` block's guard does. The fix touches all three functions identically (`send`, `retry`, `resume` each duplicate this ~90-line shape); no shared-helper extraction — out of scope, would be an unrelated refactor. |
| D2 | **Interrupt rehydration — response shape.** `GET /agent/conversations/{id}/messages` changes its `response_model` from a bare `list[Message]` to a new `ConversationMessages` object: `{messages: list[Message], interrupt_pending: bool, interrupt_payload: dict \| None}`. A conversation that doesn't exist or isn't owned by the caller returns `{messages: [], interrupt_pending: false, interrupt_payload: null}` — same 200-with-empty semantics as today, reshaped. | This is a **breaking response-shape change** (array → object), not additive — corrected from the design's first pass, which mis-described folding a field into an array response as additive. Blast radius is the FE call site (`fetchConversationMessages`) **and four existing BE assertions** that index/compare the response as a bare list: `test_list_messages_returns_ordered_messages`, `test_list_messages_unknown_conversation_returns_empty`, `test_list_messages_scoped_to_owner` (all in `tests/api/agent/test_agent_history.py`), and the PII-redaction test in `tests/api/agent/test_agent_chat.py` that iterates `history.json()` directly. All four are updated to read `.json()["messages"]` in the same change. Recorded as a deviation from E002-A's "additive" framing in SUMMARY.md. |
| D3 | **Interrupt rehydration — BE read.** `list_conversation_messages` becomes `async def` and gains `graph: GraphDep` (the same injection pattern the streaming routes already use in this file). It builds `thread_id` via the existing `_thread_id(conversation.user_id, conversation.trip_id, conversation_id)` helper and a minimal `cfg = {"configurable": {"thread_id": thread_id}}` (no `run_id`/`metrics` — this is a pure read, not a run), then `state = await graph.aget_state(cfg)`; `interrupt_pending = bool(state.interrupts)`, `interrupt_payload = state.interrupts[0].value if state.interrupts else None`. `stream_agent_events` reads interrupts the same way (`mapper.py:283-293`) but always with the full per-run `cfg` (run_id/callbacks/metadata) already in scope — there is no existing precedent in this codebase for calling `aget_state` with a bare thread-only cfg. Checkpoint reads should not need callbacks/metadata, but xia2 confirms this against the pinned LangGraph version before the plan is written. | Ownership check unchanged (conversation must belong to the JWT subject, else empty/absent as today). No new BE dependency; one route signature changes shape (sync → async, one new param). |
| D4 | **Interrupt rehydration — FE apply.** On hydrate, after `fetchConversationMessages` resolves, if `interrupt_pending`: call `setInterrupt({conversationId: storedId, payload: interrupt_payload})`, and set `assistantIdRef.current` to the id of the **last hydrated message if its role is `assistant`**; otherwise (the agent interrupted before emitting any token, so `persist_assistant_turn` wrote nothing) push a fresh empty assistant placeholder message and point `assistantIdRef.current` at its id. Either way `resume()` then has a bubble to append continuation tokens into, exactly matching the live-session shape. | Verified both branches are real and exhaustive: `persist_assistant_turn` (`apps/api/app/streaming/persistence.py:60-61`) skips the DB write when the accumulated token text is empty, so an interrupt that fires with zero preceding tokens leaves no assistant row. The user's turn is always persisted **before** the stream starts for a fresh turn (`agent.py:555-557`), and a resume never re-adds a user row, so the last hydrated message is deterministically either that user row (zero-token branch) or the interrupt-turn's own assistant row (prior-tokens branch) — never a stale assistant row from an unrelated earlier turn. |
| D5 | **Claim-403 — don't forfeit on a retryable failure.** `fetchClaim` (in `apps/web/src/lib/query/agent.ts`) is changed to throw a typed `ClaimError` carrying the response `status` instead of a bare `Error`. The hook's claim step clears `LEGACY_ANON_STORAGE_KEY` **only** when `status === 403` (a real conflict — the id belongs to a registered account, nothing to retry) or on success. On any other failure (network, timeout, 5xx) the key is **kept** so a later reload retries, and `setError(t("errorClaimFailed"))` surfaces it through the existing error banner (`ChatPanel.tsx:184-189`) — the same mechanism already used for stream failures, no new UI. | Fixes the real defect: today the key is deleted "regardless of outcome," so one transient network error permanently loses the ability to ever claim that history. A genuine 403 still clears (there is nothing to retry). |
| D6 | **Side-panel persistence — explicitly out of scope**, by the user's decision. Closing/reopening the chat does **not** lose panels today (`ChatWidget` mounts `useAgentStream` unconditionally, independent of its `open` boolean — verified). A full page **reload** does lose them, because panel payloads are never persisted (`grep -rn panel apps/api/app/db/models apps/api/app/schemas/agent.py` — no match). This design fixes neither; it documents the boundary. | No schema change. Recorded in SUMMARY.md so it is not mistaken for an unaddressed bug later. |

## Out of scope (non-goals)

- GitHub issue #109 (D0 — separate spec).
- Persisting side-panel artifacts to the DB (D6).
- Extracting the `send`/`retry`/`resume` shared fetch/SSE shape into one helper — a real
  simplification opportunity, but an unrelated refactor to this change.
- Any change to `/agent/conversations` (the list endpoint) or `/agent/conversations/claim`'s own
  response shape — only its call-site consumer (D5) changes.

## Components and data flow (HOW)

```
Reload
  └─ useAgentStream mount
       ├─ claim (D5): fetchClaim → 403 clears key; other failure keeps key + setError
       └─ hydrate: fetchConversationMessages(id)
              → { messages, interrupt_pending, interrupt_payload }   (D2/D3, BE: graph.aget_state)
              ├─ setMessages(messages)
              └─ if interrupt_pending:
                    setInterrupt({ conversationId, payload })         (D4)
                    assistantIdRef.current = lastAssistantId | newPlaceholderId
                    → InterruptPrompt renders, resume() has a target bubble

Streaming (send/retry/resume)
  └─ ChatComposer send-button → Stop icon while isStreaming
       └─ onStop → stream.stop() → userStoppedRef=true → abortRef.current.abort()  (D1)
              → catch/finally in the active function resets isStreaming, stamps elapsedMs
```

Units:

- `apps/web/src/components/chat/useAgentStream.ts` — `stop()` export; `userStoppedRef`; guard
  change in `send`/`retry`/`resume`; hydrate-effect interrupt handling (D4); claim-step status
  branching (D5).
- `apps/web/src/lib/query/agent.ts` — `fetchConversationMessages` return type changes to
  `ConversationMessages`; `fetchClaim` throws `ClaimError { status }`.
- `apps/web/src/components/chat/ChatComposer.tsx` — accepts `isStreaming`/`onStop`; send button
  swaps icon + click handler while streaming.
- `apps/web/src/components/chat/ChatPanel.tsx` — passes `stream.stop` through to the composer.
- `apps/web/messages/{en,vi}.json` — one new key, `errorClaimFailed` (Chat namespace, matching the
  existing `error*` keys' tone).
- `apps/api/app/routers/agent.py` — `list_conversation_messages` reads interrupt state (D3);
  `response_model` changes.
- `apps/api/app/schemas/agent.py` — new `ConversationMessages` schema (D2).

## Error behavior

| Situation | Behavior |
|---|---|
| User taps Stop mid-stream | Fetch aborted; partial tokens already rendered stay; `isStreaming` → false; no error shown; `onTurnComplete` fires unless an interrupt had already landed in the same tick. |
| Stop tapped with nothing streaming | No-op (`abortRef.current` is `null`). |
| Reload with a pending interrupt, prior tokens existed | Last assistant message becomes the resume target; `InterruptPrompt` renders with the rehydrated payload. |
| Reload with a pending interrupt, zero prior tokens | A fresh empty assistant placeholder is created client-side as the resume target. |
| Reload with no pending interrupt | `interrupt_pending: false`; unchanged from today. |
| Claim fails with 403 | Key cleared (unchanged); no error shown — this is not the user's history. |
| Claim fails with network/5xx/timeout | Key **kept**; `error` banner shows `errorClaimFailed`; next reload retries. |
| `GET .../messages` for a conversation with no interrupt | `interrupt_pending: false`, `interrupt_payload: null` — same call, same latency class as today (one extra `aget_state` await, already paid per-turn by the streaming path). |

## Tests / verification

- BE: update the four existing assertions D2 names (`tests/api/agent/test_agent_history.py`'s
  three list-messages tests, `tests/api/agent/test_agent_chat.py`'s PII-redaction test) to read
  `.json()["messages"]` instead of the bare list. Add a router/integration test that pauses a
  conversation at an interrupt (existing HITL test fixtures, if any — xia2 to confirm), then
  asserts `GET .../messages` reports `interrupt_pending: true` with the right payload; a second
  conversation with no interrupt asserts `false`/`null`.
- FE: a `useAgentStream` test exercising `stop()` mid-stream and asserting `isStreaming` becomes
  `false` (the specific regression this design fixes); a hydrate test asserting the interrupt
  prompt renders after a mocked `interrupt_pending: true` response, in both the
  prior-tokens-existed and zero-prior-tokens branches; a claim test asserting the key survives a
  non-403 failure and is cleared on 403.
- Manual: local reload against a real interrupt (book/cancel flow) to confirm `resume()` completes
  into the correct bubble.
