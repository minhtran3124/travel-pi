# research-plan-view — Summary

Lane: normal
Confidence: high
Reason: web-only view change in the Research tab (new components, i18n); no backend, contract or data change.
Flags: none
Affects: apps/web Research tab
Input-type: change request

### Intent

> 1 cái nữa cần suy nghĩ là đối với end user thì việc view research files kiểu ntn khá là bất tiện, hãy suy nghĩ tìm cách render thể hiện UI/UX giúp cho user dễ đọc, dễ hình dung hơn.

Decisions (AskUserQuestion): "Tóm tắt + chi tiết" (plan view on top, detailed report collapsed
below) and "Gộp luôn" (friendly progress stepper instead of raw tool chips).

## What changed

A finished run renders `ResearchPlan`: header (verdict, `summary.md` bullets, quick stats, Apply),
a section nav, day-by-day itinerary of place cards from `GET /places/{id}` with per-stop opt-out,
flight cards (`/flights/{id}`), hotel cards (`/hotels/{id}`), a budget bar vs the trip cap, entry &
season prose, and a collapsed "Detailed report" holding the reader-view files (inline edit kept).
Each section falls back to its markdown when the proposal has no ids or a lookup fails.
`ProposalPanel` folded into the plan (same Apply calls). While running, `ProgressStepper` shows
localized steps; a step is done once its dossier file is written (`research_file` events — the
stream never emits `research_subagent`), subagent events are a secondary signal, quality = rubric
event. Revise box gains quick chips. Built by a subagent; the main thread reworked the stepper
signal and added the section nav after screenshot review.

### Rationale

The run already yields structured data (proposal ids + catalog routes + existing card styles), so
the traveller gets pictures, times and prices instead of prose; the prose stays one click away.

### Alternatives considered

- A nicer document reader only — rejected by the user.
- Plan only, no report — rejected by the user: loses the "why" (trade-offs, weather notes).

### Deviations

- Rule 1 — stepper keyed on subagent events that the backend never emits; now keyed on written files.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| unit (web) | `cd apps/web && pnpm vitest run src/components/trips/research` | 0 | 18 passed: header/itinerary/flight/hotel/budget, nav anchors | SC-1 |
| unit (web) | `cd apps/web && pnpm vitest run src/components/trips/research` | 0 | failed place lookup → prose; empty proposal → prose | SC-2 |
| unit (web) | `cd apps/web && pnpm vitest run src/components/trips/research` | 0 | stepper localized, file-driven done/active, no tool names | SC-3 |
| typecheck | `cd apps/web && pnpm exec tsc --noEmit -p .` | 0 | lint 0 errors (1 pre-existing warning) | SC-4 |
| full web suite | `cd apps/web && pnpm vitest run` | 0 | 400 passed | |
| visual | Node 24 playwright-core screenshots of a temporary preview route (removed) fed the real Đà Nẵng dossier; lookups hit the real API | 0 | desktop, 390px mobile, dark | |

### Not auto-verified

- The budget bar against a real cap was not seen (the preview had no signed-in user; `/budget` 401 → the estimate-only fallback rendered).
- The stepper against a live stream — covered by unit tests on the event shapes only.
- Vietnamese locale in the screenshots (preview rendered en; vi copy covered by tests).

### Rollback

- `git revert <sha>`.

### Harness-Delta

- none
