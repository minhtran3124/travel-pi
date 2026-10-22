---
slug: side-panel-multi-category-tabs
status: shipped
owner: Minh Tran
created: 2026-09-08
---

# Side panel: one tab per places category (cafe + restaurant coexist)

## 1. Motivation

"Find cafes and restaurants in Da Nang" makes the concierge call `search_places` twice
(`category="cafe"`, then `category="restaurant"`). The backend streams two `panel` SSE events,
both `kind: "places"`, with distinct `tool_call_id`s and `data.category`. The frontend identifies a
panel by `kind` alone, so the restaurant panel deletes the cafe panel
(`useAgentStream.ts:160` `upsertPanelByKind`, `useAgentStream.ts:341` `attachPanelToMessage`),
and even if both survived, `SidePanel.tsx:65` builds its tab strip from `Set(kind)` — one
"Places" tab. The user watches the cafe list appear and vanish. Root cause and confirmed
defaults are recorded in `SUMMARY.md` (§Root cause, §Rationale).

Fix: panel identity becomes a **panel key** = `kind` plus a kind-specific sub-key (`places` →
`data.category`; every other kind → none). Same key still replaces (a repeat "more cafes"
search refreshes the cafe tab); different keys coexist as separate tabs.

## 2. Non-goals

- No backend change. The SSE `panel` contract, `search_places`, and the mapper stay as they are.
- No sub-key for `route` / `weather` / `air_quality` / `flights` / `hotels` — they keep
  latest-wins-per-kind (user-confirmed default 1).
- No cross-turn retention policy change — panels persist until `newConversation()` (default 3).
- No new i18n catalog entries. `data.category` arrives already localized from the backend
  (`app/streaming/panels/places.py` `CATEGORY_VI`), so the tab label reuses it verbatim.
- No merge of the two category results into one list (rejected in `SUMMARY.md` §Alternatives).

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|------|-------------------------|-----------------------|------------|
| SC-1 | `panelKey()` returns `places:cafe` for a places panel with `data.category = "cafe"`, `places` when category is null, and the bare `kind` for every non-places kind | `pnpm -C apps/web exec vitest run src/lib/stream/panel.test.ts` | exit 0 |
| SC-2 | After streaming two `places` panels with categories `cafe` then `restaurant` in one turn, `result.current.panels` has length 2 and the assistant message's `panels` has length 2, cafe first | `pnpm -C apps/web exec vitest run src/components/chat/useAgentStream.stream.test.tsx` | exit 0 |
| SC-3 | Streaming a second `places` panel with the same category `cafe` (new toolCallId) leaves `panels` at length 1 carrying the newer toolCallId; a second `weather` panel still replaces the first | `pnpm -C apps/web exec vitest run src/components/chat/useAgentStream.stream.test.tsx` | exit 0 |
| SC-4 | `SidePanel` given cafe + restaurant places panels renders two tab buttons whose accessible names are the category strings, the newest (restaurant) body is active, clicking the cafe tab shows the cafe body, and `focus={{ key: "places:cafe", nonce }}` activates the cafe tab | `pnpm -C apps/web exec vitest run src/components/chat/panel/SidePanel.test.tsx` | exit 0 |
| SC-5 | `ResultChips` renders one chip per places panel, whose visible titles are the category strings "cafe" and "restaurant" (capitalized by CSS only), and a places panel with null category is still titled "Places" | `pnpm -C apps/web exec vitest run src/components/chat/ResultChips.test.tsx` | exit 0 |
| SC-6 | Clicking a places chip in the docked widget focuses the drawer tab for that chip's panel key (ChatWidget passes `{ key, nonce }`) | `pnpm -C apps/web exec vitest run src/components/chat/ChatWidget.test.tsx` | exit 0 |
| SC-7 | Web app typechecks with the new `PanelFocus` shape | `pnpm -C apps/web exec tsc --noEmit` | exit 0 |
| SC-8 | Web lint passes on the touched files | `pnpm -C apps/web lint` | exit 0 |

> Baseline before any change (2026-09-08, branch `feat/side-panel-multi-category-tabs`):
> `vitest run src/components/chat` and `tsc --noEmit` both exit 0.

## Global Constraints

- Frontend only: no file under `apps/api/` is touched.
- Run every Node/pnpm command with Node 24 on PATH:
  `export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH"` (CLAUDE.md).
- Test-first: each task adds or extends the failing test before the implementation.
- The panel key helper lives in ONE place (`apps/web/src/lib/stream/panel.ts`); components and the
  hook import it — no component re-derives `kind + category` inline.
- Keep replace-on-same-key semantics: `upsert` never appends a duplicate key.
- The `focus` prop of `SidePanel` changes shape from `{ kind, nonce }` to `{ key, nonce }`;
  the only producer is `ChatWidget.tsx` and it must change in the same wave as the consumer.
- Do not touch `apps/web/src/components/chat/zzdebug.test.tsx` (pre-existing untracked stray file,
  not part of this work).
- Match existing style: render-phase adjust-on-change pattern in `SidePanel`, `capitalize`
  class for category text (as `PlacesPanel.tsx:60`).

## 4. Tasks

### Task 1.1 — Panel key + sub-label helpers (wave 1)

- **Files:** apps/web/src/lib/stream/panel.ts, apps/web/src/lib/stream/panel.test.ts
- **Action:** Add and export two pure helpers next to `PanelArtifact`:
  `panelKey(p: PanelArtifact): string` — returns `` `${p.kind}:${category}` `` when
  `p.kind === "places"` and `(p.data as PlacesPanelData).category` is a non-empty string,
  otherwise `p.kind`; and `panelSubLabel(p: PanelArtifact): string | null` — returns that same
  category string for places panels, `null` otherwise. Narrow `data` defensively (`data` is
  `unknown`; a non-object or missing `category` → no sub-key). Create `panel.test.ts` first with
  cases: places+cafe → `places:cafe`; places+null category → `places`; places with `data: {}` →
  `places`; weather → `weather`; sub-label mirrors (cafe / null / null). Update the `PanelArtifact`
  doc comment to say identity is `panelKey`, not `kind`.
- **Verify:** `pnpm -C apps/web exec vitest run src/lib/stream/panel.test.ts`
- **Done:** 5+ assertions pass; `grep -c "export function panelKey" apps/web/src/lib/stream/panel.ts` prints 1
- **Criteria:** SC-1
- **Interfaces:** Consumes the existing PanelArtifact and PlacesPanelData types (already in panel.ts). Produces `panelKey`, `panelSubLabel` in `apps/web/src/lib/stream/panel.ts`.

### Task 2.1 — Hook state keyed by panel key (wave 2)

- **Files:** apps/web/src/components/chat/useAgentStream.ts, apps/web/src/components/chat/useAgentStream.stream.test.tsx
- **Action:** Rename `upsertPanelByKind` → `upsertPanelByKey` and filter on
  `panelKey(p) !== panelKey(next)`; in `attachPanelToMessage` find the existing index by
  `panelKey(existing) === panelKey(panel)`. Update the three call sites (send / regenerate /
  resume) and the `panels` doc comment on the hook's return type ("latest per panel key: kind +
  places category"). Add to `useAgentStream.stream.test.tsx`, in the existing
  "per-turn activity + panels" describe, two tests written before the change: (a) stream
  `panel` events `{kind:"places", data:{category:"cafe", …}}` then
  `{kind:"places", data:{category:"restaurant", …}}` with distinct tool_call_ids → hook `panels`
  length 2 and assistant `panels` length 2 with `[0].data.category === "cafe"`; (b) stream
  places/cafe twice with new tool_call_ids → length 1 and `toolCallId` equals the second id.
  Keep the existing weather-replaces-weather assertions untouched (they cover SC-3's second half).
- **Verify:** `pnpm -C apps/web exec vitest run src/components/chat/useAgentStream.stream.test.tsx`
- **Done:** New tests (a) and (b) pass; all pre-existing tests in the file still pass; `grep -c upsertPanelByKind apps/web/src/components/chat/useAgentStream.ts` prints 0
- **Criteria:** SC-2, SC-3
- **Interfaces:** Consumes `panelKey` from `apps/web/src/lib/stream/panel.ts`. Produces `upsertPanelByKey` in `apps/web/src/components/chat/useAgentStream.ts` (module-private) and unchanged hook surface `panels: PanelArtifact[]`.

### Task 2.2 — Drawer tabs + focus keyed by panel key (wave 2)

- **Files:** apps/web/src/components/chat/panel/SidePanel.tsx, apps/web/src/components/chat/panel/SidePanel.test.tsx, apps/web/src/components/chat/ChatWidget.tsx, apps/web/src/components/chat/ChatWidget.test.tsx
- **Action:** In `SidePanel`: export `type PanelFocus = { key: string; nonce: number }` and
  change the `focus` prop to it; replace `activeKind` state with `activeKey`; build tabs from the
  renderable panels themselves (one button per panel, `key={panelKey(p)}`, no `Set(kind)`);
  resolve `active` with `renderable.find((p) => panelKey(p) === resolvedKey) ?? newest`; label
  each tab with `panelSubLabel(p)` rendered in a `capitalize` span when non-null, else the
  existing `t(PANEL_LABEL_KEYS[kind])`; key the body wrapper `<div key={panelKey(active)}>` so a
  tab switch between two places panels still remounts. In `ChatWidget.tsx` change `panelFocus`
  state and the `onOpenPanel` producer to `{ key: panelKey(panel), nonce }`. Tests first: extend
  `SidePanel.test.tsx` (add `places` to the mocked `PANEL_RENDERERS` / `PANEL_LABEL_KEYS`) with a
  test that renders `[cafe, restaurant]` places panels → two buttons named "cafe" and
  "restaurant" (accessible name is the category text), restaurant body active, click cafe → cafe
  body; a test that `focus={{ key: "places:cafe", nonce: 1 }}` activates cafe; and rewrite the
  existing focus test from `kind` to `key` values ("route", "weather"). In `ChatWidget.test.tsx`
  add or adjust a test asserting the chip click passes a `key` into `SidePanel` (mock SidePanel
  and capture props, following the file's existing mocking style).
- **Verify:** `pnpm -C apps/web exec vitest run src/components/chat/panel/SidePanel.test.tsx src/components/chat/ChatWidget.test.tsx`
- **Done:** Both files green; `grep -c "focus?: { kind" apps/web/src/components/chat/panel/SidePanel.tsx` prints 0; `grep -c "kind: panel.kind" apps/web/src/components/chat/ChatWidget.tsx` prints 0
- **Criteria:** SC-4, SC-6
- **Interfaces:** Consumes `panelKey`, `panelSubLabel` from `apps/web/src/lib/stream/panel.ts`. Produces `PanelFocus` type and the new `focus` prop contract in `apps/web/src/components/chat/panel/SidePanel.tsx`; `ChatWidget.tsx` is its only producer.

### Task 2.3 — Result chips titled by category (wave 2)

- **Files:** apps/web/src/components/chat/ResultChips.tsx, apps/web/src/components/chat/ResultChips.test.tsx
- **Action:** In `ResultChips`, compute `const title = panelSubLabel(panel) ?? (labelKey ? tPanel(labelKey) : panel.kind)`
  and render the sub-label in a `capitalize` span; keep `aria-label` / `title` composition and
  the `toolCallId` chip key unchanged. Test first: two places panels (cafe, restaurant) render
  two chips whose visible titles are "cafe" and "restaurant" and whose count badges are their
  `places.length`; a places panel with `category: null` still renders the "Places" title.
- **Verify:** `pnpm -C apps/web exec vitest run src/components/chat/ResultChips.test.tsx`
- **Done:** New assertions pass; existing flights/weather chip tests unchanged and green
- **Criteria:** SC-5
- **Interfaces:** Consumes `panelSubLabel` from `apps/web/src/lib/stream/panel.ts`. Produces updated `apps/web/src/components/chat/ResultChips.tsx` (same props).

### Task 3.1 — Whole-app typecheck + lint gate (wave 3)

- **Files:** (none — verification only; fix-ups land in the wave-2 files if tsc/lint flag them)
- **Action:** Run the typecheck and lint over `apps/web`. If `tsc` reports an error in a
  wave-2 file, fix it there (Rule 3 auto-fix) and note it under SUMMARY `### Deviations`.
  Then run the chat-directory vitest slice once as a smoke (cite in SUMMARY prose, not as a
  Verify row).
- **Verify:** `pnpm -C apps/web exec tsc --noEmit && pnpm -C apps/web lint`
- **Done:** Both commands exit 0; no file outside the wave-1/2 Files sets is modified (`git status --short apps/web` lists only those paths)
- **Criteria:** SC-7, SC-8
- **Interfaces:** Consumes all wave-1/2 outputs. Produces the green gate recorded in `specs/side-panel-multi-category-tabs/SUMMARY.md` `### Verify`.

## 5. Risks

- **Localized category as key.** `data.category` is the backend-localized string ("cafe" in
  en, "quán cà phê" in vi). If a traveller switches conversation language mid-thread, a cafe
  search in each language yields two tabs. Accepted: rare, harmless, and using the raw slug
  would need a backend field (out of scope, see Non-goals).
- **`SidePanel` newest-panel rule.** Auto-focusing the newest panel is kept, so restaurant (the
  later call) is the active tab on arrival; the cafe tab is one click away and never lost. If UAT
  wants "first result stays active", that is a one-line change in the adjust-on-change block.
- **Compact sheet.** `ChatPanel.tsx` renders `SidePanel panels={[sheetPanel]}` (one panel) —
  unaffected, but it re-types against the new `focus` prop; covered by SC-7.
- **Test doubles.** `SidePanel.test.tsx` mocks the registry with route/weather only; Task 2.2
  must add `places` to the mock or the places panels are filtered as unrenderable.

## 6. Status Log

- 2026-09-08 — plan authored after intake (`SUMMARY.md`); baseline chat vitest + tsc green on `feat/side-panel-multi-category-tabs`.
- 2026-09-08 — task 1.1 complete; commit d1459b5; review spec pass / quality approved (2 Minor: verify exit re-run by controller = 0; whitespace-only category not trimmed — outside brief contract).
- 2026-09-08 — tasks 2.1, 2.2, 2.3 complete; commits e3ba4ae, 3485d55, 7d8bd27; wave gate tsc 0 / lint 0 errors / 33 tests pass; per-task reviews dispatched.
- 2026-09-08 — task 3.1 complete (verify-only; tsc 0 / lint 0 / chat+stream smoke 155 tests pass). Reviews 2.1, 2.2, 2.3: spec pass / quality approved; Minor only (see SUMMARY ### Review roll-up). Run → verifying.
- 2026-09-08 — correctness-review: 6 angles over 8d830d9..7d8bd27, 5 locations deduped, scored independently (A 100, B 75, C 75, D 0; E/F unmodified-line advisory). A/B/C fixed in f76155f (A = user-approved Rule-4 additive `category_key` on the places panel). Intent review v1 ✅; re-review of fix + intent v2 dispatched.
- 2026-09-08 — re-review of f76155f: A/B/C closed, 1 P2 regression (stale chip focus re-pinned on drawer remount) fixed in e8f2e81 + 2 P3 advisories recorded; intent v2 ✅. Round-2 re-review + intent v3 dispatched.
- 2026-09-08 — re-review of e8f2e81: P2 closed; mirrored P2 (nonce restarted after clear → first chip click after a new panel dead) fixed in ba78360 (round 3 of 3); intent v3 ✅. Final re-review dispatched.
- 2026-09-08 — re-review of ba78360 pass (1 P3 advisory recorded); intent v4 ✅; receipt pinned at ba78360; full FE suite 161 pass, BE suite failures all local-env (see SUMMARY). Status → shipped; PR opened from feat/side-panel-multi-category-tabs → main.
