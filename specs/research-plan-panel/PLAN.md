---
slug: research-plan-panel
status: shipped
owner: minhtran3124
created: 2026-09-22
---

# research-plan-panel — the finished trip plan as a chat side panel, with a day map

## 1. Motivation

The chat's side drawer shows weather / places / flights panels, but a finished deep-research
plan lives only in the trip's Research tab. The traveller should see the whole plan next to the
chat: overview, day by day on a map, flights and stays.

## 2. Scope

In (web only): panel kind `research_plan` with three tabs — Overview (summary, stats, budget,
Apply), By day (day chips → map with numbered stops + straight dashed line, timeline), Flights &
stays; the drawer gets the panel whenever the trip page has a completed research run, and opens
on it when a run completes or after a research chat turn; the done card gains "View plan".
Out: backend changes (panels are not persisted in chat history today — hydration sets
`panels: []` — so the panel is derived from the trip's latest completed run instead of being
attached to a message).

## Global Constraints

- No backend change; data from existing routes (research files/status, /places, /flights, /hotels, budget).
- Reuse `TripMap`, `trips/research` cards, `useProposal`, lookup hooks; no second copy of Apply logic.
- en + vi copy; no tool names or ids rendered.
- Panel identity is stable (`kind` + run id) so the derived panel never duplicates.
- The drawer never auto-opens on a plain page load; only on completion or after a research turn.
- Minimal comments; match surrounding style.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|---|---|---|---|
| SC-1 | `research_plan` panel renders 3 tabs; By day shows numbered stops for the chosen day and a map | `cd apps/web && pnpm vitest run src/components/chat/panel` | exit 0 |
| SC-2 | Chat drawer gains the plan tab for a completed run; opens on completion / research turn only | `cd apps/web && pnpm vitest run src/components/chat` | exit 0 |
| SC-3 | Typecheck + lint clean | `cd apps/web && pnpm exec tsc --noEmit -p .` | exit 0 |

## 4. Tasks

### Task 1.1 — Plan panel + drawer wiring (wave 1)

- **Files:** apps/web/src/components/chat/panel/ResearchPlanPanel.tsx, apps/web/src/components/chat/panel/ResearchPlanPanel.test.tsx, apps/web/src/components/chat/panel/registry.ts, apps/web/src/components/chat/ChatWidget.tsx, apps/web/src/components/chat/ChatWidget.test.tsx, apps/web/src/components/chat/useResearchWatch.ts, apps/web/src/components/chat/useResearchWatch.test.tsx, apps/web/src/components/chat/ResearchDoneCard.tsx, apps/web/src/components/chat/ResearchDoneCard.test.tsx, apps/web/src/components/trips/research/ResearchPlan.tsx, apps/web/src/components/map/TripMap.tsx, apps/web/src/lib/stream/panel.ts, apps/web/src/lib/query/research.ts, apps/web/messages/en.json, apps/web/messages/vi.json
- **Action:** Build the panel and wire it per §2.
- **Criteria:** SC-1, SC-2, SC-3
- **Interfaces:** Consumes `TripMap` in `apps/web/src/components/map/TripMap.tsx`; produces `ResearchPlanPanel.tsx`.
- **Verify:** `cd apps/web && pnpm vitest run src/components/chat`
- **Done:** tests pass, tsc + lint clean

## 6. Status Log

- 2026-09-22 — task 1.1 complete
