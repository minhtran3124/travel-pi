---
slug: web-trip-planner
status: active
owner: Minh Tran
created: 2026-06-26
initiative: monorepo-fe (Phase 1)
---

# Phase 1 Frontend Implementation Plan — Trip Planner + Agent Co-pilot

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans (or subagent-driven-development) to implement this plan task-by-task.

**Goal:** Build the Phase 1 Next.js frontend in `apps/web` — a personal trip-planning dashboard (trips, itinerary, budget/expenses, saved places + shortlist, bookings view) plus a Kith-style streaming agent co-pilot — against the existing FastAPI backend, consumed as-is.

**Architecture:** App Router routes are thin shells; `lib/api` is the only BE-aware layer (an `openapi-fetch` client typed from the committed `schema.d.ts`, with middleware injecting `user_id` + conditional `Idempotency-Key`); `lib/query` owns all server-state via TanStack Query v5; `lib/identity` is the swappable local-pseudo-identity seam; `components/ui` is pure presentation built from the "Sunset Departures Board" `@theme` tokens; `components/chat` is a self-contained co-pilot consuming only `/agent/*`.

**Tech Stack:** Next.js 16.2.9 (App Router) · React 19.2.4 · TypeScript 5 · Tailwind v4 (CSS-first `@theme`) · TanStack Query 5.101 · openapi-typescript 7.13 + openapi-fetch 0.17 · Vitest + RTL + MSW · Playwright (one smoke).

**Inputs:** `specs/web-trip-planner/design.md` (approved) · `specs/web-trip-planner/research-brief.md` (exact BE schemas, SSE framing, `@theme` block, lib versions). **Read the research brief's "Local Findings" for exact request/response field names — this plan references them rather than duplicating.**

## Conventions for every task

- **Node:** all `pnpm` verify commands assume Node 24 on PATH:
  `export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH"`. The BE venv is the repo-root `.venv` (apps/api/Makefile `VENV=../../.venv`).
- **Run BE when a verify needs live data:** `cd apps/api && ../../.venv/bin/uvicorn app.main:app --port 8000`.
- **Path alias:** `@/* → apps/web/src/*` (tsconfig already set).
- **Decisions locked:** SSE streams **direct-to-origin** via `NEXT_PUBLIC_API_URL`; JSON via the `/api/be/*` proxy. `Idempotency-Key` only on `POST /trips` + `POST /trips/{id}/items`. `schema.d.ts` is committed.

---

## File Structure

```
apps/web/
  .env.example                         # NEXT_PUBLIC_API_URL
  package.json                         # + deps, gen:api/test scripts
  src/
    app/
      globals.css                      # @theme tokens (Wave 2)
      layout.tsx                       # Providers + AppShell + ChatWidget mount (Wave 3)
      page.tsx                         # redirect → /trips (Wave 3)
      error.tsx, not-found.tsx         # boundaries (Wave 3)
      trips/page.tsx                   # list + create (Wave 4)
      trips/[tripId]/page.tsx          # planner shell + tabs (Wave 4)
      places/page.tsx                  # saved + browse (Wave 4)
      bookings/page.tsx                # ledger (Wave 4)
    lib/
      api/{schema.d.ts, client.ts, keys.ts}   # typed client (Wave 1/2)
      query/{provider.tsx, trips.ts, items.ts, budget.ts, expenses.ts, places.ts, shortlist.ts, bookings.ts}
      identity/{provider.tsx, useUserId.ts}
      stream/parseSSE.ts               # bespoke SSE parser (Wave 6)
    components/
      ui/{Button,Card,Pill,Modal,EmptyState,Field,Spinner,Tabs}.tsx
      app-shell/AppShell.tsx
      trips/{TripCard,NewTripModal,TripHeader, itinerary/*, budget/*, expenses/*, shortlist/*}
      places/{SavedPlaceCard, BrowseDrawer}
      bookings/{BookingTable, BookingDetailModal}
      chat/{ChatWidget,ChatLauncher,ChatPanel,MessageList,QuickReplies,useAgentStream.ts}
  tests/ (or src co-located *.test.tsx)
  playwright/trip-smoke.spec.ts
```

---

## Chunk 1: Foundation + core libraries (Waves 1–3)

### Task 1.1 — Dependencies, type generation, env, test harness

> Creates the Vitest harness HERE (Wave 1) so every Wave 2–6 TDD `<verify>` (`pnpm test`)
> has jsdom + jest-dom + the `@/` alias + MSW available. Task 3.3 only consolidates/CI.

```xml
<task id="1.1" wave="1">
  <files>apps/web/package.json, apps/web/.env.example, apps/web/src/lib/api/schema.d.ts, apps/web/vitest.config.ts, apps/web/src/test/setup.ts, apps/web/src/test/msw.ts, pnpm-lock.yaml</files>
  <action>Add deps to apps/web: runtime `@tanstack/react-query@^5.101`, `openapi-fetch@^0.17`; dev `openapi-typescript@^7.13`, `vitest`, `@testing-library/react`, `@testing-library/jest-dom`, `@vitejs/plugin-react`, `jsdom`, `msw`, `@playwright/test`. Add scripts: `"gen:api": "openapi-typescript http://localhost:8000/openapi.json -o ./src/lib/api/schema.d.ts"`, `"test": "vitest run --passWithNoTests"`, `"test:watch": "vitest"`, `"e2e": "playwright test"`. Add `apps/web/.env.example` with `NEXT_PUBLIC_API_URL=http://localhost:8000`. Create the test harness: `vitest.config.ts` (jsdom env, `@vitejs/plugin-react`, `setupFiles: ['./src/test/setup.ts']`, resolve alias `@ → ./src` mirroring tsconfig), `src/test/setup.ts` (import `@testing-library/jest-dom`; start/reset/stop the MSW server around tests), `src/test/msw.ts` (`setupServer()` exporting `server` + a base handler set; modules add handlers per-test). Start the BE and run `pnpm gen:api` to produce the committed `schema.d.ts`. Approve sharp/native build scripts via pnpm-workspace allowBuilds if prompted.</action>
  <verify>(cd apps/api && ../../.venv/bin/uvicorn app.main:app --port 8000) & BE=$!; for i in $(seq 1 30); do curl -sf localhost:8000/openapi.json >/dev/null && break; sleep 1; done; cd apps/web && export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm install && pnpm gen:api && test -s src/lib/api/schema.d.ts && grep -q '/trips' src/lib/api/schema.d.ts && pnpm test; R=$?; kill $BE 2>/dev/null; exit $R</verify>
  <done>schema.d.ts exists, non-empty, contains /trips; deps + scripts present; `pnpm test` runs green (passWithNoTests) proving the harness is wired.</done>
</task>
```

### Task 1.2 — Typed BE client (`lib/api`)

```xml
<task id="1.2" wave="2">
  <files>apps/web/src/lib/api/client.ts, apps/web/src/lib/api/keys.ts</files>
  <action>Create `client.ts`: `createClient<paths>({ baseUrl: "/api/be" })` from openapi-fetch + schema.d.ts. Add `client.use({ onRequest })` middleware that injects header `X-User-Id` (from identity — read lazily via a getter to avoid SSR coupling; default to a module-held value set by IdentityProvider) and, for `POST /trips` and `POST /trips/{tripId}/items` only, an `Idempotency-Key` = crypto.randomUUID(). NOTE the BE reads `user_id` in the agent body, not a header — the header is the FE's own ownership marker; agent calls pass user_id in the body (Wave 6). Export a `streamBaseUrl()` returning `process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"` for direct-to-origin SSE. Create `keys.ts`: typed TanStack queryKey factories (trips, trip(id), items(id), budget(id), expenses(id,filters), savedPlaces(filters), shortlist(id), bookings, manifest).</action>
  <verify>cd apps/web && export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm exec tsc --noEmit -p tsconfig.json</verify>
  <done>Client + keys typecheck against schema.d.ts; middleware attaches user header + conditional idempotency key.</done>
</task>
```

### Task 1.3 — Local pseudo-identity (`lib/identity`)

```xml
<task id="1.3" wave="2">
  <files>apps/web/src/lib/identity/provider.tsx, apps/web/src/lib/identity/useUserId.ts, apps/web/src/lib/identity/provider.test.tsx</files>
  <action>`provider.tsx` ("use client"): on mount read `localStorage["travel.userId"]`; if absent generate `crypto.randomUUID()` and persist. Expose via React context. Also push the value into the lib/api module-level getter so `client.ts` middleware can read it without importing React. `useUserId()` returns the id (and a stable `null` during the first SSR/hydration tick). Write a test (TDD): mount provider, assert a UUID is created and persisted, and re-mount reuses the same id (mock localStorage).</action>
  <verify>cd apps/web && export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm test -- identity</verify>
  <done>Identity test passes; id is stable across remounts; value reaches the api client.</done>
</task>
```

### Task 1.4 — Design system: `@theme` tokens + UI primitives

```xml
<task id="1.4" wave="2">
  <files>apps/web/src/app/globals.css, apps/web/src/components/ui/Button.tsx, Card.tsx, Pill.tsx, Modal.tsx, EmptyState.tsx, Field.tsx, Spinner.tsx, Tabs.tsx, apps/web/src/components/ui/Button.test.tsx</files>
  <action>Replace globals.css placeholder @theme with the full "Sunset Departures Board" block from research-brief.md §Area 5 (coral brand, surfaces, ink/muted, closed status spectrum, topic palette incl `--color-lime`, Inter/Menlo fonts, radii, spacing, shadows; the @layer base focus ring; tp-pop keyframes + prefers-reduced-motion). Set body bg `--color-void`, text `--color-ink`. Build the UI primitives per DESIGN.md vocabulary: Button (variant primary=coral-deep/white | ghost; 34px; coral focus ring), Card (panel bg, md radius, resting shadow, lift on hover), Pill (status + topic variants — color paired with text, AA via color-mix), Modal (blurred dark scrim, tp-pop entrance, Esc/backdrop close, reduced-motion safe), EmptyState (emoji + bold headline + hint/action), Field (label + input/select, 34px, panel-raised), Spinner, Tabs (controlled). Numbers use `tabular-nums`. TDD: a Button test (renders label, variant class, calls onClick, has accessible role).</action>
  <verify>cd apps/web && export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm test -- ui && pnpm exec tsc --noEmit</verify>
  <done>UI tests pass; typechecks. (Tailwind/build errors caught at the Wave 2 barrier build.)</done>
</task>
```

### Task 1.5 — App shell, providers, routing skeleton

```xml
<task id="1.5" wave="3">
  <files>apps/web/src/lib/query/provider.tsx, apps/web/src/app/layout.tsx, apps/web/src/app/page.tsx, apps/web/src/components/app-shell/AppShell.tsx, apps/web/src/components/chat/ChatWidget.tsx, apps/web/src/app/error.tsx, apps/web/src/app/not-found.tsx</files>
  <action>`query/provider.tsx` ("use client"): `getQueryClient()` (isServer→new client; browser→singleton) + `<QueryClientProvider>`. `layout.tsx`: wrap children in IdentityProvider → QueryProvider → AppShell; mount `<ChatWidget />` (a temporary stub rendering the launcher FAB only — real widget in Task 2.7). Load **Inter** via `next/font/google` and set it as `--font-sans`; the mono is system Menlo/Consolas already declared in the `@theme` `--font-mono` (do NOT fetch Menlo via next/font — it is not a Google font). Update metadata. `AppShell.tsx`: top nav with links Trips / Places / Bookings (coral active state), main content slot. `page.tsx`: redirect("/trips"). `error.tsx` + `not-found.tsx`: friendly EmptyState-styled boundaries. Create the minimal `components/chat/ChatWidget.tsx` stub (FAB only) so layout compiles; Task 2.7 replaces it.</action>
  <verify>cd apps/web && export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm build && pnpm lint</verify>
  <done>App builds; `/` redirects to /trips; nav renders; providers mounted; FAB visible.</done>
</task>
```

---

## Chunk 2: Feature modules + chat widget (Waves 4–6)

> Wave 4 modules touch disjoint dirs and run in parallel. The trip-detail shell (4.1) imports tab components by stable path as **stubs**; Wave 5 fills those stub files (own dirs, disjoint). Bookings (4.2) and Places (4.3) are fully independent.

### Task 2.1 — Trips: list, create, detail shell

```xml
<task id="2.1" wave="4">
  <files>apps/web/src/lib/query/trips.ts, apps/web/src/app/trips/page.tsx, apps/web/src/app/trips/[tripId]/page.tsx, apps/web/src/components/trips/TripCard.tsx, NewTripModal.tsx, TripHeader.tsx, apps/web/src/components/trips/itinerary/ItineraryTab.tsx, budget/BudgetTab.tsx, expenses/ExpensesTab.tsx, shortlist/ShortlistTab.tsx, apps/web/src/lib/query/trips.test.tsx</files>
  <action>`trips.ts`: useTrips (GET /trips paginated), useTrip(id) (GET /trips/{id} → TripDetail with total_spent/remaining_budget/gaps/places), useCreateTrip (POST /trips, Idempotency-Key auto), useUpdateTrip (PUT), useDeleteTrip (DELETE) — invalidate `keys.trips`/`keys.trip(id)`. `/trips/page.tsx`: card grid + EmptyState + "New trip" → NewTripModal (title/city/dates/travelers/notes → useCreateTrip; plain pending state). `/trips/[tripId]/page.tsx`: TripHeader (dates, travelers, total_spent, remaining_budget, gaps as warning pills) + Tabs(Itinerary/Budget/Expenses/Shortlist) rendering the four tab components. Create the four tab components as **stubs** ("use client", render their own heading + a Spinner/placeholder) so the shell compiles. TDD: trips.test.tsx mocks `be()` via MSW, asserts useTrips returns parsed results and useCreateTrip sends an Idempotency-Key.</action>
  <verify>cd apps/web && export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm test -- trips && pnpm exec tsc --noEmit</verify>
  <done>Trips list renders cards/empty; create works; detail shell shows header + 4 tabs (stubs); hook tests pass.</done>
</task>
```

### Task 2.2 — Bookings module

```xml
<task id="2.2" wave="4">
  <files>apps/web/src/lib/query/bookings.ts, apps/web/src/app/bookings/page.tsx, apps/web/src/components/bookings/BookingTable.tsx, BookingDetailModal.tsx, apps/web/src/lib/query/bookings.test.tsx</files>
  <action>`bookings.ts`: useBookings (GET /bookings), useBooking(id) (GET /bookings/{id}), useCancelBooking (POST /bookings/{id}/cancel → invalidate). `/bookings/page.tsx`: FIDS-style BookingTable (type + status pills: confirmed=green, cancelled=red; flight vs hotel via hotel-blue tag), client-side search/filter/sort over the fetched list (no server params), row → BookingDetailModal showing the discriminated details + confirmation_code (mono) + cancel action. EmptyState when none. TDD: bookings.test.tsx asserts list parse + cancel invalidates.</action>
  <verify>cd apps/web && export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm test -- bookings && pnpm exec tsc --noEmit</verify>
  <done>Bookings ledger renders, filters client-side, detail modal + cancel work; tests pass.</done>
</task>
```

### Task 2.3 — Saved places + browse

```xml
<task id="2.3" wave="4">
  <files>apps/web/src/lib/query/places.ts, apps/web/src/app/places/page.tsx, apps/web/src/components/places/SavedPlaceCard.tsx, BrowseDrawer.tsx, apps/web/src/lib/query/places.test.tsx</files>
  <action>`places.ts`: useSavedPlaces (GET /places/saved + filters city/category/favorite/visited), useCreateSavedPlace (POST, handle 409 duplicate → surface hint), useDeleteSavedPlace, useSetFavorite/useSetVisited (POST flag SET, value:bool — optimistic toggle with rollback), usePlaceSearch (GET /places/search). `/places/page.tsx`: saved grid with favorite/visited filters + toggles, "Add place" form, and a BrowseDrawer running place search (city + category) to save a catalog place. 409 → friendly toast. **Define BrowseDrawer with a stable prop contract** — `onPick(place, source)` callback + an optional `mode` ("save" | "shortlist") — so Task 2.6 (shortlist) can import and reuse it without editing this file. TDD: optimistic favorite toggle rolls back on error (MSW 500).</action>
  <verify>cd apps/web && export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm test -- places && pnpm exec tsc --noEmit</verify>
  <done>Saved places render + filter; favorite/visited optimistic with rollback; browse drawer searches; 409 handled; tests pass.</done>
</task>
```

### Task 2.4 — Itinerary tab (fills stub)

```xml
<task id="2.4" wave="5">
  <files>apps/web/src/lib/query/items.ts, apps/web/src/components/trips/itinerary/ItineraryTab.tsx, ItemRow.tsx, ItemForm.tsx, apps/web/src/lib/query/items.test.tsx</files>
  <action>`items.ts`: useAddItem (POST /trips/{id}/items, Idempotency-Key auto; handle 409 over-budget → toast), useUpdateItem (PUT — FULL REPLACE: read current item, merge changes, send complete TripItemUpdate incl sort_order), useDeleteItem; useReorderItem helper that swaps sort_order of adjacent items via two full-replace PUTs (optimistic with rollback). Replace ItineraryTab stub: group items by `day`, render ItemRow (kind icon, status pill, title, start_time, notes) with up/down reorder + edit + delete, ItemForm modal (day, kind, status, title, place_id?, start_time?, notes?). TDD: items.test.tsx asserts reorder sends a COMPLETE body (all fields present) not a partial, and add attaches Idempotency-Key.</action>
  <verify>cd apps/web && export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm test -- items && pnpm exec tsc --noEmit</verify>
  <done>Itinerary groups by day; add/edit/delete/reorder work; reorder PUT is full-replace; 409 over-budget toast; tests pass.</done>
</task>
```

### Task 2.5 — Budget + Expenses tabs (fill stubs)

```xml
<task id="2.5" wave="5">
  <files>apps/web/src/lib/query/budget.ts, apps/web/src/lib/query/expenses.ts, apps/web/src/components/trips/budget/BudgetTab.tsx, apps/web/src/components/trips/expenses/ExpensesTab.tsx, ExpenseForm.tsx, apps/web/src/lib/query/expenses.test.tsx</files>
  <action>`budget.ts`: useBudget(id) (GET), useSetBudget(id) (POST full-replacement of caps → invalidate budget + trip). `expenses.ts`: useExpenses(id, filters), useExpenseSummary(id), useAddExpense, useUpdateExpense (PATCH partial), useDeleteExpense. BudgetTab: per-category caps (flights/hotels/activities/buffer) vs spent vs remaining, over_budget warning; edit caps form. ExpensesTab: ledger (amount in currency + amount_usd, category pill, occurred_at) with category/date filters, summary (by_category, by_currency, budget actuals), add/edit/delete (plain pending). Numbers tabular-nums. TDD: expenses summary renders by_category totals from a mocked response.</action>
  <verify>cd apps/web && export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm test -- expenses && pnpm exec tsc --noEmit</verify>
  <done>Budget caps vs spend render with over-budget state; expenses CRUD + summary + filters work; tests pass.</done>
</task>
```

### Task 2.6 — Shortlist tab (fills stub)

```xml
<task id="2.6" wave="5">
  <files>apps/web/src/lib/query/shortlist.ts, apps/web/src/components/trips/shortlist/ShortlistTab.tsx, apps/web/src/lib/query/shortlist.test.tsx</files>
  <action>`shortlist.ts`: useShortlist(id) (GET /trips/{id}/places → plain ShortlistEntry[], NOT paginated), useAddToShortlist (POST {place_id, source} — handle 409 already-shortlisted), useRemoveFromShortlist (DELETE by link_id). ShortlistTab: list shortlisted entries (place|saved), "Add from saved/catalog" reusing the BrowseDrawer (from 2.3) + saved places picker, remove by link_id. 409 → friendly notice. TDD: add-to-shortlist 409 surfaces a non-crashing message; remove uses link_id.</action>
  <verify>cd apps/web && export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm test -- shortlist && pnpm exec tsc --noEmit</verify>
  <done>Shortlist lists/add/remove work; 409 handled; remove targets link_id; tests pass.</done>
</task>
```

### Task 2.7 — Agent co-pilot chat widget (Kith-style)

```xml
<task id="2.7" wave="6">
  <files>apps/web/src/lib/stream/parseSSE.ts, apps/web/src/components/chat/ChatWidget.tsx, ChatLauncher.tsx, ChatPanel.tsx, MessageList.tsx, QuickReplies.tsx, useAgentStream.ts, apps/web/src/lib/query/agent.ts, apps/web/src/lib/stream/parseSSE.test.ts</files>
  <action>`parseSSE.ts`: a pure async generator/parser over a ReadableStream — accumulate, split on `\n\n`, keep trailing partial, for each `data: ` segment strip prefix; `[DONE]` → stop; tolerate a continuation line lacking `data:` (append to current event) per brief watch-out. `useAgentStream.ts`: POST to `${streamBaseUrl()}/agent/stream` (DIRECT-to-origin, not the proxy) with `{message,user_id,trip_id?,conversation_id?}`, AbortController, feed parseSSE into a growing assistant bubble; on error fall back to `POST /agent/chat` (via `agent.ts` useChat) and render reply; persist conversation_id in state. `agent.ts`: useManifest (GET /agent/manifest) for quick-reply chips. Replace the ChatWidget stub: ChatLauncher (lime FAB bottom-right, chat↔close), ChatPanel (dark surface + lime accent — `bg-void`/`text-ink`/`text-lime`; header with brand + expand/fullscreen + close; greeting; QuickReplies from manifest; MessageList; input+send). Accept `tripId` prop (passed from trip pages via context or a route-aware mount); on assistant turn completion call `queryClient.invalidateQueries` for trip/items/budget/expenses so the planner refreshes. Degraded amber notice if /agent unreachable. TDD: parseSSE.test.ts — multi-chunk stream assembles correct text, `[DONE]` stops, a newline-containing token doesn't crash.</action>
  <verify>cd apps/web && export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm test -- parseSSE && pnpm build</verify>
  <done>parseSSE tests pass; widget opens/streams (manual: with BE running, ask "what's the weather in Hanoi" → streamed reply); trip context passed; invalidation wired; amber fallback on failure.</done>
</task>
```

---

## Chunk 3: Tests, e2e smoke, CI (Wave 7)

### Task 3.1 — Full-suite gate + MSW handler completeness

> The Vitest harness already exists (Task 1.1). This task ensures the consolidated
> MSW handler set in `src/test/msw.ts` covers every endpoint the suite touches and
> that the FULL suite is green together (not just per-module slices).

```xml
<task id="3.1" wave="7">
  <files>apps/web/src/test/msw.ts</files>
  <action>Audit the MSW base handlers against all *.test.* files added in Waves 2–6; add any missing endpoint handlers so the full suite runs without per-file handler gaps. Do not change vitest.config.ts/setup.ts (created in 1.1) unless a real gap exists.</action>
  <verify>cd apps/web && export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm test</verify>
  <done>The full vitest suite (all component/hook/parser tests) runs green together.</done>
</task>
```

### Task 3.2 — Playwright e2e smoke

```xml
<task id="3.2" wave="7">
  <files>apps/web/playwright.config.ts, apps/web/playwright/trip-smoke.spec.ts</files>
  <action>Playwright config: baseURL http://localhost:3000, a webServer that runs `pnpm dev` (and assume BE started separately on :8000 via env). One spec: create a trip → open it → add an itinerary item → reload → assert the item persists. Mark e2e opt-in (not in the fast CI path). Document in the spec file header how to run (BE on :8000 + `pnpm e2e`).</action>
  <verify>(cd apps/api && ../../.venv/bin/uvicorn app.main:app --port 8000) & BE=$!; for i in $(seq 1 30); do curl -sf localhost:8000/openapi.json >/dev/null && break; sleep 1; done; cd apps/web && export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm exec playwright install chromium && pnpm e2e; R=$?; kill $BE 2>/dev/null; exit $R</verify>
  <done>The create-trip → add-item → persists smoke passes against a running BE. (First run downloads Chromium — exceeds 60s once; e2e is opt-in, not in fast CI.)</done>
</task>
```

### Task 3.3 — CI: run web unit tests

```xml
<task id="3.3" wave="7">
  <files>.github/workflows/ci.yml</files>
  <action>Add a `Test` step to the existing `web` job after Build (or before): `pnpm --filter @travel/web test`. Keep Playwright OUT of the fast CI path (opt-in/local for Phase 1). Leave the `api` job unchanged.</action>
  <verify>python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('valid')" && grep -q 'filter @travel/web test' .github/workflows/ci.yml</verify>
  <done>ci.yml is valid YAML and runs the web unit suite; api job untouched.</done>
</task>
```

---

## Waves summary

| Wave | Tasks | Parallelism | Barrier |
|------|-------|-------------|---------|
| 1 | 1.1 deps+gen:api | single | schema.d.ts committed before any typed code |
| 2 | 1.2 api client · 1.3 identity · 1.4 design system | 3 parallel (disjoint) | typecheck/build green |
| 3 | 1.5 app shell + providers | single | app builds, routes resolve |
| 4 | 2.1 trips+shell · 2.2 bookings · 2.3 places | 3 parallel (disjoint) | trip-detail stubs exist for Wave 5 |
| 5 | 2.4 itinerary · 2.5 budget+expenses · 2.6 shortlist | 3 parallel (fill own dirs) | all tabs functional |
| 6 | 2.7 chat widget | single | streams + invalidates |
| 7 | 3.1 full-suite gate · 3.2 e2e · 3.3 CI | 3.1→(3.2,3.3) | full suite green, CI valid |

> **Wave-barrier build:** per-task verifies use `pnpm exec tsc --noEmit` (fast); at the end of each
> wave run a full `pnpm --filter @travel/web build` once before advancing (catches Tailwind/RSC/route
> errors that typecheck alone misses). The Vitest harness exists from Task 1.1, so every TDD verify works.

## Risks (from research brief)

- **SSE proxy buffering** → mitigated by streaming direct-to-origin (`NEXT_PUBLIC_API_URL`); JSON via proxy. If origin CORS blocks, add a Next route handler passthrough with `runtime="nodejs"` + no-transform headers.
- **OpenAPI drift** → `schema.d.ts` committed; `pnpm gen:api` to refresh; a no-diff CI check is a Phase 2 add.
- **Full-replace PUT** → reorder/edit mutations must send the complete `TripItemUpdate` body (test enforces this in 2.4).
- **Single-user identity** → `IdentityProvider` is the only seam; all trips shown as "mine" until real auth.
- **SSE token-with-newline** → parser tolerates continuation lines (test in 2.7).

## Status Log

- 2026-06-26 — Plan drafted from approved design + xia2 brief.
- 2026-06-26 — **Wave 1 DONE**: Task 1.1 commit `94fa016` (deps + gen:api → committed schema.d.ts + vitest/MSW harness). Spec review ✅.
- 2026-06-26 — **Wave 2 DONE**: 1.2 `41df5fb` (typed client+keys), 1.4 `a370d69` (@theme + 8 ui primitives), 1.3 `ccb0e37` (identity). Review ✅ (10 tests pass, tsc clean, barrier build ✓).
- 2026-06-26 — **Wave 3 DONE**: 1.5 `98d4c74` (QueryProvider+IdentityProvider+AppShell+Inter+redirect+error/not-found+ChatWidget FAB stub). Barrier build ✓ — app builds & renders. **Foundation complete (Waves 1–3).** Remaining: Wave 4 (trips/bookings/places) · 5 (tabs) · 6 (chat widget) · 7 (tests/e2e/CI + correctness + intent).
- 2026-06-26 — Plan-review round 1: 2 blocking issues fixed (test harness moved to Task 1.1;
  `cd`-backgrounding bug in 1.1/3.2 verifies → subshell + readiness poll + `$!` PID). Advisories
  applied: per-task `tsc --noEmit` + wave-barrier builds; Inter-only via next/font; ChatWidget in
  1.5 `<files>`; BrowseDrawer prop contract for 2.6 reuse; 3.1 reframed to full-suite gate.
