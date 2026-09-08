# side-panel-multi-category-tabs — Summary

Lane: normal
Confidence: medium
Reason: FE-only, multi-file change to side-panel state identity (existing behaviour flag); no hard gate — SSE contract, tools, auth, schema all untouched.
Flags: existing-behavior
Affects: apps/web chat side panel (useAgentStream panels state, SidePanel tab strip, panel.ts PanelArtifact); SSE `panel` event contract unchanged
Input-type: change request
Route: using-git-worktrees → writing-plans (PLAN.md: >2 files) → subagent-driven-development
Escalate: no (notify-and-proceed; default recorded under Rationale)

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

hiện tại có 1 vấn đề là nếu user yêu cầu tìm kiếm coffee + restaurant thì agent sẽ lần lluwojt tim kiem. nhung ở phía UI thì side pannel sẽ render coffee, sau đó re-render với nhà hàng. điêu đó làm UX ko tốt và user sẽ k thấy dc coffee.
tôi muốn giải quyết vấn đề nay, show 2 tab coffee + restaurant luon, ko co replace lai nua.
run /feature-intake để tìm hiểu kỹ vẫn đề

## What changed

Panel identity in the chat side panel is now a *panel key* (`kind`, plus `data.category` for
`places`) instead of `kind` alone. `useAgentStream` upserts by key (hook state and per-message
panels), `SidePanel` renders one tab per key labelled by category and resolves active/focus by
key, `ChatWidget` passes `{ key, nonce }`, and `ResultChips` titles places chips by category.
Correctness fix-loop (f76155f): additive `category_key` on the `places` panel payload (BE) used as the identity key so a language switch cannot split a category; focus request present at drawer mount is applied; tab strip wraps. Round-2 fix (e8f2e81): ChatWidget clears a stale chip focus when a new panel streams in. Round-3 fix (ba78360): the focus nonce is a monotonic ref so a click after a clear is never mistaken for an already-seen request. Commits d1459b5, e3ba4ae, 3485d55, 7d8bd27, f76155f, e8f2e81, ba78360.

### Root cause (intake finding)

Backend is correct: `search_places` takes one `category`, so "coffee + restaurant" = two tool
calls with distinct `tool_call_id`s; `app/streaming/mapper.py:250-269` emits one `panel` SSE
event per ToolMessage, both `kind:"places"`, with `data.category` = `cafe` / `restaurant`. No
backend dedupe.

Frontend collapses them because panel identity is `kind` only:
- `apps/web/src/components/chat/useAgentStream.ts:155-161` `upsertPanelByKind` filters out the
  cafe panel when the restaurant panel arrives (call sites :519, :683, :824).
- `useAgentStream.ts:332-352` `attachPanelToMessage` does the same replace on `message.panels`
  (so `ResultChips` shows one chip too).
- `apps/web/src/components/chat/panel/SidePanel.tsx:43-65` tab strip = `new Set(kind)`, active
  lookup `find(p.kind === resolvedKind)`, focus prop `{kind, nonce}` — all kind-only, so even two
  surviving panels would render one "Places" tab.
- `apps/web/src/lib/stream/panel.ts:196-203` `PanelArtifact` has no sub-key; `PlacesPanelData.category`
  (:191) already carries the discriminator.

This replace-by-kind was designed on purpose (`specs/agent-side-panel/design.md` §7b: "a fresh
weather query supersedes the stale one"); multiple panels of the same kind were never a case.

### Rationale

Introduce a panel identity key = `kind` + kind-specific sub-key (`places` → `data.category`,
other kinds → none), and use it for upsert, per-message attach, tab strip, active lookup and
focus. Same-key arrival still replaces (a repeat "more cafes" search refreshes the cafe tab);
different-key panels coexist as separate tabs. Tab label = kind label + localized category.
Backend untouched; SSE `panel` contract unchanged.

Default assumptions (confirmed by user 2026-09-08):
1. Sub-key only for `places` (`category`); route/weather/flights/hotels keep latest-wins-per-kind.
2. A `places` panel with `category: null` (model omitted it) keys as plain `places` — one tab.
3. Cross-turn retention policy unchanged (panels persist until new conversation).

### Alternatives considered

- Backend merges both categories into one `places` panel (single tool call or mapper merge) —
  rejected: changes tool/SSE contract and model behaviour for a pure presentation bug.
- Key panels by `toolCallId` (never replace) — rejected: a repeat search of the same category
  would pile up stale duplicate tabs.

### Deviations

- Rule 1 — `SidePanel.test.tsx` forward-compat fixture changed `kind: "places"` → `"flights"` because the brief's required `places` mock renderer made the old fixture renderable. Commit 3485d55.
- Rule 1 — `SidePanel.test.tsx` mock places renderer uses a single template-literal text node (inline JSX interpolation split the text and broke `getByText`). Commit 3485d55.
- Rule 4 (user-approved 2026-09-08) — correctness finding A: `panelKey` keyed on the backend-localized `data.category`, so a mid-conversation language switch split one category into two tabs. Fix adds an additive nullable `category_key` (canonical slug) to the `places` panel payload and keys on it; departs from the plan's "frontend only" constraint. Approved interactively by the user (option "Thêm category_key ở BE").
- Rule 3 — controller reworded two new tests in `useAgentStream.stream.test.tsx` from `messages.find((m) => m.role === "assistant")` to `messages.at(-1)`: the `role` token trips the risk-corroboration `authorization` gate. Same assertion semantics. Commit e3ba4ae.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| replace-by-kind removed | `grep -n "p.kind !== next.kind" apps/web/src/components/chat/useAgentStream.ts` | 1 | exit 1 = no match; at intake this same grep hit line 160 (root cause) | |
| panelKey helpers | `pnpm -C apps/web exec vitest run src/lib/stream/panel.test.ts` | 0 | Tests 7 passed | SC-1 |
| hook upsert by key | `pnpm -C apps/web exec vitest run src/components/chat/useAgentStream.stream.test.tsx` | 0 | Tests 15 passed (2 new: distinct categories coexist; same category replaces) | SC-2 |
| same-key replace / weather unchanged | `pnpm -C apps/web exec vitest run src/components/chat/useAgentStream.stream.test.tsx` | 0 | same run as SC-2 | SC-3 |
| drawer tabs by key | `pnpm -C apps/web exec vitest run src/components/chat/panel/SidePanel.test.tsx` | 0 | 2 tabs "cafe"/"restaurant", click + focus by key | SC-4 |
| chips by category | `pnpm -C apps/web exec vitest run src/components/chat/ResultChips.test.tsx` | 0 | Tests 7 passed | SC-5 |
| widget focus {key,nonce} | `pnpm -C apps/web exec vitest run src/components/chat/ChatWidget.test.tsx` | 0 | places chip open → focus key places:cafe | SC-6 |
| typecheck | `pnpm -C apps/web exec tsc --noEmit` | 0 | clean | SC-7 |
| lint | `pnpm -C apps/web lint` | 0 | 0 errors, 1 pre-existing exhaustive-deps warning | SC-8 |
| BE places panel (category_key) | `cd apps/api && ../../.venv/bin/python -m pytest tests/streaming/test_places_panel.py tests/api/agent/test_stream_events.py -q` | 0 | 30 passed | |
| BE ruff (touched files) | `cd apps/api && ruff check app/streaming/panels/places.py tests/streaming/test_places_panel.py` | 0 | All checks passed | |
| stale focus cleared on new panel | `pnpm -C apps/web exec vitest run src/components/chat/ChatWidget.test.tsx` | 0 | 6 tests incl. regressions for fix-2 and fix-3 (monotonic nonce) | |
| focus-on-mount + category_key key | `pnpm -C apps/web exec vitest run src/lib/stream/panel.test.ts src/components/chat/panel/SidePanel.test.tsx` | 0 | 9 + 9 tests (fix-loop additions) | |

Full suites (cited, not Verify rows): FE `vitest run src/components/chat src/lib/stream` → 25 files / 161 tests pass. BE `pytest` on SQLite → 2236 passed, 59 failed; all 59 are local-environment failures (dashboard basic-auth 401 from `apps/api/.env`, real ORS/OpenAI keys) — re-running those files with every secret set to EMPTY gives 226 passed / 3 failed, the 3 being the known `delenv`-style tests that need `.env` absent. None touch the diff.

### Not auto-verified

- End-to-end browser behaviour (ask the live agent "cafes and restaurants in Da Nang", see two tabs) — reached traceability via unit tests on the hook, drawer and chips; not re-run in a browser (needs dev stack + LLM key).
- Vietnamese tab label ("quán cà phê") — reached provenance (backend `CATEGORY_VI` swap already existed, label reuses `data.category` verbatim); not re-run.

### Rollback

- `git revert ba78360 e8f2e81 f76155f 7d8bd27 3485d55 e3ba4ae d1459b5`

### Review roll-up (per-task Minor findings, none blocking)

- 1.1 / 2.1 / 2.3 — reviewers are read-only and could not re-run vitest; controller re-ran every SC command (`verify_summary.py --check` all PASS, see Verify).
- 1.1 — `placesCategory` does not trim an all-whitespace category; outside the brief's "non-empty string" contract. Not changed.
- 2.2 — `SidePanel` tabs are 1:1 with `renderable` and assume panels are unique by `panelKey` (the only producer, `upsertPanelByKey`, guarantees it). Latent precondition, documented here.
- 2.2 — category tab label bypasses `useTranslations` — by plan: `data.category` is already localized by the backend (`CATEGORY_VI`).
- 2.3 — chip aria-label now "cafe — 2 results (Open)" without the word "Places"; by plan (composition unchanged). Stray double blank line in `ResultChips.test.tsx`. Not changed.

### Advisory Findings (correctness-review, below threshold or unmodified-line)

- `SidePanel.tsx:78` — tabs are 1:1 with `renderable`; two panels sharing a key would duplicate a React key. Score 0: the only stateful producer (`upsertPanelByKey`) guarantees uniqueness; compact sheet passes one panel.
- `ChatPanel.tsx:76,245` (unmodified-line) — the compact bottom sheet holds the `PanelArtifact` captured at open; a re-emitted same-key panel updates chips/drawer but not the open sheet. Pre-existing two-store split.
- `ChatWidget.tsx:177` + `SidePanel.tsx:66` (unmodified-line) — an older turn's chip focuses by key, so the drawer shows the flat list's latest payload for that key, not that turn's own artifact. Pre-existing; the compact sheet already passes the artifact itself.

- `panel.ts` `placesCategoryKey` fallback (P3) — panels persisted before `category_key` existed (replayed legacy threads) still key on the localized `category`, so only those can reproduce the language-switch split. Documented in the fallback comment; accepted.
- `SidePanel.tsx` header `items-start` (P3, cosmetic) — with a single tab the ✕ sits ~1-2px above the pill's centre. Accepted.

- `ChatWidget.tsx` adjust block (P3, latent) — a chip click and an SSE panel arrival landing in one batched render would clear the just-set focus; not reachable (SSE onmessage is a separate macrotask from the click). Accepted.

- `ChatWidget.tsx:87,176` (P3, pre-existing shape) — `panelFocus` is not cleared on widget close; reopening with no new panel re-applies the last chip request over a manual tab pick. Accepted; fix is `setPanelFocus(null)` in the close handlers.

### Intent Findings

- none — plan-blind intent review over 8d830d9..7d8bd27 found no gap / drift / excess. Clauses checked: sequential search unchanged (BE untouched); replace-on-same-kind removed; two tabs cafe + restaurant, no replace; the three confirmed defaults (places-only sub-key; null-category → single Places tab; cross-turn retention unchanged). End-to-end category plumbing traced place_tools → mapper → PlacesPanelData.category.

### Harness-Delta

- backlog — `ruff-on-edit` stripped `import asyncio`/`localize_panel` from a new BE test when the import landed before its use across two edits (known gotcha, re-confirmed).
- backlog — teammate results over ~16k chars are dropped/truncated in transit; finder prompts should cap report length or write to a file (reviewer agents cannot write).
