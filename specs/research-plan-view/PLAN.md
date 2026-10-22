---
slug: research-plan-view
status: shipped
owner: minhtran3124
created: 2026-09-22
---

# research-plan-view — the Research tab shows a plan, not a folder of files

## 1. Motivation

A finished run is shown as a file list + markdown viewer. The run already produces structured
data — `proposal.json` (itinerary with `place_id`s, flight `offer_id`s, `hotel_id`s,
`budget_estimate`), `summary.md`, the grader `review` — and every id resolves through existing
REST routes (`GET /places/{id}`, `/flights/{id}`, `/hotels/{id}`). The traveller should see a plan
they can picture and apply; the markdown becomes an optional detailed report. While running, the
progress shows raw tool chips (`search_flights ok`) and the grader's English explanation.

## 2. Scope

In (web only): plan header (summary, verdict, quick stats, Apply), section nav, day-by-day
itinerary with place cards, flight cards, hotel cards, budget bar vs trip cap, entry & season
prose, collapsible "detailed report" (reader-view files), revise box with quick chips, friendly
localized progress stepper. Out: BE changes, a batch lookup endpoint, localized file names beyond
the report's labels.

## Global Constraints

- No backend change; data comes from existing routes only.
- Reuse existing card components / design tokens (DESIGN.md) instead of new visual language.
- All copy en + vi via next-intl; no hard-coded strings; no tool names or ids rendered.
- Graceful fallback: a missing/empty proposal section or a failed lookup degrades to the report prose, never an error screen.
- Apply keeps today's semantics (existing ProposalPanel REST calls), per-stop opt-out allowed.
- Minimal comments; match surrounding style.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|---|---|---|---|
| SC-1 | Completed run renders header, itinerary, flights, stays, budget from proposal + lookups | `cd apps/web && pnpm vitest run src/components/trips/research` | exit 0 |
| SC-2 | Missing proposal / failed lookups fall back to report prose without crashing | `cd apps/web && pnpm vitest run src/components/trips/research` | exit 0 |
| SC-3 | Running state shows a localized step list, no tool names | `cd apps/web && pnpm vitest run src/components/trips/research` | exit 0 |
| SC-4 | Typecheck + lint clean | `cd apps/web && pnpm exec tsc --noEmit -p .` | exit 0 |

## 4. Tasks

### Task 1.1 — Plan view + progress stepper (wave 1)

- **Files:** apps/web/src/components/trips/research/*, apps/web/src/lib/query/research*.ts, apps/web/messages/en.json, apps/web/messages/vi.json
- **Action:** Build the plan view and stepper per §2; keep the report as a collapsible section.
- **Criteria:** SC-1, SC-2, SC-3, SC-4
- **Interfaces:** Consumes `getResearchFile` / `getLatestResearch` in `apps/web/src/lib/api/research.ts` and the places/flights/hotels/budget query hooks; produces `ResearchPlan.tsx`.
- **Verify:** `cd apps/web && pnpm vitest run src/components/trips/research`
- **Done:** tests pass, tsc + lint clean

## 6. Status Log

- 2026-09-22 — task 1.1 complete
