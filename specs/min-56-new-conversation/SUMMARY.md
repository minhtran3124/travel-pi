# min-56-new-conversation — Summary

Lane: normal
Confidence: high
Reason: FE-only additive UI — wires the already-existing `newConversation()` into a new top-right Settings menu; no auth/schema/contract/external change, so no flags or hard gates fire; lands as normal (not tiny) because it spans >1 file and adds a new component.
Flags: none
Affects: apps/web chat UI (ChatHeader.tsx, ChatPanel.tsx, useAgentStream.ts) — no BE change; `/agent/stream` contract already supports a fresh `conversation_id`.
Input-type: change request

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

<!-- MIN-56, verbatim from Linear. -->

**New feature: Let users start a "New conversation" via the top-right Settings menu**

## Goal

Let the user start a new conversation with the chatbot without reloading or losing navigation context, through a quick-access button in the top-right corner.

## Proposed UI/UX

* Add a **Settings** icon (⚙️) in the top-right corner of the chat screen.
* Clicking the Settings icon shows a menu/dropdown with a **"New conversation"** option.
* When the user selects "New conversation":
  * Clear/reset the current chat history in the UI.
  * Initialize a new session (new session ID) for the conversation.
  * Show the initial welcome/shortcut screen again (first-time chat suggestions).

## To do

* Design the Settings icon and dropdown menu (positioned in the top-right corner).
* Implement the "New conversation" action: reset UI state, create a new session on the backend.
* Confirm that old context data (if stored on the BE) does not leak into the new session.
* Consider adding a confirmation dialog if the current conversation contains important content (to avoid accidental data loss).
* Test the flow: create a new conversation several times in a row and ensure context does not leak between sessions.

## What changed

Adds a Settings (⚙️) menu (`ChatSettingsMenu`) to the chat header's top-right with a "New conversation" action, mirroring `UserMenu`'s open/click-outside/Escape pattern. Selecting it resets the UI chat state via the existing `useAgentStream.newConversation()` (clears messages + stored id + panels), which re-shows `ChatEmptyState` and mints a fresh client `conversation_id` on the next message. A `window.confirm` guards the reset only when the transcript is non-empty. The gear is disabled while the agent is `working`/`waiting`, so a reset cannot race an in-flight stream. No backend change — a new `conversation_id` → new `thread_id` → empty checkpoint, so old context cannot leak.

### Rationale

The hook already exposes an unused `newConversation()` (clears messages + localStorage id + nulls `conversationIdRef`) and `ChatPanel` already re-renders `ChatEmptyState` whenever `messages.length === 0`. The lightest credible path is to plumb that existing function into a new header menu rather than build new reset logic or a BE endpoint. Fresh `conversation_id` → fresh `thread_id` → empty checkpoint means "no context leak" is already guaranteed on the BE.

### Alternatives considered

- BE reset endpoint — rejected: unnecessary; `conversation_id` is client-minted and the checkpointer is keyed per-thread, so a new id already isolates context.
- Confirmation dialog — the issue lists it as an optional "consider". Default assumption: include a lightweight confirm only when the current conversation has messages, to prevent accidental loss without adding friction to an empty chat. To be settled in the plan.

### Deviations

- Rule 1 (fix bug found in review) — Gated the settings gear on `status === "ready"` (passing the already-tested `disabled` prop from `ChatHeader`) to close a reset-vs-live-stream race: a mid-stream reset would let the in-flight `start`/`interrupt` event restore the old `conversation_id`, reopening the old BE thread. `ChatHeader.tsx`.
- Rule 2 (proof for the fix) — Added `ChatHeader.test.tsx` asserting the gear is enabled only when `ready` and disabled while `working`/`waiting`.

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| i18n key parity (en↔vi) | `python3 -c "import json;a=json.load(open('apps/web/messages/en.json'))['Chat'];b=json.load(open('apps/web/messages/vi.json'))['Chat'];ks={'settingsMenu','newConversation','newConversationConfirm'};assert ks<=a.keys() and ks<=b.keys()"` | 0 | both locales have the 3 keys |
| Types | `cd apps/web && pnpm exec tsc --noEmit` | 0 | clean |
| Lint | `cd apps/web && pnpm lint` | 0 | clean |
| Chat unit tests | `cd apps/web && pnpm exec vitest run src/components/chat/` | 0 | 12 files, 35 tests (incl. new ChatSettingsMenu + ChatHeader) |

### Rollback

- `git revert <sha>`

### Harness-Delta

- none
