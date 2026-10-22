# close-product-loop — Design (umbrella)

Status: **approved by user 2026-09-08**, amended 2026-09-08 after xia2 research (S1 items 1, 4, 9b, 9c) (spec-document-reviewer round 2 clean; brainstorming §1–§5 confirmed).
Lane: `high-risk` · Confidence: `medium` (see `SUMMARY.md`; E001/E002 decided in `ESCALATIONS.md`).
Source: `docs/reviews/2026-09-02-deep-review.md` §1 ("Parity chỉ đúng một chiều") and §4
("Đóng vòng plan → book → travel → recap").

## 1. Purpose

Close the product loop **plan → book → travel → recap** on the web app by giving every
user-relevant agent capability a screen. Today roughly a third of the agent's tools (flight/hotel
search and booking, weather/AQI, climate, tips, route, visa via REST) have no non-chat UI, and a
free user cannot book anything anywhere.

Success for the umbrella: after all six slices ship, every row in the parity table below has a
web screen, and a premium user can search → book → see the booking on the trip → travel with a
"today" view → export/share → recap, without opening the chat.

## 2. Constraints and non-goals

Decided (do not reopen inside a slice):

| Decision | Value | Where decided |
|---|---|---|
| Scope shape | Umbrella design + one spec folder per slice | ESCALATIONS E001 |
| Booking tier policy | Booking stays **premium**; free tier can search | ESCALATIONS E002 |
| Where the tier gate lives | **REST** (`POST /flights/book`, `POST /hotels/book`), not UI-only | brainstorming step 2 |
| Share link semantics | Public **read-only token** URL, no login required, owner toggles | brainstorming step 2 |
| "Today" screen | Online web page only; no offline cache, no push/notifications | brainstorming step 2 |
| Slice order | A: S1 booking UI → S2 guide+map → S3 today → S4 .ics → S5 recap → S6 share | brainstorming step 3 |

Non-goals for the whole umbrella:

- No new agent tools. UI→agent parity already holds; this work is the agent→UI direction.
- No real providers or payments. Flights/hotels stay simulated (hash-seeded inventory).
- No collaboration/editing on shared trips (read-only link only; membership model is a later spec).
- No PDF export (the review mentions ".ics / PDF"; the request says `.ics`).
- No changes to the chat side panels beyond extracting shared result-card components.
- No `[locale]` URL segments; i18n stays cookie-based next-intl (see `specs/review-c3-web-ssr-i18n`).

## 3. Current state (verified 2026-09-08)

Parity: agent tool → REST route → web screen. Registry: `apps/api/app/tools/registry.py`.

| Capability | REST (`apps/api/app/routers/`) | Web screen today | Slice |
|---|---|---|---|
| search_flights / book_flight | `GET /flights/search`, `POST /flights/book` | none (chat `FlightsPanel` only) | S1 |
| search_hotels / browse_hotels / book_hotel | `GET /hotels`, `/hotels/search`, `/hotels/availability`, `POST /hotels/book` | none (chat `HotelsPanel` only) | S1 |
| cancel_flight / cancel_hotel | `POST /bookings/{id}/cancel` | `/bookings` | — (exists) |
| visa (REST only) / get_local_tips / get_climate | `GET /visa`, `GET /tips`, `GET /destinations/climate?city=` | none | S2 |
| get_route / get_city_route | `GET /places/route`, `/cities/route` | none (chat `RoutePanel` only) | S2 (map), S3 (next stop) |
| get_weather / get_air_quality | `GET /weather`, `/air-quality` | none (chat panels only) | S3 |
| get_trip_summary / recall_past_trips | agent-only (memory store) | none | S5 |
| trips / itinerary / budget / expenses / places | `/trips/**`, `/places/**` | `/trips`, `/trips/[tripId]` tabs, `/places` | — (exists) |

Facts that shape the design:

- **No tier check on REST booking.** `book_flight` (`routers/flights.py:206`) and `book_hotel`
  (`routers/hotels.py:271`) take `CurrentUserDep` + optional `Idempotency-Key` and call
  `BookingService` directly. Premium gating exists only in the agent path: `routers/agent.py:253`
  reads `UserRepository.get_tier` (`repositories/user.py:24`) → `resolve_agent_context`
  (`agents/context.py:80–92`) → supervisor gate (`agents/supervisor.py:273–277`,
  `agents/constants.py` `PREMIUM_ONLY_SUBAGENTS={"booking"}`). The agent's book tools call
  `BookingService` directly (`tools/flight_tools.py:384`), not the REST route.
- **Booking has no `trip_id`.** `db/models/booking.py` links only one-way via
  `trip_items.booking_id`. `GET /bookings` filters by `status` and `type` only.
- **Trip dates are optional** (`db/models/trip.py` `start_date`/`end_date` nullable strings).
  `GET /trips/{id}/day-plan?date=` already returns a travel-time-annotated plan and 409s without
  a start date.
- **maplibre-gl 5.24** is a dependency, used only in `components/chat/panel/RoutePanel.tsx`.
- **No icalendar dependency, no `.ics` route, no share/token/public route.** Trip ownership is
  enforced in `TripService.__init__(user_id)` + `TripRepository.get_trip(trip_id, user_id)`.
- Web conventions: Next 16 App Router, client components, TanStack Query hooks in
  `apps/web/src/lib/query/*`, openapi-fetch client `lib/api/client.ts` (base `/api/be`, Supabase
  bearer, auto `Idempotency-Key`), next-intl messages `apps/web/messages/{en,vi}.json` with a
  parity test, hand-rolled `components/ui/*`, tokens in `/DESIGN.md` + `app/globals.css`.
- Trip detail (`app/trips/[tripId]/page.tsx`) is a `Tabs` page: itinerary, budget, expenses,
  shortlist. New trip-scoped screens are added as tabs there.

## 4. Umbrella architecture

**A. Screens over existing REST.** Each slice adds web pages/tabs and only the minimal BE needed
to make the screen honest (S1 tier gate + `trip_id`; S4 `.ics` route; S6 share token/route).
S2, S3, S5 add zero BE unless research finds a hard blocker, in which case that slice escalates.

**B. One spec folder per slice.** `specs/close-product-loop-s<N>-<name>/` created via
`/feature-intake`, citing this design as the approved design. Slices with a hard gate (S1, S4,
S6) are `high-risk` and run xia2 at Deep; S2/S3/S5 are expected `normal` (Standard). Slices are
**sequential**: every trip-scoped slice edits `app/trips/[tripId]/page.tsx` (new tab) and both
message files, and S1 also edits the app-shell nav, so parallel slices would conflict on merge.
A later slice branches from `main` after the previous slice has merged.

**C. Placement rule.** Trip-scoped screens are tabs on `/trips/[tripId]` (Bookings, Map, Today,
Recap). Screens not bound to a trip are top-level routes (`/flights`, `/hotels`,
`/guide/[city]`) and accept an optional `?tripId=` to pre-fill context and link results back.
The public share page is `/share/[token]` outside the authenticated shell.

**D. Frontend conventions are inherited, not redesigned.** New data access = one hook module per
resource in `lib/query/`; every new string in both `en.json` and `vi.json` (parity test
enforces); result cards for flights/hotels are extracted from the chat panels into
`components/{flights,hotels}/` and consumed by both the chat panel and the new page.

**E. Free-tier UX.** The FE does not learn the tier up front. The "Book" button is always
shown; a free user's click reaches `POST /…/book`, and the 403 with `code: "premium_required"`
opens the upgrade dialog. That dialog is the intended first touch of the premium offer, so S1 must
not pre-hide the button. No `/me` endpoint is added.

## 5. Slice specifications

### S1 · Flights & hotels UI, tier gate, booking ↔ trip (`high-risk`)

BE:

1. `require_premium` dependency in `app/core/auth.py`: resolves tier via
   `UserRepository.get_tier(auth_user.id)` (returns a plain `str`; coerce with `Tier(...)` and
   fall back to `Tier.FREE` on unknown values, exactly as `agents/context.py:82` does); raises 403 with body
   a `PremiumRequiredError(ForbiddenError)` for `Tier.FREE`. The error envelope has no `code`
   field and gains none: its existing `error` field carries the exception class name, which is
   the discriminator (`app/core/errors.py:29-39`). Applied to
   `POST /flights/book` and `POST /hotels/book` only. Agent booking path unchanged (already
   gated by the supervisor; the tool calls the service, not the route).
2. `bookings.trip_id` nullable **plain indexed string column** (the codebase uses no real FK
   constraints; `trip_items.trip_id` is the precedent, `db/models/trip.py:48`), Alembic migration
   (additive, no backfill).
   `FlightBookingRequest` / `HotelBookingRequest` gain optional `trip_id`; `BookingService`
   verifies the trip belongs to `user_id` (404 `trip_not_found` otherwise) before creating.
   `Booking` schema exposes `trip_id`. Idempotent replay ignores `trip_id` differences (the
   original booking wins), consistent with existing replay semantics.
3. `GET /bookings?trip_id=` filter (owner-scoped as today).
4. `TripBudget` (`schemas/trip.py:310`) gains `booked_total: float` = sum of non-cancelled
   bookings carrying this `trip_id`, each counted once. This deliberately differs from
   `total_spent`, which sums per itinerary item and therefore ignores a booking no item
   references and double-counts one that two items reference
   (`services/trip_service.py:394-412`). Existing budget logic is not changed. The Budget tab
   labels them distinctly: `total_spent` = "counted in the itinerary", `booked_total` =
   "booked for this trip". Bookings carry their own `currency` column
   (`db/models/booking.py:18`, copied from the inventory row); research checks whether any
   seeded inventory is non-USD. If it is, `booked_total` is reported per currency and this
   design is amended, never silently converted.

FE:

5. `/flights`: search form (origin, destination, departure date, optional return date,
   passengers) → results list (extracted `FlightResultCard`) → "Book" opens a dialog (passenger
   name, phone, optional trip select) → success state links to `/bookings` and to the trip's
   Bookings tab. `?tripId=` pre-selects the trip.
6. `/hotels`: city, check-in, check-out, rooms/adults/children → results (extracted
   `HotelResultCard`, uses `/hotels/availability`) → book dialog (guest name, phone, trip) →
   same success state.
7. Trip detail gains a **Bookings** tab: `GET /bookings?trip_id=` list with cancel (reuses the
   `/bookings` row component) and a "Book a flight / hotel" link carrying `?tripId=`.
8. Budget tab shows `booked_total` beside the cap.
9. Nav: "Flights" and "Hotels" entries in the app shell.

9b. FE `throwOn403(response, error, PremiumRequiredError)` in `src/lib/api/errors.ts`, mirroring
   the existing `throwOn409`; the book hooks read `response` instead of bare `unwrap()`, as
   `useCreateSavedPlace` already does.
9c. Add `POST /flights/book` and `POST /hotels/book` to `IDEMPOTENT_POST_PATHS`
   (`src/lib/api/client.ts:10-13`). Without this a double-click double-books, because the BE
   replay only triggers when the header is sent.

Error behaviour: 403 `PremiumRequiredError` → upgrade dialog; 404 trip → inline error, keep form;
409 no availability / flight sold out → inline, results refresh; network → existing toast.

### S2 · Guide pages and trip map (`normal` expected)

- `/guide/[city]`: three sections from `GET /visa`, `GET /tips`, `GET /destinations/climate?city=`,
  with the visa disclaimer rendered verbatim from the API. Entry points: trip header
  (destination city) and `/places`.
- Trip detail **Map** tab: maplibre map with markers for trip places (`/trips/{id}/places`) and
  itinerary items that have a `place_id`, coloured by day; click → item summary. Map component
  is extracted from `RoutePanel` into `components/map/`. No routing lines in S2.

### S3 · Today (`normal` expected)

- Trip detail **Today** tab, shown only when `start_date ≤ today ≤ end_date` (otherwise a
  "trip not in progress" empty state with the dates). Content: `GET /trips/{id}/day-plan?date=today`
  ordered items with travel-time annotations, `GET /weather` + `GET /air-quality` for the
  destination, and for the next unstarted item with a place: `GET /places/route` from the
  previous item. "Unstarted" = item `status` in `pending` or `booked` (not `optional`, not
  `constraint`), first by `sort_order`. Online only.
  Open at S3 intake: `TripItemStatus` is a *planning* state, not a progress state, so excluding
  `constraint` hides fixed anchors (a train departure) — the item a traveller most needs
  directions to. S3 decides between including `constraint` and "first item whose `start_time` is
  later than now".

### S4 · Export .ics (`high-risk`: public contract)

- `GET /trips/{id}/export.ics` (owner-only; `text/calendar`; `Content-Disposition` attachment).
  One VEVENT per itinerary item with a resolvable date (trip `start_date` + day offset; all-day
  unless `start_time` set); bookings linked to the trip (S1 `trip_id`) become VEVENTs with
  departure/check-in times. 409 `trip_has_no_dates` when `start_date` is null. Dependency:
  `icalendar` (pinned in `requirements.txt`). FE: "Export .ics" button on the trip header.

### S5 · Recap (`normal` expected)

- Trip detail **Recap** tab, shown when `end_date < today`: budget vs `expenses/summary` vs
  `booked_total`, itinerary completion (item `status`), and "trips like this" from
  `recall_past_trips`. Research decides whether recall is reachable over REST without a new
  endpoint; if a small `GET /trips/{id}/recap` aggregate is needed, that makes S5 `high-risk`
  (public contract) and is declared at its intake.

### S6 · Share link (`high-risk`: authorization + migration + public contract)

- Table `trip_shares` (`trip_id`, `token` unique random 32+ chars, `enabled`, `created_at`).
  Owner routes: `POST /trips/{id}/share` (create or return existing), `DELETE /trips/{id}/share`
  (disable). Public route `GET /share/{token}` (no auth) returning a read-only trip view
  (trip, itinerary, places; **no** bookings, expenses, budget, or owner identity), 404 when
  missing or disabled. FE: share toggle + copy-link in the trip header; `/share/[token]` page
  outside the auth shell, `noindex`.

## 6. Testing strategy

Every slice ships its own tests; the umbrella sets the floor:

- **BE (pytest, SQLite + Docker Postgres):** one test module per new/changed route under
  `apps/api/tests/api/<domain>/`. S1 must cover free→403 `premium_required`, premium→201,
  `trip_id` of another user's trip→404, idempotent replay unchanged, `GET /bookings?trip_id=`,
  `booked_total` excludes cancelled bookings **and bookings on another user's trip**, migration
  on a legacy DB. S4/S6 cover 404/409 and
  the public route's field allow-list.
- **Agent regression:** S1 asserts the agent booking path still works for premium and is still
  refused for free (existing supervisor tests), proving the REST gate did not double-gate.
- **FE (vitest):** hook + page tests per new page/tab; `messages.parity.test.ts` stays green.
- **E2E (Playwright, not in CI):** S1 adds a premium search→book→Bookings-tab smoke to
  `playwright/`; later slices add one smoke each. Fixing CI e2e is out of scope (deep-review
  item, separate spec).

## 7. Risks and open points carried to research (xia2)

- S1: whether any seeded flight/hotel inventory is non-USD (drives `booked_total`); whether `HotelResultCard` can be extracted
  without breaking `HotelsPanel` tests; how `FlightsPanel` maps API results (reuse mapping).
- S3: timezone for "today" (use the destination city's tz already plumbed for the agent's date
  resolution, see `specs/flight-search-date-context`).
- S4: `icalendar` version and Python 3.12/3.14 compatibility (Docker vs local).
- S6: token entropy, rate limiting of the public route (existing DB-backed limiter,
  `app/core/rate_limit.py`), and whether the public route must be excluded from the MCP surface.
