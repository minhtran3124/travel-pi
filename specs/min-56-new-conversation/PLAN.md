---
slug: min-56-new-conversation
status: shipped
owner: Minh Tran
created: 2026-07-08
---

# MIN-56 — "New conversation" via a top-right Settings menu

## 1. Motivation

Let users start a fresh chatbot conversation from a quick-access Settings (⚙️) menu in
the chat header's top-right — resetting the UI transcript, minting a new session id, and
re-showing the welcome/shortcut empty state — without a page reload or losing navigation
context.

The heavy lifting already exists: `useAgentStream` exposes an **unused** `newConversation()`
that clears messages + the stored `conversation_id` + panels, and `ChatPanel` already
re-renders `ChatEmptyState` whenever `messages.length === 0`. A new `conversation_id` →
new `thread_id` → empty LangGraph checkpoint, so **no old context leaks** by construction.
This work is purely wiring that function into a new header menu. **No backend change.**

## 2. Non-goals

- No backend endpoint / no checkpointer or schema change (a fresh client-minted
  `conversation_id` is already an isolated session).
- No persisted list of past conversations / history switcher (single-session reset only).
- No settings beyond "New conversation" in the menu (leave room, but don't build more).

## 3. Success Criteria

- A Settings icon sits in the chat header top-right; clicking it opens a dropdown with a
  "New conversation" item (keyboard: Escape + click-outside close, mirroring `UserMenu`).
- Choosing "New conversation" resets the transcript, re-shows `ChatEmptyState`, and the next
  message streams under a brand-new `conversation_id` (verified: no leaked prior context).
- When the current conversation has messages, a confirmation guards accidental loss; when
  empty, it resets immediately (no needless prompt).
- `en.json` / `vi.json` stay in sync; `pnpm test` + `pnpm lint` green.

## 4. Tasks

### Task 1.1 — i18n keys (en + vi)

```xml
<task id="1.1" wave="1">
  <files>apps/web/messages/en.json, apps/web/messages/vi.json</files>
  <action>Under the "Chat" namespace add three keys to BOTH locale files (keep key order/style consistent with neighbors): `settingsMenu` (aria-label for the settings trigger, e.g. EN "Conversation settings"), `newConversation` (menu item + its aria-label, EN "New conversation"), and `newConversationConfirm` (confirm text shown only when the transcript is non-empty, EN "Start a new conversation? The current chat will be cleared."). Provide natural Vietnamese for vi.json (e.g. "Cài đặt hội thoại", "Cuộc trò chuyện mới", "Bắt đầu cuộc trò chuyện mới? Đoạn chat hiện tại sẽ bị xoá."). Do not touch other keys.</action>
  <verify>cd apps/web && python3 -c "import json;a=json.load(open('messages/en.json'))['Chat'];b=json.load(open('messages/vi.json'))['Chat'];ks={'settingsMenu','newConversation','newConversationConfirm'};assert ks<=a.keys() and ks<=b.keys(), ks-(a.keys()&b.keys());print('ok')"</verify>
  <done>Both locale files contain the three new Chat keys; JSON parses; no unrelated keys changed.</done>
</task>
```

### Task 2.1 — ChatSettingsMenu component + test

```xml
<task id="2.1" wave="2">
  <files>apps/web/src/components/chat/ChatSettingsMenu.tsx, apps/web/src/components/chat/ChatSettingsMenu.test.tsx</files>
  <action>Create ChatSettingsMenu.tsx: a "use client" settings dropdown mirroring src/components/auth/UserMenu.tsx's open-state + click-outside(mousedown) + Escape pattern (useRef wrapper, useEffect listeners gated on `open`). Props: `{ onNewConversation: () => void; disabled?: boolean }`. Trigger is an icon button styled with the SAME classes ChatHeader uses for its header icon buttons (a gear/⚙️ SVG at 18×18, viewBox 0 0 24 24, stroke currentColor — match ChatHeader's svgProps); set `aria-haspopup="menu"`, `aria-expanded`, and `aria-label={t("settingsMenu")}` via useTranslations("Chat"); respect `disabled`. Dropdown: `role="menu"`, right-aligned (`absolute right-0`), one `role="menuitem"` button labelled `t("newConversation")` that calls `onNewConversation()` then closes. Keep it minimal — no extra menu items. Add ChatSettingsMenu.test.tsx (vitest + @testing-library/react) mocking next-intl exactly like ChatComposer.test.tsx (`useTranslations: () => (k) => k`): assert (a) menu is closed initially (query "newConversation" is null), (b) clicking the trigger opens it, (c) clicking the "newConversation" item fires the onNewConversation spy, (d) the trigger is disabled when `disabled` is set.</action>
  <verify>cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm exec vitest run src/components/chat/ChatSettingsMenu.test.tsx</verify>
  <done>Component renders; menu opens/closes; item invokes callback; disabled honored; test file green.</done>
</task>
```

### Task 3.1 — Wire into ChatHeader + ChatPanel

```xml
<task id="3.1" wave="3">
  <files>apps/web/src/components/chat/ChatHeader.tsx, apps/web/src/components/chat/ChatPanel.tsx, apps/web/src/components/chat/ChatHeader.test.tsx</files>
  <action>ChatHeader.tsx: add prop `onNewConversation: () => void` to ChatHeaderProps and render `<ChatSettingsMenu onNewConversation={onNewConversation} />` as the FIRST control in the right-hand button group (before the expand/close buttons), so the gear sits top-right; import it from "./ChatSettingsMenu". ChatPanel.tsx: destructure `newConversation` from `stream`; define a `handleNewConversation` that, when `messages.length > 0`, guards with `window.confirm(t("newConversationConfirm"))` before calling `stream.newConversation()`, and resets immediately when the transcript is empty; pass it to `<ChatHeader onNewConversation={handleNewConversation} />`. No other behavior changes. (The side-panel drawer auto-hides: it derives from `stream.panels`, which `newConversation()` already clears.)</action>
  <verify>cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm exec tsc --noEmit && pnpm lint && pnpm exec vitest run src/components/chat/</verify>
  <done>Types + lint clean; chat test suite green; gear renders top-right and triggers reset (with confirm only when non-empty).</done>
</task>
```

## 5. Risks

- **Confirmation UX choice** — v1 uses a native `window.confirm` gated on a non-empty
  transcript (simplest credible guard against accidental loss; the two-step menu already
  reduces misclicks). A bespoke in-panel dialog is deferred unless requested.
- **i18n drift** — vi.json must gain the same keys; Task 1.1's verify asserts parity.
- **Low overall risk** — additive FE-only, no BE/contract/schema change (SUMMARY: normal lane).

## 6. Status Log

- 2026-07-08 — Plan drafted; branch `feat/min-56-new-conversation` off `v3`.
- 2026-07-08 — Tasks 1.1–3.1 implemented. Independent review caught a reset-vs-live-stream
  race (a mid-stream reset let the in-flight `start` event restore the old `conversation_id`,
  leaking BE context). Fixed by gating the gear on `status === "ready"` (`disabled` when
  `working`/`waiting`), which also wires the previously-dead `disabled` prop. Added
  `ChatHeader.test.tsx` as the regression guard. tsc 0 · lint 0 · 35 chat tests green.
- 2026-07-08 — shipped via `feat/min-56-new-conversation` (PR #75 → v3).
