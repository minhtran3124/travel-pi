---
type: Feature
title: Trip research UI
description: The web client for trip research. Covers the Research tab on the trip page (locked, empty, running and finished states, origin prompt, revise and run-again), the typed research client and the SSE parser and hook for the progress stream, the plan view built from proposal.json with apply-to-trip, and the chat's research watch, done card and derived research-plan side panel.
tags: [frontend, research, nextjs, sse, react-query, side-panel, trips]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-25T03:45:43.723Z
sources:
  - id: openwiki-source-3c0ffd4ada8943a7635c0106
    resource: repo://apps/web/src/app/trips/%5BtripId%5D/page.tsx
  - id: openwiki-source-ca25c537a8f26748ded05f77
    resource: repo://apps/web/src/components/chat/panel/ResearchPlanPanel.tsx
  - id: openwiki-source-333c55401231af0692dddd31
    resource: repo://apps/web/src/components/chat/useResearchWatch.ts
  - id: openwiki-source-52a4d74971cdf303017ad1e7
    resource: repo://apps/web/src/components/map/TripMap.tsx
  - id: openwiki-source-c6d7e72b23feee8f3aac05b4
    resource: repo://apps/web/src/components/trips/research/proposal.ts
  - id: openwiki-source-18307e7332b9d883d90e7070
    resource: repo://apps/web/src/components/trips/research/ResearchPlan.tsx
  - id: openwiki-source-d69ac1d5ebb717388e6db903
    resource: repo://apps/web/src/components/trips/research/ResearchTab.tsx
  - id: openwiki-source-da684ce1a249d4ff8932ab85
    resource: repo://apps/web/src/components/trips/research/useResearchStream.ts
  - id: openwiki-source-6b794936beb1a815a2f10a5e
    resource: repo://apps/web/src/lib/api/research.ts
  - id: openwiki-source-f4d6fcd5134ba07be72e46c7
    resource: repo://apps/web/src/lib/features.ts
generated: { by: "claude-code", at: "2026-09-25T03:45:43.723Z" }
---

# Trip research UI

The web app shows trip research in two places. The **Research tab** on `/trips/{id}` is where research is started, watched, revised and applied. The **chat widget** follows a run launched from the chat and shows the finished plan in its side drawer. Both read the premium, JWT-authenticated `/agent/...research...` routes described in [Trip-research deep agent](../agent/trip-research-deep-agent.md).

## Feature flag

`researchEnabled()` (`src/lib/features.ts`) is true unless `NEXT_PUBLIC_RESEARCH_ENABLED` is exactly `"false"`. It mirrors the API's `RESEARCH_ENABLED` kill switch, which unmounts the research routes when off. The two should be set together, or the tab's Start button would only get a 404. With the flag off, the trip page drops the Research tab and the chat widget never starts its research watch. The trip page also accepts `?tab=<id>` to open a tab directly (the chat's done card links to `?tab=research`), and it falls back to the itinerary tab for an unknown or disabled tab id (see [Trips, bookings and catalog pages](trips-bookings-and-catalog-pages.md)).

## Typed client and stream

`src/lib/api/research.ts` is a **hand-typed** client, not generated from the OpenAPI schema. Its types mirror the backend's `ResearchStatusResponse` field for field. Each call attaches `authHeader()` and goes through the `/api/be` proxy: `startResearch` (with `language` and `origin`), `reviseResearch`, `getLatestResearch`, `getResearch`, `getResearchFile` and `putResearchFile`. There is no list endpoint, so `getResearchFiles` reads the file index from the status response. A failed response throws `Error("<path>: <status>")`, and the tab parses the status code from that message.

The progress stream is the one exception to the proxy. `useResearchStream(runId)` fetches `${streamBaseUrl()}/agent/research/{runId}/stream` **directly from the origin**, because the buffering proxy would stall the stream. It sends the Supabase token and aborts on unmount or when `runId` changes. `src/lib/stream/research.ts` is a network-free parser for the eight `research_*` events, using the same framing as `parseSSE.ts`. It copies that framing logic rather than importing it, so the chat parser stays untouched. The hook reduces the events into todos, per-subagent and per-tool status, the files seen so far, the last grader evaluation, and a terminal `done` or `error` status.

## The Research tab

`ResearchTab` (`src/components/trips/research/ResearchTab.tsx`) chooses what to show from the latest-run query and any run started in this session:

- **403 → locked** (not premium): an upgrade empty state.
- **404, or no run yet → empty**: an origin input and a Start button. Start is disabled until an origin is typed, because flights need a departure point and it is never assumed. A start that fails (for example, a 404 while the router is unmounted) shows a calm notice instead of crashing the tab.
- **Running**: it subscribes to the stream while either this session started or revised a run, or the latest summary says `running`. A `ProgressStepper` shows subagent progress, files written and the latest grader verdict. A terminal stream event settles this view even though the cached summary still says `running`, and the tab then refetches the summary.
- **Finished**: the `ResearchPlan` view. A run that ended as `failed` or `interrupted`, or whose stream errored, stays readable, but Apply is hidden and a **Run again** button starts a revise with a canned resume instruction.
- A **Revise** box, with quick-instruction chips, is always available and posts the next turn on the same thread.

## The plan view and applying it

`ResearchPlan` builds structured sections from `/plan/proposal.json`, which `parseProposal` coerces so any list can be missing. Each id is resolved through the normal REST lookups (`GET /places/{id}`, `/flights/{id}`, `/hotels/{id}`, in `src/lib/query/research.ts`), and React Query caches each id so it is fetched once. A section without ids falls back to the matching dossier prose file. The full dossier stays reachable in a collapsed report, where each file can be opened and edited. The grader's `review` verdict decides whether a "needs review" hint appears.

`useApplyProposal(tripId)` holds the apply logic in one place, shared by the tab and the chat panel. It adds every itinerary stop the traveller has not excluded as a trip item (`kind: "place"`, `status: "pending"`, with the proposal's day, time and notes), then adds each shortlist id to the trip shortlist. Per-entry results are mirrored in a ref, so clicking Apply again skips entries already applied. A place that is already on the shortlist counts as applied, not as an error. Applying uses only existing trip endpoints; nothing about the proposal is written back to the dossier.

## In the chat

The chat widget runs `useResearchWatch` and builds a client-side `research_plan` panel from the latest completed run (see [Chat widget and streaming client](chat-and-streaming-client.md)):

- `ResearchDoneCard` is shown when a run this chat was following finishes. It renders the run's `summary.md` (already cleaned for the traveller by the server), the dossier sections the run wrote, a link to `?tab=research` and, in the docked layout, a **View plan** action that opens the drawer.
- `ResearchPlanPanel` is the drawer's copy of the plan, with Overview, By day and Flights & stays tabs. The By day tab plots each stop on `TripMap` with numbered badge markers (`TripMapMarker.badge`). It reuses the tab's cards and `useApplyProposal`, and disables Apply while `updating` is true, meaning a newer run is refreshing the plan. It brings its own `TripDetail` catalog slice next to `Panel`, because the reused cards translate under `TripDetail.research` (see [Internationalization and theming](i18n-and-theming.md)).

## Tests

Vitest covers each piece: `ResearchTab.test.tsx` (locked, empty, running and settled states, origin gating, run again), `ResearchPlan.test.tsx`, `ProgressStepper.test.tsx`, `useResearchStream.test.tsx`, `lib/stream/research.test.ts` (parser framing), `useResearchWatch.test.tsx` (only a run seen running raises `done`, silent stop on errors), `ResearchDoneCard.test.tsx`, `ResearchPlanPanel.test.tsx`, `ChatWidget.test.tsx` (plan derivation and auto-open), `lib/features.test.ts` and the trip page's `?tab=` handling in `app/trips/[tripId]/page.test.tsx`.
