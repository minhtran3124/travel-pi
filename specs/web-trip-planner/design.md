---
slug: web-trip-planner
status: proposed
owner: Minh Tran
created: 2026-06-26
initiative: monorepo-fe (Phase 1)
---

# Phase 1 Frontend — Trip Planner + Agent Co-pilot

## 1. Motivation

The monorepo (`monorepo-fe` Phase 0) relocated the FastAPI backend to `apps/api`
and scaffolded an empty Next.js app at `apps/web`. Phase 1 builds the first real
frontend: a **personal trip-planning dashboard** over the user's own data, plus a
**floating agent co-pilot** styled like the Kith Hotel chat widget.

The backend is large (~70 JSON endpoints) and already ships a server-rendered
`/dashboard/*` for browse/search. So Phase 1 deliberately does **not** rebuild the
browse surface; it targets the stateful, mutable, user-owned core the static
dashboard does poorly: trips, itinerary, budget/expenses, saved places, bookings —
with an in-app AI assistant.

Bar: **product-MVP foundation** — solid architecture and extensible patterns,
balanced polish and correctness, built to grow across later phases.

## 2. Non-goals (Phase 1)

- No full discovery/search parity (flights/hotels/places search+filter) — only a
  **minimal place browse** sufficient to shortlist/save onto a trip.
- No booking **creation** flow (search → book). Bookings are **view + cancel** only.
- No drag-and-drop reordering — reorder via up/down controls (DnD is Phase 2 polish).
- No real authentication — a **local pseudo-identity** stands in (see §6).
- No backend changes. The BE contract is consumed as-is.
- No `packages/sdk` yet — the typed client lives in `apps/web` (may graduate later).

## 3. Success criteria

- A user can create a trip, build a day-by-day itinerary (add/edit/reorder/delete
  items), set budget caps, log expenses, shortlist saved/catalog places, and view +
  cancel bookings — all persisting to the BE.
- The agent co-pilot opens from a bottom-right launcher, streams replies, and when
  open on a trip page carries that `trip_id`; agent-driven mutations refresh the
  planner live.
- FE↔BE calls are type-checked against the BE's OpenAPI schema.
- `pnpm --filter @travel/web lint` and `build` pass in CI; component + hook tests
  pass; one Playwright smoke (create trip → add item → persists) passes.

## 4. Stack & architecture

**Stack:** Next.js 16 (App Router) · TypeScript · Tailwind v4 · TanStack Query ·
`openapi-typescript` (generated BE types) · Vitest + RTL + MSW · Playwright (smoke).

```
apps/web/src/
  app/                       # App Router — routes are thin shells/orchestrators
    layout.tsx               # Providers (QueryClient, Identity) + AppShell + ChatWidget
    page.tsx                 # → redirect to /trips
    trips/page.tsx           # Trips list + "New trip"
    trips/[tripId]/page.tsx  # Planner (tabbed: Itinerary/Budget/Expenses/Shortlist)
    places/page.tsx          # Saved places + Browse drawer
    bookings/page.tsx        # Booking ledger + cancel
    error.tsx, not-found.tsx # root boundaries
  lib/
    api/                     # generated schema.d.ts + be() typed fetch wrapper
    query/                   # TanStack Query hooks per resource (+ queryKeys)
    identity/                # IdentityProvider, useUserId (localStorage)
  components/
    ui/                      # design-system primitives (Button, Card, Pill, Modal, Empty…)
    chat/                    # self-contained Kith-style co-pilot widget
    trips/ places/ bookings/ # composite, route-specific components
```

**Layer boundaries (the isolation contract):**
- **Routes** (`app/**`) orchestrate layout + compose components; no direct fetch.
- **`lib/query`** owns all server-state: fetching, caching, mutation, invalidation.
  It is the only consumer of `lib/api`.
- **`lib/api`** is the only place that knows BE paths/types. Exposes `be(path, opts)`
  returning typed data; attaches the proxy base (`/api/be/*`) and `user_id`.
- **`components/ui`** is pure presentation (no data, no BE knowledge).
- **`components/chat`** is fully self-contained — consumes only `/agent/*` + a
  `trip_id` prop + a `queryClient.invalidateQueries` callback.

## 5. Routes & flows

### /trips — list + create
Card grid of the user's trips (`GET /trips`). "New trip" opens a modal →
`POST /trips` (title, city, start/end dates, travelers, notes) with an
`Idempotency-Key`. Empty state: friendly emoji + "Plan your first trip" action.

### /trips/[tripId] — the planner (tabs)
Header: title, dates, travelers, `total_spent`, `remaining_budget`, gap warnings
(`GET /trips/{id}` → TripDetail). Tabs:
- **Itinerary** — items grouped by day (`day` field). Add (`POST /items`), edit
  (`PUT`), delete (`DELETE`), reorder via up/down. `PUT /trips/{id}/items/{itemId}`
  is a **full replace** (TripItemUpdate ⊇ TripItemCreate, which includes
  `sort_order`), so the reorder mutation must send the **complete item body** with the
  new `sort_order` — never a partial PUT. Item kinds: place/activity/meal/transport/
  note; status pills. 409 "over budget" → toast.
- **Budget** — per-category caps vs booked spend (`GET/POST /trips/{id}/budget`).
- **Expenses** — trip-scoped: `GET/POST /trips/{tripId}/expenses`,
  `GET /trips/{tripId}/expenses/summary`, `PATCH`/`DELETE` per expense. Filters by
  category/date. `lib/query` keys for expenses include `tripId`.
- **Shortlist** — places linked to the trip (`GET/POST/DELETE /trips/{id}/places`),
  from saved or catalog. 409 "already shortlisted" handled gracefully.

### /places — saved places + browse
My saved places (`GET /places/saved`) with favorite/visited filters and toggles
(idempotent POST flags), create (`POST /places/saved`, 409 on duplicate), soft
delete. A **Browse drawer** runs `GET /places/search` (minimal: city + category)
to save or shortlist a catalog place.

### /bookings — ledger
FIDS-style table (`GET /bookings`) with flight/hotel + status pills, row → detail
modal (`GET /bookings/{id}`), cancel (`POST /{id}/cancel`, idempotent). Note:
`GET /bookings` is a plain list — search/filter/sort in Phase 1 is **client-side**
over the fetched ledger (no server-side query params assumed).

### Chat widget — every page
Floating launcher → popup; passes `trip_id` on trip pages (see §7).

## 6. Identity (the auth seam)

`IdentityProvider` mounts in `layout.tsx`. On first load it reads `userId` from
`localStorage`; if absent, generates a UUID and stores it. `useUserId()` exposes it;
`be()` attaches it (as the agent `user_id` and a logical owner). Because the BE has
no auth and `GET /trips` returns all trips, Phase 1 treats all trips/bookings as the
single logical user's. This is the **one seam** to swap for real auth later — no
other layer knows how identity is derived.

## 7. Chat co-pilot widget (Kith-style)

Self-contained `components/chat/`:
- **Launcher**: circular FAB pinned bottom-right (chat icon ⇄ close ×).
- **Panel**: anchored bottom-right; header (brand, expand/fullscreen, close),
  assistant greeting, **quick-reply chips** sourced from `GET /agent/manifest`
  (tool/subagent names), scrollable message thread, input + send.
- **Streaming**: `POST /agent/stream` (Server-Sent Events) appended into a growing
  assistant bubble; falls back to `POST /agent/chat` if SSE errors.
- **Context**: receives `trip_id` when rendered on a trip page; included in the
  `ChatRequest`. `conversation_id` persisted in component state for continuity.
- **Live sync**: on agent turns that may mutate a trip, calls
  `queryClient.invalidateQueries` so the planner reflects changes.
- **Style**: distinct dark surface + lime accent (Kith look) — a deliberate overlay,
  decoupled from the warm-coral app chrome. Lime aligns with the design system's
  existing `best_time` topic hue (#a3e635), so it doesn't introduce a foreign color.
- **Degraded state**: amber "assistant unavailable" if `/agent/*` fails.

## 8. Design system

A small Tailwind v4 theme derived from `apps/api/DESIGN.md` ("Sunset Departures
Board"): coral brand voice (bright/deep/soft), void→panel→panel-raised surfaces,
hairlines, the closed status spectrum, the topic palette, Inter + Menlo, the radii/
spacing scale. `components/ui` implements the documented vocabulary: coral-deep
primary + ghost buttons (34px), cards, status/remark pills, modals over a blurred
scrim with `pop` entrance, friendly empty states, `tabular-nums` on compared
numbers, a coral focus ring on every focusable control, and a
`prefers-reduced-motion` alternative for every animation. Do/Don't rules from
DESIGN.md are honored (no cream backgrounds, no gradient text, no per-section
uppercase eyebrows, no decorative glassmorphism, color is functional).

## 9. Error handling & states

Every Query surface renders explicit **loading / empty / error** states. BE domain
errors map to friendly inline messages or toasts: 404 → not-found state, 409 →
contextual notice ("already shortlisted" / "over budget"), 502 → "live data
unavailable, retry". **Optimism is scoped to high-frequency interactions** —
itinerary reorder, favorite/visited toggles — with rollback on error; slower
create/update flows (new trip, add expense) use plain pending states to avoid
rollback complexity where it adds little UX value. A root
`error.tsx` boundary catches unexpected failures; `not-found.tsx` for bad ids. The
chat widget degrades independently (amber notice) without affecting the app.

## 10. Testing

- **Component/unit:** Vitest + React Testing Library for `components/ui` primitives
  and the chat message reducer/stream parser.
- **Query hooks:** tested against `be()` mocked with MSW — zero real network.
- **E2E smoke:** one Playwright flow — create trip → add itinerary item → reload →
  item persists — against a locally running BE.
- CI: the existing `web` job runs lint + build; unit/component tests added there.
  The Playwright smoke is opt-in/local for Phase 1 (kept out of the fast CI path).

## 11. Risks & open questions

- **OpenAPI generation cadence:** types are generated from a running BE's
  `/openapi.json` into a committed `schema.d.ts`; a `pnpm gen:api` script regenerates.
  Risk: drift if BE changes without regen — mitigated by committing the file and a CI
  check (Phase 2) that regen produces no diff.
- **SSE through the Next proxy:** `next.config` rewrites must not buffer the
  `/agent/stream` response. If buffering occurs, the widget calls the BE origin
  directly via `NEXT_PUBLIC_API_URL` instead of the proxy.
- **Single-user assumption:** all trips shown as "mine" until real auth exists; the
  identity seam contains the change.
- **Reorder semantics:** RESOLVED — `TripItemUpdate ⊇ TripItemCreate` includes
  `sort_order` (apps/api/app/schemas/trip.py), and PUT is a full replace, so reorder
  sends the complete item body with the new `sort_order` (see §5 Itinerary).

## 12. Phasing note

Phase 2+ candidates (out of scope here): full discovery/search, booking creation
(search→book), drag-and-drop itinerary, destination intel inline (weather/tips/
visa/climate/air-quality), `packages/sdk` extraction, real auth.
