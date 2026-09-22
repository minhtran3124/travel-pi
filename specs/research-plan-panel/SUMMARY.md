# research-plan-panel — Summary

Lane: normal
Confidence: high
Reason: web-only chat panel + drawer wiring; no backend, contract or data change.
Flags: none
Affects: apps/web chat widget + side panel, shared TripMap (additive optional marker badge)
Input-type: change request

### Intent

> tôi đang có idea là ngoài viêc hiện thị vd như ở link http://localhost:3000/trips/c26e4907-f068-4107-9780-e8edef0dc016?tab=research chúng ta sẽ render thêm UI bên cạnh kiểu như weather/search places/etc ... nhưng sẽ là full trip sau khi research, kế hoạch total, theo ngày, địa điểm, etc ... 1 cách dễ hiểu, dễ đọc vs ng

Decisions (AskUserQuestion): "3 tab + bản đồ"; "Tự mở + lưu lại".

## What changed

New chat side-panel kind `research_plan` (`ResearchPlanPanel.tsx`): Overview (verdict, summary,
stats, budget bar, Apply), By day (day chips → `TripMap` with numbered badge markers in time order
and a dashed line, numbered timeline), Flights & stays (cards). The panel is derived from the
trip's latest completed run (`useResearchWatch.completed`), so the drawer has a Plan tab on the trip
page — surviving reloads — and auto-opens on it when a run completes or after a research chat turn,
never on a plain load. The done card gains "View plan" (desktop). Apply logic and the budget bar
were extracted from `ResearchPlan.tsx` and shared. `TripMap` gains an optional `badge` per marker
(default pin unchanged). Built by a subagent; the main thread added numbered badges after
screenshot review.

### Rationale

"Lưu lại" through the backend would not have survived a reload: chat hydration sets
`panels: []` for every message, weather included. Deriving the panel from the trip's latest
completed run meets both asks (auto-open, still there after reload) with no backend change.

### Alternatives considered

- Backend attaches the panel to the bot reply (the chosen option's wording) — not done: panels are not persisted in history, so it would vanish on reload anyway.
- One scrolling page without a map — rejected by the user.

### Deviations

- Rule 2 — `TripMap` marker `badge` (numbered pins) added after review; additive, other callers unchanged.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| unit (web) | `cd apps/web && pnpm vitest run src/components/chat/panel` | 0 | tabs, time-ordered numbered badges, cards, fallbacks, vi labels | SC-1 |
| unit (web) | `cd apps/web && pnpm vitest run src/components/chat` | 0 | plan tab on completed run; auto-open on done / research turn, not on mount | SC-2 |
| typecheck | `cd apps/web && pnpm exec tsc --noEmit -p .` | 0 | lint 0 errors (1 pre-existing warning) | SC-3 |
| full web suite | `cd apps/web && pnpm vitest run` | 0 | 416 passed | |
| visual | Node 24 playwright-core screenshots of a temporary preview route (removed), real Đà Nẵng dossier, real lookups | 0 | 440px, light + dark, 3 tabs; numbered map pins | |

### Not auto-verified

- The drawer auto-open inside the live chat widget (needs a signed-in browser) — covered by ChatWidget unit tests only.
- Trip city/dates in the panel header (the preview had no signed-in user, so the trip query was not served).

### Rollback

- `git revert <sha>`.

### Harness-Delta

- none
