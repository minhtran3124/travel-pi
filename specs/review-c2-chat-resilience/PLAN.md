---
slug: review-c2-chat-resilience
status: active
owner: Minh Tran
created: 2026-09-04
---

# Chat resilience: Stop, interrupt rehydration, and a safer claim

## 1. Motivation

`useAgentStream.ts` has no way to cancel an in-progress stream, silently gets stuck if a page
reload happens while the graph is paused at a HITL interrupt, and can permanently forfeit a user's
pre-login conversation history on a transient network error during claim. Design:
`design.md` (approved after 2 review rounds, 2026-09-04). Research: `research-brief.md` (Deep) —
confirms `interrupt_pending`/`interrupt_payload` is an existing naming convention (`ChatResponse`)
and that `Pregel.aget_state` needs only `configurable.thread_id`, read from the installed
LangGraph 1.2.6 source.

## 2. Non-goals

- GitHub issue #109 (clarification re-streams ~3×) — split to `review-c2b-fix-gh-109`; different
  subsystem (BE LangGraph `awaiting_user`/reflection path).
- Persisting side-panel artifacts across a reload — documented as a known limitation, not fixed.
- Extracting `send`/`retry`/`resume`'s shared fetch/SSE shape into one helper — a real
  simplification, but an unrelated refactor to this change.
- Any change to `GET /agent/conversations` (the list endpoint) or the response shape of
  `POST /agent/conversations/claim` itself.

## Global Constraints

- Node 24 for every FE command: `export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH"`.
- Run FE commands from `apps/web/` or through `pnpm --filter @travel/web`; run BE commands from
  `apps/api/` using `../../.venv/bin/python`.
- Stage and commit as separate commands (a PreToolUse hook blocks `git add … && git commit …`).
- Surgical changes only: no refactor of the `send`/`retry`/`resume` duplication in
  `useAgentStream.ts` beyond the one guard fix each needs (per design.md D1).
- `Message`/`Conversation`/the new `ConversationMessages` FE types are hand-mirrored from the BE
  Pydantic schemas in `apps/web/src/lib/query/agent.ts` (existing local convention — not sourced
  from the OpenAPI codegen used by `ChatRequest`/`ChatResponse` in the same file); keep that split.
- BE tests use the existing `booking_client` fixture (`tests/api/agent/test_agent_chat.py`) to
  drive a real interrupt — no new fixture.
- FE tests follow the existing per-concern file split (`useAgentStream.stream.test.tsx` already
  exists at 508 lines); new coverage goes into new sibling files, not grown into that one.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|---|---|---|---|
| SC-1 | A user-triggered stop resets `isStreaming` to false and shows no error | `export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm --filter @travel/web exec vitest run src/components/chat/useAgentStream.stop.test.tsx` | exit 0 |
| SC-2 | `GET .../messages` reports `interrupt_pending: true` with the right payload against a real pending interrupt | `../../.venv/bin/python -m pytest tests/api/agent/test_agent_history.py -k interrupt -q` (from `apps/api/`) | exit 0 |
| SC-3 | The three pre-existing list-messages assertions still pass under the new response shape | `../../.venv/bin/python -m pytest tests/api/agent/test_agent_history.py -q` (from `apps/api/`) | exit 0 |
| SC-4 | The pre-existing PII-redaction test still passes reading messages under the new shape | `../../.venv/bin/python -m pytest tests/api/agent/test_agent_chat.py -k test_chat_redacts_pii_in_persisted_messages -q` (from `apps/api/`) | exit 0 |
| SC-5 | A claim failure keeps the legacy key on non-403, clears it on 403, and hydration still runs either way | `export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm --filter @travel/web exec vitest run src/components/chat/useAgentStream.hydrate.test.tsx` | exit 0 |
| SC-6 | Hydrating with a pending interrupt sets `interrupt` state and a valid resume target, in both the prior-tokens and zero-tokens branches | `export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm --filter @travel/web exec vitest run src/components/chat/useAgentStream.hydrate.test.tsx` | exit 0 |
| SC-7 | The whole web package still type-checks | `export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm --filter @travel/web exec tsc --noEmit` | exit 0 |

## 4. Tasks

### Task 1.1 — `ConversationMessages` BE schema (wave 1)

- **Files:** apps/api/app/schemas/agent.py
- **Action:** Add a `ConversationMessages` Pydantic model: `messages: list[Message]`,
  `interrupt_pending: bool = False`, `interrupt_payload: dict | None = None` — the same two field
  names and defaults already used on `ChatResponse` (lines ~94-95), for naming consistency across
  the API surface. Place it near `Message`/`Conversation` in the file.
- **Verify:** `../../.venv/bin/python -c "from app.schemas.agent import ConversationMessages; ConversationMessages(messages=[])"` (from `apps/api/`)
- **Done:** The import succeeds and constructing with only `messages=[]` fills both interrupt
  fields with their defaults.
- **Criteria:** SC-2, SC-3
- **Interfaces:** Consumes nothing new. Produces `apps/api/app/schemas/agent.py` with `ConversationMessages`, consumed by Task 2.1.

### Task 1.2 — `errorClaimFailed` i18n key (wave 1)

- **Files:** apps/web/messages/en.json, apps/web/messages/vi.json
- **Action:** Add `errorClaimFailed` under the `Chat` namespace in both files, matching the tone
  and placement of the existing `error*` keys (`errorConnectionDropped`, `errorResumeFailed`, …).
  English: "Couldn't restore your earlier chat history. It'll try again next time you open the
  app." Vietnamese: an equivalent, non-alarming phrasing in the same register as the file's other
  Chat strings.
- **Verify:** `python3 -c "import json; a=json.load(open('apps/web/messages/en.json'))['Chat']; b=json.load(open('apps/web/messages/vi.json'))['Chat']; assert 'errorClaimFailed' in a and 'errorClaimFailed' in b"`
- **Done:** Both files parse as JSON and contain the key under `Chat`.
- **Criteria:** SC-5
- **Interfaces:** Consumes nothing. Produces `apps/web/messages/en.json` and `apps/web/messages/vi.json` with the Chat.errorClaimFailed key, consumed by Task 3.1.

### Task 1.3 — FE query-layer: `ConversationMessages` return type + `ClaimError` (wave 1)

- **Files:** apps/web/src/lib/query/agent.ts, apps/web/src/lib/query/agent.test.ts
- **Action:** Add a hand-mirrored `ConversationMessages` interface (`messages: Message[]`,
  `interrupt_pending: boolean`, `interrupt_payload: { type: string; draft: string } | null` — the
  same payload shape `InterruptState.payload` already uses in `useAgentStream.ts`), matching the
  BE schema from Task 1.1. Change `fetchConversationMessages`'s return type from `Message[]` to
  `ConversationMessages` and its `res.json()` cast to match. Add a `ClaimError` class
  (`extends Error`, carries `status: number`) and change `fetchClaim` to throw
  `new ClaimError(res.status, ...)` instead of a bare `Error` on a non-ok response. Write
  `agent.test.ts` (new file, `msw` per the existing project convention) asserting:
  `fetchConversationMessages` resolves the new object shape; `fetchClaim` throws a `ClaimError`
  whose `.status` equals the mocked response's status for both a 403 and a 500 response.
- **Verify:** `export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm --filter @travel/web exec vitest run src/lib/query/agent.test.ts`
- **Done:** The new test file passes; `fetchClaim`'s thrown error is `instanceof ClaimError` with
  a numeric `.status`.
- **Criteria:** SC-7
- **Interfaces:** Consumes the interrupt payload shape already used by `apps/web/src/components/chat/useAgentStream.ts` (read-only reference, not imported). Produces `apps/web/src/lib/query/agent.ts` with `ConversationMessages` and `ClaimError`, consumed by Task 3.1.

### Task 2.1 — BE route: async interrupt read + response shape (wave 2)

- **Files:** apps/api/app/routers/agent.py, apps/api/tests/api/agent/test_agent_history.py, apps/api/tests/api/agent/test_agent_chat.py
- **Action:** Change `list_conversation_messages` to `async def`, add `graph: GraphDep` as a
  parameter, and change `response_model` to `ConversationMessages`. After the existing ownership
  check (unchanged: absent/foreign conversation still returns the empty-shaped result, now
  `ConversationMessages(messages=[])` instead of `[]`), build `thread_id = _thread_id(uid,
  conversation.trip_id, conversation_id)` and `cfg = {"configurable": {"thread_id": thread_id}}`,
  then `state = await graph.aget_state(cfg)`. Set `interrupt_pending = bool(state.interrupts)` and
  `interrupt_payload = state.interrupts[0].value if state.interrupts else None`. Return
  `ConversationMessages(messages=repo.list_messages(conversation_id), interrupt_pending=...,
  interrupt_payload=...)`. Update the three existing assertions in `test_agent_history.py`
  (`test_list_messages_returns_ordered_messages`, `test_list_messages_unknown_conversation_returns_empty`,
  `test_list_messages_scoped_to_owner`) and the one in `test_agent_chat.py`
  (`test_chat_redacts_pii_in_persisted_messages`) to read `.json()["messages"]` instead of the bare
  list. Add one new test in `test_agent_history.py`: using `booking_client`, POST
  `/agent/chat {"message": "book me a hotel in Paris", "user_id": "u1"}` to produce a real
  interrupt, then GET the conversation's messages and assert `interrupt_pending is True` and
  `interrupt_payload` is a non-empty dict; assert a second, freshly created conversation with no
  turns reports `interrupt_pending is False` and `interrupt_payload is None`.
- **Verify:** `../../.venv/bin/python -m pytest tests/api/agent/test_agent_history.py tests/api/agent/test_agent_chat.py::test_chat_redacts_pii_in_persisted_messages -q` (from `apps/api/`) — the whole `test_agent_history.py` module (measured 9.95s) so the new interrupt test and all three pre-existing list-messages tests run without an imprecise `-k` filter accidentally over- or under-selecting.
- **Done:** All named tests pass; the route imports and runs under `async def` with no other
  behavior change (ownership check, empty-result shape for absent/foreign conversations unchanged
  apart from the object wrapper).
- **Criteria:** SC-2, SC-3, SC-4
- **Interfaces:** Consumes `apps/api/app/schemas/agent.py` (Task 1.1) and the existing thread-id/graph-dependency/repository helpers already in apps/api/app/routers/agent.py. Produces `apps/api/app/routers/agent.py` with the changed GET /agent/conversations/{id}/messages route, structurally consumed by Task 3.1's hydrate path.

### Task 3.1 — FE hook: Stop, interrupt rehydration, safer claim (wave 3)

- **Files:** apps/web/src/components/chat/useAgentStream.ts, apps/web/src/components/chat/useAgentStream.stop.test.tsx, apps/web/src/components/chat/useAgentStream.hydrate.test.tsx
- **Action:** Three changes to the hook, each independently testable:
  1. **Stop.** Add a `userStoppedRef = useRef(false)` and an exported `stop = useCallback(() => {
     userStoppedRef.current = true; abortRef.current?.abort(); }, [])`. The fetch/SSE catch-finally
     shape lives in exactly three functions: `send` (line ~365), `resume` (line ~542), and `rerun`
     (line ~654) — `retry` and `regenerate` (lines ~799, ~806) are thin wrappers that both delegate
     to `rerun` and share its bug; fixing `rerun` fixes both. In all three functions, leave each
     `catch` block's `if (controller.signal.aborted) return;` **unchanged**. In each `finally`
     block, change the guard from `if (!controller.signal.aborted) { ... }` to
     `if (!controller.signal.aborted || userStoppedRef.current) { ...; userStoppedRef.current =
     false; }` so a deliberate stop still resets `isStreaming`, stamps `elapsedMs`, and (unless
     `sawInterrupt`) calls `onTurnComplete`, while the unmount-cleanup abort
     (`userStoppedRef.current` stays `false`) still skips the block exactly as today. Export `stop`
     on the hook's return type **and add it to the hook's returned object**, not just its type.
  2. **Interrupt rehydration.** In the hydrate effect, change the
     `fetchConversationMessages(storedId, userId)` call site to destructure
     `{ messages, interrupt_pending, interrupt_payload }`. Keep the existing `setMessages(...)`
     mapping. When `interrupt_pending` is true: if the last message in `messages` has
     `role === "assistant"`, set `assistantIdRef.current` to its id; otherwise push a fresh
     `{ id: newId(), role: "assistant", content: "", activity: [], panels: [] }` onto the mapped
     array before calling `setMessages`, and point `assistantIdRef.current` at that new id. Either
     way, call `setInterrupt({ conversationId: storedId, payload: interrupt_payload! })`.
  3. **Safer claim.** The claim `try`/`catch` and the hydrate step both live inside the *same*
     top-level `void (async () => { ... })()` IIFE — a bare `return` inside the claim's `catch`
     would exit that whole IIFE and skip hydration below it, which is worse than the bug being
     fixed. Do not use `return` in the catch. Instead, move
     `localStorage.removeItem(LEGACY_ANON_STORAGE_KEY)` inside both the success path and the 403
     branch, and default to keeping the key otherwise:
     ```
     if (anonId) {
       try {
         await fetchClaim(anonId);
         localStorage.removeItem(LEGACY_ANON_STORAGE_KEY);
       } catch (err) {
         if (err instanceof ClaimError && err.status === 403) {
           localStorage.removeItem(LEGACY_ANON_STORAGE_KEY);
         } else {
           setError(t("errorClaimFailed"));
         }
       }
     }
     ```
     This keeps the key on a plain network failure too: a rejected `fetch` throws a `TypeError`, not a
     `ClaimError`, so it never matches the 403 branch. Execution then falls through to the hydrate
     step exactly as before, unconditionally.
  Write `useAgentStream.stop.test.tsx`: render the hook mid-stream (reuse the existing
  `wireStream`/SSE-mock pattern from `useAgentStream.stream.test.tsx`), call `stop()`, assert
  `isStreaming` becomes `false` and `error` stays `null`. Write
  `useAgentStream.hydrate.test.tsx` with two describe blocks: (a) interrupt rehydration — mock
  `fetchConversationMessages` to resolve `{ messages: [...], interrupt_pending: true,
  interrupt_payload: {...} }` in one case with a trailing assistant message and in another with
  only a user message, and assert `interrupt` is set and (via a subsequent `resume()` call) that
  the continuation targets the expected message id in both cases; (b) claim behavior — set
  `LEGACY_ANON_STORAGE_KEY` in `localStorage` before mount, mock `fetchClaim` to reject with a
  `ClaimError(500, ...)` in one case and `ClaimError(403, ...)` in another, and assert the key
  survives the 500 case (`localStorage.getItem(...)` still returns it) with `error` set to the
  claim-failed message, is removed in the 403 case, and — for both cases — that
  `fetchConversationMessages` still ran (hydration was not skipped).
- **Verify:** `export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm --filter @travel/web exec vitest run src/components/chat/useAgentStream.stop.test.tsx src/components/chat/useAgentStream.hydrate.test.tsx src/components/chat/useAgentStream.stream.test.tsx`
- **Done:** All three test files pass, including the pre-existing `useAgentStream.stream.test.tsx` (regression guard — its `fetchConversationMessages` mock must be updated to the new object shape or its hydrate effect will throw destructuring `undefined`), and the new claim-behavior describe block confirms hydration still runs after both a kept-key and a cleared-key claim outcome.
- **Criteria:** SC-1, SC-5, SC-6, SC-7
- **Interfaces:** Consumes `ConversationMessages` and `ClaimError` from `apps/web/src/lib/query/agent.ts` (Task 1.3) and the Chat.errorClaimFailed key from Task 1.2. Produces `apps/web/src/components/chat/useAgentStream.ts` with the hook's new `stop` export and its changed hydrate/claim behavior, consumed by Task 4.1.

### Task 4.1 — Wire Stop into the composer (wave 4)

- **Files:** apps/web/src/components/chat/ChatComposer.tsx, apps/web/src/components/chat/ChatComposer.test.tsx, apps/web/src/components/chat/ChatPanel.tsx
- **Action:** Add `isStreaming: boolean` and `onStop: () => void` to `ChatComposerProps`. While
  `isStreaming` is true, the existing send button (the `type="submit"` button with the arrow SVG)
  swaps to `type="button"`, `aria-label={t("stopMessage")}`, `onClick={onStop}`, `disabled={false}`
  (it must stay clickable even though `disabled` — the composer's existing `disabled` prop, driven
  by `inputBlocked` — would otherwise grey it out), and a stop-square SVG (`<rect x="6" y="6"
  width="12" height="12" rx="1.5" />` in the same `viewBox="0 0 24 24"` stroke style as the
  existing send icon) in place of the arrow path. Add `stopMessage` to `Chat` in both message
  files, matching Task 1.2's convention. In `ChatPanel.tsx`, pass `isStreaming={isStreaming}` and
  `onStop={stop}` (destructure `stop` from the `useAgentStream()` return alongside the existing
  fields) to the one `<ChatComposer>` call site (the `ChatEmptyState` branch has no composer and
  is unaffected). Extend `ChatComposer.test.tsx` with a case asserting the button's
  `aria-label`/click behavior swaps when `isStreaming` is true.
- **Verify:** `export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm --filter @travel/web exec vitest run src/components/chat/ChatComposer.test.tsx src/components/chat/ChatPanel.test.tsx`
- **Done:** Both test files pass, including the new Stop-button case.
- **Criteria:** SC-7
- **Interfaces:** Consumes the `stop` export from `apps/web/src/components/chat/useAgentStream.ts` (Task 3.1). Produces `apps/web/src/components/chat/ChatComposer.tsx` with the Stop affordance, wired by `apps/web/src/components/chat/ChatPanel.tsx`.

## 5. Risks

- **`trip_id` divergence between the write and read paths.** The interrupt read (Task 2.1) derives
  `thread_id` from `conversation.trip_id` — set once at conversation creation and never updated
  (`ConversationRepository.ensure_conversation` only writes `trip_id` on insert). The write path
  (an active turn) derives `thread_id` from the request's live `body.trip_id`. If a client ever
  sends a different `trip_id` on a later turn than the one that created the conversation — against
  the documented client contract (`ChatResponse.trip_id`'s docstring already tells clients to keep
  sending the conversation's original `trip_id`, including `null`) — the interrupt-producing turn
  and the read both key on different LangGraph threads: the read silently reports
  `interrupt_pending: false` for a real pending interrupt, no error. Confirmed real by the task 2.1
  review; not fixed here because a proper fix (accepting a live `trip_id` on the read endpoint, or
  persisting `trip_id` updates on every turn) is a public-contract or data-model change beyond
  design.md's scope. The one condition already required by the FE contract — a conversation's
  `trip_id` never changes turn to turn — keeps this from firing in the intended client flow.

- **No live FE↔BE integration test in this plan.** Tasks 2.1 and 3.1 are each verified against
  their own layer (BE pytest, FE vitest with mocks) but nothing in this plan exercises the real
  `GET .../messages` response against the real hook. The design's own "Tests / verification"
  section names this as a manual step (local reload against a real interrupt); it is not
  mechanized here because it needs a live backend + a real HITL flow, which exceeds a task
  `Verify`'s automation and time bounds. Do this manually before shipping, or add it as a follow-up
  spec if it needs to be a repeatable check.
- **`response_model` change is a real breaking shape change**, not additive (per design.md D2,
  itself a correction of an earlier "additive" framing). Blast radius is fully enumerated (one FE
  call site, four BE test assertions) and all four are fixed in Task 2.1 — but any *other*,
  undiscovered consumer of this specific endpoint would break silently. `grep -rn
  "conversations/.*messages"` across `apps/web/src` before merging is cheap insurance.
- **Degraded checkpointer.** If the dev Postgres checkpointer is down and LangGraph falls back to
  an in-process `MemorySaver` (`docs/solutions/agent/local-postgres-checkpointer.md`), an interrupt
  from before a server restart is invisible to Task 2.1's read — pre-existing limitation of the
  whole HITL mechanism, not introduced by this change.
- **`InterruptPrompt`'s `draft` field assumes `payload.type`/`payload.draft`** stays shaped that
  way. Task 3.1's rehydration path passes through whatever `interrupt_payload` the BE returns
  without reshaping it — if a future BE change alters the interrupt value's shape, both the live
  and rehydrated paths break identically (no new coupling introduced).

## 6. Status Log

| Date | Event |
|---|---|
| 2026-09-04 | Tasks 1.1-4.1 complete across 4 waves; commits 2b4c482..a72c01f. |
| 2026-09-04 | Correctness review (6 angles, 2 rounds): 2 findings fixed (GraphOptionalDep for graph-availability coupling, revealRef.flush on stop). Commits d8ea6c7, c920133. |
| 2026-09-04 | Intent review: approved with 4 non-blocking findings (2 disclosed drift, 1 stale-codegen gap, 1 trivial formatter churn). Review chain complete. |
| 2026-09-04 | Intake (parent `review-c-web-experience`, E001-A slice 2 of 4). Brainstormed; #109 split to `review-c2b-fix-gh-109`. Design approved after 2 review rounds. Deep research brief resolved D3's cfg question from installed LangGraph source. Plan drafted. |
