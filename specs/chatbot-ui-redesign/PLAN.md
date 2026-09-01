---
slug: chatbot-ui-redesign
status: proposed
owner: Minh Tran
created: 2026-08-28
---

# Chatbot UI Redesign

## 0. Global Constraints

- **Frontend only.** No file under `apps/api/` is touched. The `/agent/stream` SSE wire
  contract (`apps/web/src/lib/stream/parseSSE.ts`) is consumed exactly as it exists today —
  no new event types, no changed payloads.
- **Design system is fixed.** Use the shipped tokens (`ink`, `lime`, `panel`, `line`, `muted`,
  `radius-*`, `spacing-*`, `shadow-card|lift`). No new colors, no gradients, no glassmorphism.
  `globals.css` may gain *additive* `@keyframes` only (Task 4.1).
- **Do not edit `src/components/chat/panel/**`.** The 7 panel renderers and `registry.ts` are
  reused by wrapping, not by modification; their existing tests must stay green untouched.
- **Node 24 required** for any pnpm/vitest command:
  `export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH"` (the nvm default is 18).
- **i18n.** Every user-visible string goes through `next-intl` with a key in **both**
  `messages/en.json` and `messages/vi.json`. No hardcoded copy in components.
- **A11y floor.** Interactive elements keep an accessible name; live regions keep
  `aria-live="polite"`; all motion is silenced under `prefers-reduced-motion`.
- Rationale for every decision below lives in `design.md` §3 (Forks 1–7). Implementers must
  not re-litigate a fork; deviations go in `SUMMARY.md` → Deviations.

## 1. Motivation

The chat co-pilot is functionally strong (typed streaming, HITL interrupts, 7 panel renderers,
dark mode, en/vi) and presentationally behind the two reference shots reviewed in
`design.md` §1. Four concrete gaps, evidenced in `design.md` §2:

1. **The agent's work is invisible** — `subagent` / `tool_call` / `tool_result` events are
   parsed and then discarded (`useAgentStream.ts:377`); the user sees only "Working on it…".
2. **Results are detached from the question** that produced them (a global drawer, not a turn).
3. **The widget is unusable on phones** — a fixed 400px card that puts a second drawer beside
   itself in a `flex-row` at any viewport width.
4. **No per-message affordances** — no copy, no regenerate.

## 2. Non-goals

- Conversation history / recents (needs a new API contract → separate spec, higher lane).
- 👍/👎 rating (blocked on `specs/user-feedback-v1/`; no feedback route exists today).
- Voice mode, image generation, attachments, premium upsell — no backend capability.
- Any change to the SSE protocol, the panel renderers, or the color tokens.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|------|-------------------------|-----------------------|------------|
| SC-1 | Each assistant message carries the tool/subagent steps and the panels produced during its own turn | `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm -C apps/web exec vitest run src/components/chat/useAgentStream.stream.test.tsx` | exit 0 |
| SC-2 | A turn that used tools shows a live, human-labeled activity trail that collapses to one summary line when the turn ends | `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm -C apps/web exec vitest run src/components/chat/AgentActivityTrail.test.tsx` | exit 0 |
| SC-3 | Every completed assistant turn offers Copy and Regenerate; neither is offered mid-stream | `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm -C apps/web exec vitest run src/components/chat/MessageActions.test.tsx` | exit 0 |
| SC-4 | A tool result renders as a compact card inside the turn, and "Open" promotes it to the full renderer | `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm -C apps/web exec vitest run src/components/chat/ResultCard.test.tsx` | exit 0 |
| SC-5 | Below 640px the chat is a full-height sheet and never renders the drawer beside the panel | `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm -C apps/web exec vitest run src/components/chat/ChatWidget.test.tsx` | exit 0 |
| SC-6 | The empty state greets the user and offers a 2×2 capability grid of real agent capabilities | `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm -C apps/web exec vitest run src/components/chat/ChatEmptyState.test.tsx` | exit 0 |
| SC-7 | Follow-up chips ride on the composer as one rail instead of a separate stacked band | `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm -C apps/web exec vitest run src/components/chat/ChatComposer.test.tsx` | exit 0 |
| SC-8 | The header shows identity + a single status pill and keeps settings / expand / close reachable by name | `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm -C apps/web exec vitest run src/components/chat/ChatHeader.test.tsx` | exit 0 |
| SC-9 | Every `Chat` string exists in both en and vi | `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm -C apps/web exec vitest run src/messages.parity.test.ts` | exit 0 |
| SC-10 | The 7 existing panel renderers still pass, unmodified | `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm -C apps/web exec vitest run src/components/chat/panel` | exit 0 |
| SC-11 | The whole chat module type-checks and lints clean | `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm -C apps/web exec tsc --noEmit` | exit 0 |
| SC-12 | The transcript region announces politely and all new motion is disabled under reduced-motion | `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm -C apps/web exec vitest run src/components/chat/ChatPanel.test.tsx` | exit 0 |

## 4. Tasks

### Task 1.1 — Surface agent activity + per-turn panels in the stream hook (wave 1)

- **Files:** apps/web/src/components/chat/useAgentStream.ts, apps/web/src/components/chat/useAgentStream.stream.test.tsx
- **Action:** Replace the discard at `useAgentStream.ts:377` (`subagent / tool_call / tool_result:
  not surfaced`). Add `export type ActivityStep = { id: string; tool: string; subagent: string | null;
  status: "running" | "ok" | "error" }` and extend `ChatMessage` with `activity: ActivityStep[]`
  and `panels: PanelArtifact[]`, both scoped to the assistant message being streamed.
  On `subagent` record the active specialist; on `tool_call` push a step with `status:"running"`;
  on `tool_result` flip that step by `id`. On `panel`, append to the *current* assistant
  message's `panels` in addition to the existing flat `stream.panels` (keep the flat array —
  the drawer still consumes it). On `reset`, clear the current message's content but KEEP its
  activity (the reflection loop re-ran the sub-agent; the work still happened).
  Do not add fields to the SSE parser — everything needed is already parsed.
- **Verify:** `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm -C apps/web exec vitest run src/components/chat/useAgentStream.stream.test.tsx`
- **Criteria:** SC-1
- **Interfaces:** Consumes the existing `SSESubagentEvent` / `SSEToolCallEvent` /
  `SSEToolResultEvent` / `SSEPanelEvent` types. Produces `ActivityStep` and the widened
  `ChatMessage` in `useAgentStream.ts` — the contract every wave-2 component is built against.
- **Done:** New tests assert that a token+tool_call+tool_result+panel+done sequence yields one
  assistant message with 1 completed step and 1 attached panel; existing stream tests stay green.

### Task 1.2 — Chat i18n keys for the new surface, en + vi (wave 1)

- **Files:** apps/web/messages/en.json, apps/web/messages/vi.json, apps/web/src/messages.parity.test.ts
- **Action:** Add the `Chat` keys the redesign needs, in both locales: `activity.*`
  (`running`, `summary` with `{count}`/`{seconds}` params, `expand`, `collapse`, plus one
  human label per agent tool used by the trail — hotels, flights, places, weather, route,
  air quality, budget, journal — and a generic `activity.working` fallback), `actions.copy`,
  `actions.copied`, `actions.regenerate`, `result.open`, `result.close`, and
  `capabilities.*` for the 4 empty-state tiles. Reuse existing keys where they already say the
  right thing (`greetingTitle`, `greetingBody`, `retry`, `suggestions.*`, `followups.*`).
  Add `src/messages.parity.test.ts`: a recursive key-set comparison of en vs vi over the whole
  file, failing with the offending key paths.
- **Verify:** `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm -C apps/web exec vitest run src/messages.parity.test.ts`
- **Criteria:** SC-9
- **Interfaces:** Consumes the existing `messages/*.json` shape. Produces `apps/web/messages/en.json`,
  `apps/web/messages/vi.json` key sets and `apps/web/src/messages.parity.test.ts`.
- **Done:** Parity test passes; every key referenced by the wave-2/3 tasks resolves in both locales.

### Task 1.3 — Responsive shell: mobile sheet vs. desktop docked panel (wave 1)

- **Files:** apps/web/src/components/chat/ChatWidget.tsx, apps/web/src/components/chat/ChatWidget.test.tsx
- **Action:** Fix `design.md` G3. Replace the unconditional
  `fixed bottom-6 right-6 … flex flex-row items-end` composition with two layouts driven by a
  `sm` breakpoint: below `sm`, the open widget is a full-viewport sheet (`inset-0`, `h-dvh`,
  `role="dialog"` owned by `ChatPanel`) and the `SidePanel` drawer is **never** rendered beside
  it — panels are reachable only through the inline result cards (Task 2.3); at `sm` and above,
  keep today's docked floating panel + drawer row. Keep the launcher FAB fixed bottom-right in
  both. Add `ChatWidget.test.tsx` driving the breakpoint with a `matchMedia` mock.
  Do not change the trip-id derivation, the query-invalidation callback, or the
  `newestPanelId` re-surface logic.
- **Verify:** `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm -C apps/web exec vitest run src/components/chat/ChatWidget.test.tsx`
- **Criteria:** SC-5
- **Interfaces:** Consumes `useAgentStream`, `ChatPanel`, `SidePanel`. Produces the
  `isCompact` layout contract in `apps/web/src/components/chat/ChatWidget.tsx` plus
  `apps/web/src/components/chat/ChatWidget.test.tsx`.
- **Done:** Under `sm` the drawer is absent from the tree and the panel fills the viewport;
  at `sm`+ the current side-by-side layout is unchanged.

### Task 2.1 — `AgentActivityTrail` component (wave 2)

- **Files:** apps/web/src/components/chat/AgentActivityTrail.tsx, apps/web/src/components/chat/AgentActivityTrail.test.tsx
- **Action:** Build the Fork-4 component: props `{ steps: ActivityStep[]; isStreaming: boolean }`.
  While streaming, render each step as a row — a small state dot (running = pulsing `lime`,
  ok = `status-confirmed`, error = `status-cancelled`), the **localized human label** from
  `activity.*` resolved by tool name, falling back to `activity.working`; **never** render the
  raw tool name or `argsPreview`. When `isStreaming` is false, collapse to a single
  `activity.summary` line (count + elapsed) that expands on click (`aria-expanded`).
  Render `null` when `steps` is empty. Wrap in `aria-live="polite"`. All motion behind
  `motion-reduce:` variants. Presentational only — no hook access.
- **Verify:** `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm -C apps/web exec vitest run src/components/chat/AgentActivityTrail.test.tsx`
- **Criteria:** SC-2
- **Interfaces:** Consumes `ActivityStep` (Task 1.1) and the `activity.*` keys (Task 1.2).
  Produces `apps/web/src/components/chat/AgentActivityTrail.tsx`.
- **Done:** Tests cover empty → null, streaming → per-step rows with localized labels,
  done → collapsed summary that expands, and that no raw tool name appears in the DOM.

### Task 2.2 — `MessageActions` component (wave 2)

- **Files:** apps/web/src/components/chat/MessageActions.tsx, apps/web/src/components/chat/MessageActions.test.tsx
- **Action:** Build the Fork-5 row: props `{ content: string; onRegenerate?: () => void; disabled?: boolean }`.
  Two icon buttons — Copy (`navigator.clipboard.writeText`, swapping to an `actions.copied`
  confirmation for ~1.5s, degrading silently if the clipboard API is unavailable) and
  Regenerate (rendered only when `onRegenerate` is supplied). Both carry `aria-label`s from
  `actions.*`. Ghost styling: `text-muted`, hover to `text-ink`, no fill — this row must not
  compete with the composer's send button. **No thumbs up/down** (`design.md` Fork 5: there is
  no feedback endpoint); leave the component's button list trivially extensible.
- **Verify:** `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm -C apps/web exec vitest run src/components/chat/MessageActions.test.tsx`
- **Criteria:** SC-3
- **Interfaces:** Consumes the `actions.*` keys (Task 1.2). Produces
  `apps/web/src/components/chat/MessageActions.tsx`.
- **Done:** Copy writes the message text and shows the confirmation; Regenerate fires the
  callback and is absent when no callback is given; both are inert when `disabled`.

### Task 2.3 — `ResultCard` — inline panel summary that promotes to the full renderer (wave 2)

- **Files:** apps/web/src/components/chat/ResultCard.tsx, apps/web/src/components/chat/ResultCard.test.tsx
- **Action:** Build the Fork-2 hybrid. Props `{ panel: PanelArtifact; onOpen: (p: PanelArtifact) => void }`.
  Render a compact card — kind icon, the localized `PANEL_LABEL_KEYS` title, a one-line
  summary derived from the payload (e.g. item count), and a `result.open` affordance — using
  `radius-md`, `border-line`, `shadow-card`. Clicking anywhere on the card calls `onOpen`.
  **Import `PANEL_LABEL_KEYS` / `PANEL_RENDERERS` from `./panel/registry` and do not modify
  that file or any renderer** (Global Constraints): a panel `kind` with no registered renderer
  must render `null`, matching `SidePanel`'s existing gate. The heavy renderer stays in the
  drawer/sheet — this card never mounts it.
- **Verify:** `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm -C apps/web exec vitest run src/components/chat/ResultCard.test.tsx`
- **Criteria:** SC-4, SC-10
- **Interfaces:** Consumes `PanelArtifact`, `PANEL_LABEL_KEYS`, `PANEL_RENDERERS` (unmodified)
  and the `result.*` keys. Produces `apps/web/src/components/chat/ResultCard.tsx`.
- **Done:** A known `kind` renders a titled card and fires `onOpen`; an unknown `kind` renders
  nothing; `src/components/chat/panel` tests are untouched and still pass.

### Task 2.4 — Empty state as a capability grid (wave 2)

- **Files:** apps/web/src/components/chat/ChatEmptyState.tsx, apps/web/src/components/chat/ChatEmptyState.test.tsx
- **Action:** Restyle the first-run state from a vertical list into the reference **2×2
  capability grid** (`design.md` §1, both refs): keep `AgentAvatar` + `greetingTitle` /
  `greetingBody`, then a `grid grid-cols-2 gap-sm` of 4 tiles, each an icon chip + short
  `capabilities.*` label + one-line subtitle, mapping to the four *existing* prompts in
  `suggestions.*` — plan / find nearby / weather / budget. Single column below `sm`.
  Do **not** invent tiles for capabilities the agent lacks. Preserve the current staggered
  entrance animation and the `disabled` behavior; add `ChatEmptyState.test.tsx`.
- **Verify:** `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm -C apps/web exec vitest run src/components/chat/ChatEmptyState.test.tsx`
- **Criteria:** SC-6
- **Interfaces:** Consumes `suggestions.*` + new `capabilities.*` keys and `AgentAvatar`.
  Produces the grid layout in `apps/web/src/components/chat/ChatEmptyState.tsx`.
- **Done:** Four tiles render, each dispatching its existing prompt through `onPick`; the grid
  collapses to one column at the compact breakpoint.

### Task 3.1 — Compose the turn: activity trail + result cards + actions in `MessageList` (wave 3)

- **Files:** apps/web/src/components/chat/MessageList.tsx, apps/web/src/components/chat/MessageList.render.test.tsx
- **Action:** Mount the wave-2 components per assistant turn, reading `activity` and `panels`
  off the message (Task 1.1) — no new prop plumbing from `ChatPanel` beyond `onOpenPanel` and
  `onRegenerate`. Order inside an assistant turn: `AgentActivityTrail` → bubble
  (`AssistantMarkdown`) → `ResultCard` per attached panel → `MessageActions`. Show the trail in
  place of `TypingDots` when the streaming message has steps but no content yet; keep
  `TypingDots` for the no-tool case. `MessageActions` renders only on completed assistant
  messages. Keep the existing scroll-to-end effect and the user-bubble styling unchanged.
- **Verify:** `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm -C apps/web exec vitest run src/components/chat/MessageList.render.test.tsx`
- **Criteria:** SC-2, SC-3, SC-4
- **Interfaces:** Consumes `AgentActivityTrail`, `MessageActions`, `ResultCard`, and the
  widened `ChatMessage`. Produces the turn composition in
  `apps/web/src/components/chat/MessageList.tsx`.
- **Done:** A turn with steps + a panel renders trail, bubble, card and actions in that order;
  a streaming turn shows no actions; existing render tests still pass.

### Task 3.2 — Composer owns the chip rail (wave 3)

- **Files:** apps/web/src/components/chat/ChatComposer.tsx, apps/web/src/components/chat/ChatSuggestions.tsx, apps/web/src/components/chat/ChatComposer.test.tsx, apps/web/src/components/chat/ChatSuggestions.test.tsx
- **Action:** Fix `design.md` G6 for the composer half: `ChatComposer` accepts an optional
  `suggestions` slot and renders it as a horizontally scrollable rail *inside* its own
  container above the input (reference pattern: Ref A's action-chip rail), instead of
  `ChatPanel` stacking `ChatSuggestions` as a separate bordered band. `ChatSuggestions` keeps
  its key→label/prompt resolution and pill styling; it loses its own border/background band.
  Rail scrolls horizontally with `overflow-x-auto` + hidden scrollbar; it must never wrap into
  a second row on mobile. Keep Enter-to-send / Shift+Enter-newline and the autogrow cap.
- **Verify:** `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm -C apps/web exec vitest run src/components/chat/ChatComposer.test.tsx`
- **Criteria:** SC-7
- **Interfaces:** Consumes `followups.*` keys. Produces the `suggestions` slot on
  `apps/web/src/components/chat/ChatComposer.tsx` and the band-less
  `apps/web/src/components/chat/ChatSuggestions.tsx`.
- **Done:** Chips render inside the composer, dispatch their prompt, and are suppressed while
  streaming or during an interrupt; keyboard send behavior unchanged.

### Task 3.3 — Header: identity + one status pill (wave 3)

- **Files:** apps/web/src/components/chat/ChatHeader.tsx, apps/web/src/components/chat/ChatHeader.test.tsx
- **Action:** Consolidate the header to `AgentAvatar` + title + a single status **pill**
  (dot + label, `rounded-pill bg-panel-raised`) replacing the loose two-line block, keeping
  `aria-live="polite"` on the status. Keep settings / expand-shrink / close, and add a
  compact-mode affordance: below `sm` the expand toggle is hidden (the sheet is already full
  screen) and the close button gets a larger 44px hit target. Retire the header's gradient
  wash in favour of a flat `bg-panel` + `border-line` (the accent budget now goes to the
  activity trail — `design.md` Fork 7). No change to `ChatSettingsMenu`.
- **Verify:** `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm -C apps/web exec vitest run src/components/chat/ChatHeader.test.tsx`
- **Criteria:** SC-8
- **Interfaces:** Consumes `AgentStatus`, `Chat.status*` keys. Produces the pill markup in
  `apps/web/src/components/chat/ChatHeader.tsx`.
- **Done:** All three statuses render a named pill; every control keeps its accessible name;
  the expand toggle is absent in compact mode.

### Task 4.1 — Panel chrome, sheet a11y and motion (wave 4)

- **Files:** apps/web/src/components/chat/ChatPanel.tsx, apps/web/src/components/chat/ChatPanel.test.tsx, apps/web/src/app/globals.css
- **Action:** Final integration pass on the container. (a) Remove the standalone
  "Show/Hide panel" band — panels are now reached from inline `ResultCard`s; route
  `onOpenPanel` to the desktop drawer or, in compact mode, to a bottom sheet.
  (b) Collapse the remaining stacked bands so at most one non-transcript band shows at a time
  (`design.md` G6): interrupt > retry > composer-with-rail. (c) Compact mode: `aria-modal="true"`,
  focus trap, `Escape` closes, body scroll locked while open, restore focus to the launcher on
  close. (d) Add the additive `@keyframes` for the trail dot / card reveal to `globals.css`,
  each paired with a `prefers-reduced-motion: reduce` no-op — do not touch any color token.
- **Verify:** `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm -C apps/web exec vitest run src/components/chat/ChatPanel.test.tsx`
- **Criteria:** SC-12
- **Interfaces:** Consumes every wave-2/3 component. Produces the integrated
  `apps/web/src/components/chat/ChatPanel.tsx` and the additive keyframes in
  `apps/web/src/app/globals.css`.
- **Done:** Escape closes the compact sheet and returns focus to the launcher; only one band
  renders at a time; reduced-motion tests confirm the new animations are inert.

### Task 4.2 — Type + lint gate over the changed module (wave 4)

- **Files:** apps/web/src/components/chat, apps/web/src/messages.parity.test.ts
- **Action:** Run the type-checker and linter across the workspace and fix only fallout from
  this plan's changes (Rule 3: no adjacent cleanups). Confirm the untouched panel-renderer
  suite is still green. Record every command + exit code in `SUMMARY.md` → `### Verify`.
- **Verify:** `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm -C apps/web exec tsc --noEmit`
- **Criteria:** SC-10, SC-11
- **Interfaces:** Consumes the full changed module. Produces the populated `### Verify` table
  in `specs/chatbot-ui-redesign/SUMMARY.md`.
- **Done:** `tsc --noEmit` and `eslint` exit 0; `vitest run src/components/chat` exits 0.

### Task 4.3 — Phase-level visual acceptance (wave 4)

- **Files:** specs/chatbot-ui-redesign/SUMMARY.md
- **Action:** Not a task-level automated check (`rules/plan-format.md` guardrail 2 — browser
  verification is phase-level). Drive the real app with a Node-24 `playwright-core` script
  (Playwright MCP is broken in this environment) at 390×844 and 1440×900, in light and dark,
  capturing: empty state, a streaming turn with an active trail, a completed turn with a
  result card and actions, the compact sheet, and an interrupt. Attach the observations to
  `SUMMARY.md` → `### Not auto-verified` with the tier reached.
- **Verify:** `python3 .claude/scripts/verify_summary.py --lane chatbot-ui-redesign`
- **Criteria:** SC-11
- **Interfaces:** Consumes the running dev app. Produces the completed
  `specs/chatbot-ui-redesign/SUMMARY.md` evidence sections.
- **Done:** All five states captured at both breakpoints in both themes with no layout
  breakage, and the SUMMARY evidence panel is complete.

## 5. Risks

See `design.md` §6 for the full table. Plan-level watch items:

- **Wave-2 contract drift.** Four components are built in parallel against the `ActivityStep`
  and widened `ChatMessage` contract from Task 1.1. Task 1.1 must land and be reviewed before
  wave 2 dispatches — this is why it is alone with i18n and the shell in wave 1.
- **Shared-file collisions.** Waves are partitioned so no two same-wave tasks share a file
  (`rules/wave-parallelism.md`); every wave-2 task writes only new files plus its own test.
  `ChatPanel.tsx` is deliberately single-owner in wave 4.
- **Silent i18n gaps.** Vietnamese copy is easy to forget under a deadline; Task 1.2's parity
  test makes the gap a failing check rather than a review catch.
- **Regression surface in `useAgentStream`.** It is 666 lines with three separate event loops
  (`start`/nested/resume). Task 1.1 must handle the tool events in **all** of them, not only
  the primary loop at line 332.

## 6. Status Log

- 2026-08-28 — Intake complete (`SUMMARY.md`: normal / medium). References reviewed via
  chrome-devtools MCP; `design.md` written with Forks 1–7 resolved. Plan drafted, status
  `proposed`. Next: `using-git-worktrees` → `subagent-driven-development`.
