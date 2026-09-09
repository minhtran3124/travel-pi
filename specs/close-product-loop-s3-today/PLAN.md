---
slug: close-product-loop-s3-today
status: proposed
owner: Minh Tran
created: 2026-09-09
---

# A Today tab for the trip in progress

## 1. Motivation

Slice 3 of `specs/close-product-loop/design.md`. One screen over four REST routes that already
exist and are already typed in `apps/web/src/lib/api/schema.d.ts`. Zero backend.

A traveller mid-trip opens the app to answer three questions: what is on today, what is the
weather like, and how do I get to the next thing. Today all three answers exist — the day plan
with its travel-time annotations, weather, air quality and point-to-point routing are live REST
routes and live agent tools — but on the web they are reachable only by asking the assistant.
The trip page has tabs for itinerary, budget, expenses, shortlist and map, all of which are
planning views. Nothing on it knows what day it is.

Intake: `specs/close-product-loop-s3-today/SUMMARY.md` (lane `normal`, confidence `high`).
Research: `specs/close-product-loop-s3-today/research-brief.md` (Standard, no external surface).

**The "unstarted item" question the design deferred to this slice is decided** in the intake
record: order by `sort_order`, and treat `pending | booked | constraint` as unstarted, excluding
only `optional`. `TripItem.start_time` is nullable, unvalidated free text with no timezone and
`get_day_plan` does not order by it, so a `start_time` selector would return nothing for most
trips and would hide fixed anchors such as a train departure — the item a traveller most needs
directions to.

**Both research follow-ups are decided here, and neither costs a backend change.** Weather and
air-quality prose arrives from the API in English. Rather than shipping English under `vi`
(the guide page's precedent) or duplicating the backend's Vietnamese map, the frontend localizes
from the **numbers the responses already carry**: `CurrentWeather.weather_code` is a WMO
interpretation code (`apps/api/app/schemas/weather.py:29`) and `AirQualityResponse.us_aqi` is the
US AQI integer (`apps/api/app/schemas/air_quality.py:34`). Both are published external standards,
so a frontend map keyed on them is not a copy of backend prose and cannot drift from it. The
API's own `description` / `category` strings remain the fallback when a code is unrecognised or
`us_aqi` is null.

## 2. Non-goals

- **No backend.** No new route, no schema change, no migration, no `lang` parameter on `/weather`.
  Adding one is a public-contract change that would push this slice to `high-risk`.
- **No progress state.** Nothing here marks an item done. `TripItemStatus` stays a planning state;
  a real `completed_at` is a schema change and belongs to its own spec if ever requested.
- **No offline support and no push.** Online only, per design §S3.
- **No second map component.** The directions card renders the existing chat `RoutePanel`, which
  already contains `TripMap` plus the mode chips, the recommended-leg summary and the Google Maps
  deep link. Do not rebuild any of that on bare `TripMap`.
- **No changes to the chat panels.** `RoutePanel`, `WeatherPanel` and `AirQualityPanel` keep their
  current props and behaviour. This slice only *consumes* `RoutePanel`.
- **No forecast, no hourly, no `weather_score`.** The design asks for current conditions only.
- No `.ics`, no recap, no share link — those are S4, S5 and S6.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|---|---|---|---|
| SC-1 | The trip-window and next-unstarted rules are correct across every date anchor, not one pinned "today" | `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/components/trips/today/todaySelectors.test.ts` | exit 0 |
| SC-2 | A `constraint` item can be the next unstarted item and an `optional` item never is | `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test -t "next unstarted" src/components/trips/today/todaySelectors.test.ts` | exit 0 |
| SC-3 | The four Today hooks call the right routes with the right keys and stay disabled without their inputs | `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/lib/query/today.test.ts` | exit 0 |
| SC-4 | Weather renders localized conditions from the WMO code and falls back to the API text on an unknown code | `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/components/trips/today/TodayWeatherCard.test.tsx` | exit 0 |
| SC-5 | Air quality renders a localized band derived from `us_aqi` and falls back to the API category when it is null | `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/components/trips/today/TodayAirQualityCard.test.tsx` | exit 0 |
| SC-6 | The directions card renders through `RoutePanel` when both items have a place, and renders nothing when either does not | `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/components/trips/today/TodayDirections.test.tsx` | exit 0 |
| SC-7 | The tab shows today's plan inside the trip window and the dated "not in progress" state outside it | `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/components/trips/today/TodayTab.test.tsx` | exit 0 |
| SC-8 | The chat Route panel behaves exactly as before this slice consumed it | `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/components/chat/panel/RoutePanel.test.tsx` | exit 0 |
| SC-9 | Every new string exists in both locales | `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/messages.parity.test.ts` | exit 0 |
| SC-10 | The frontend typechecks | `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm exec tsc --noEmit` | exit 0 |
| SC-11 | Frontend lint is clean | `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm exec eslint src` | exit 0 |

Every check names a file rather than a directory. The full frontend suite belongs to
`finishing-a-development-branch`, not to a task Verify.

## Global Constraints

- **Worktree.** All work happens in `.worktrees/feat/close-product-loop-s3-today`, branched from
  `main` at `a2380ae`. The main checkout belongs to another session — never touch it. `.venv` is a
  symlink to the main checkout's.
- **Node 24.** Every frontend command needs
  `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH"`; the nvm default is 18 and pnpm 11 requires
  Node ≥22.13.
- **Zero backend.** If a task believes it needs a backend change, it is BLOCKED — report it rather
  than making it. That is the one condition that escalates this slice.
- **Copy the sibling, do not invent.** `apps/web/src/lib/query/guide.ts` is the exact shape for the
  hook module: `unwrap(client.GET(...))`, a `qk` factory per route, an `enabled` guard on the
  input. `apps/web/src/components/trips/map/MapTab.tsx` is the exact shape for the tab: a client
  component with its own translations and its own spinner / error / empty ladder inside a `Card`.
- **No `new Date()` inside a tested unit.** Every selector takes its "now" as a parameter so tests
  can sweep anchors. `docs/solutions/harness/verify-against-invented-rule.md` is why: a single
  pinned "today" proves nothing.
- **Browser-local calendar date, not UTC.** Use the codebase's existing local-date helper
  (`tripVisuals.todayUTC`), never `new Date().toISOString().slice(0, 10)` — that is wrong for
  UTC+7 before 07:00 local, which is exactly the traveller this tab serves.
- **i18n.** Every new string lands in `messages/en.json` and `messages/vi.json` in the same edit.
  Never call `t.has`. Wave 1 adds the complete `Today` namespace up front so no later task edits a
  catalog and the waves stay conflict-free.
- **Degrade, never break.** `trip.city` is nullable, `TripItem.place_id` is nullable, and
  `us_aqi` / `pm2_5` are nullable. Every one of those is an empty state, not an error.
- Never use `max-w-md`; the spacing scale shadows the container scale in Tailwind v4. Use
  `max-w-[28rem]`.
- **Never run the whole suite in a task Verify.**

## 4. Tasks

### Task 1.1 — Pure Today selectors (wave 1)

- **Files:** apps/web/src/components/trips/today/todaySelectors.ts, apps/web/src/components/trips/today/todaySelectors.test.ts
- **Action:** Write the slice's three date/ordering rules as pure functions, each taking its
  "now" as an argument. `todayIso(now: Date): string` returns the browser-local calendar date
  (reuse the existing local-date helper in `tripVisuals`; do not reimplement it and do not use
  `toISOString`). `isWithinTrip(todayIso, startDate, endDate)` is inclusive at both ends and
  returns `false` when `startDate` is null; a null `endDate` means the trip is open-ended and only
  the start bound applies. `nextUnstarted(items)` takes the day plan's items already in
  `sort_order` and returns `{ previous, next }` — `next` is the first item whose `status` is
  `pending`, `booked` or `constraint`, `previous` is the item immediately before it in the list or
  `null`, and the whole result is `null` when no such item exists. Test-first, and sweep the
  anchors: before the trip, the first day, mid-trip, the last day, after the trip, a trip with
  only a `start_date`, an all-`optional` day, a day whose first item is a `constraint`, and an
  empty day.
- **Verify:** `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/components/trips/today/todaySelectors.test.ts`
- **Done:** Every anchor above is a passing case; no function reads the clock internally.
- **Criteria:** SC-1, SC-2
- **Interfaces:** Consumes the DayPlanItem and TripDetail types already generated in the frontend's OpenAPI schema module. Produces `todaySelectors.ts` exporting `todayIso`, `isWithinTrip` and `nextUnstarted`.

### Task 1.2 — The Today query hooks (wave 1)

- **Files:** apps/web/src/lib/query/today.ts, apps/web/src/lib/query/today.test.ts, apps/web/src/lib/api/keys.ts
- **Action:** Add four read-only hooks mirroring `lib/query/guide.ts` exactly: `useDayPlan(tripId, date)` over `GET /trips/{trip_id}/day-plan`, `useWeather(city)` over `GET /weather`, `useAirQuality(city)` over `GET /air-quality`, and `useRoute(fromPlaceId, toPlaceId)` over `GET /places/route`. Each uses `unwrap(client.GET(...))`, a new `qk` factory in `keys.ts` (`dayPlan`, `weather`, `airQuality`, `placesRoute`), and an `enabled` guard that is false whenever any input is empty or null. Re-export the four response types. Do not run `pnpm gen:api` — all four routes are already in `schema.d.ts`. Test that each hook is disabled without its input and that each calls its route with the expected query params.
- **Verify:** `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/lib/query/today.test.ts`
- **Done:** Four hooks and four key factories exist; each is disabled without its input.
- **Criteria:** SC-3
- **Interfaces:** Consumes the existing openapi-fetch client and the generated schema module, both already in the repo. Produces `lib/query/today.ts` and `lib/api/keys.ts` carrying four new qk factories.

### Task 1.3 — The complete Today message namespace (wave 1)

- **Files:** apps/web/messages/en.json, apps/web/messages/vi.json
- **Action:** Add one `Today` namespace to **both** catalogs, complete, so no later task touches a
  catalog. It holds: the tab label; the "trip not in progress" state with a dates placeholder and
  a variant for a trip with no dates set; the "nothing planned for today" state; the "this trip
  has no destination set" state used when `trip.city` is null; card titles for the plan, weather,
  air quality and directions; field labels for temperature, feels-like, humidity, wind, AQI and
  PM2.5; a "directions unavailable" note for when either item lacks a place; and two localized
  code maps — `Today.weather.wmo.<code>` covering the WMO interpretation codes Open-Meteo returns,
  and `Today.air.band.<good|moderate|unhealthySensitive|unhealthy|veryUnhealthy|hazardous>` for the
  US AQI bands. Write real Vietnamese, not English placeholders. Add no key that no other task in
  this plan consumes.
- **Verify:** `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/messages.parity.test.ts`
- **Done:** Both catalogs carry an identical `Today` key set and the parity test passes.
- **Criteria:** SC-9
- **Interfaces:** Consumes nothing. Produces `apps/web/messages/en.json` and `apps/web/messages/vi.json`, each carrying the complete Today namespace that tasks 2.1, 2.2, 2.3 and 3.1 read.

### Task 2.1 — Today weather card (wave 2)

- **Files:** apps/web/src/components/trips/today/TodayWeatherCard.tsx, apps/web/src/components/trips/today/TodayWeatherCard.test.tsx
- **Action:** A presentational card taking `WeatherResponse["current"] | undefined` and rendering
  temperature, feels-like, humidity and wind from the fields the response already carries. Render
  the condition by looking `weather_code` up in `Today.weather.wmo`, and fall back to the
  response's own `description` string when the code has no entry — never render an empty
  condition. Do not port the backend's emoji or advice mapping; do not add a BE call. Cover the
  fallback path in a test with a code the map does not contain.
- **Verify:** `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/components/trips/today/TodayWeatherCard.test.tsx`
- **Done:** A known code renders the localized string; an unknown code renders the API's own text.
- **Criteria:** SC-4
- **Interfaces:** Consumes `lib/query/today.ts` for the WeatherResponse type and `apps/web/messages/en.json` for the Today.weather strings. Produces `TodayWeatherCard.tsx`.

### Task 2.2 — Today air-quality card (wave 2)

- **Files:** apps/web/src/components/trips/today/TodayAirQualityCard.tsx, apps/web/src/components/trips/today/TodayAirQualityCard.test.tsx
- **Action:** A presentational card taking `AirQualityResponse | undefined`. Derive the band from
  the `us_aqi` integer using the published US AQI breakpoints (0–50 good, 51–100 moderate,
  101–150 unhealthy for sensitive groups, 151–200 unhealthy, 201–300 very unhealthy, 301+
  hazardous) and render `Today.air.band.<band>`. When `us_aqi` is null, render the response's own
  `category` string verbatim and omit the numeric reading. Show PM2.5 only when it is non-null. Do
  not port the backend's advice or pollutant-label mapping. Test each breakpoint boundary and the
  null case.
- **Verify:** `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/components/trips/today/TodayAirQualityCard.test.tsx`
- **Done:** Every band boundary maps to the right localized string; a null `us_aqi` falls back to the API category and hides the number.
- **Criteria:** SC-5
- **Interfaces:** Consumes `lib/query/today.ts` for the AirQualityResponse type and `apps/web/messages/en.json` for the Today.air strings. Produces `TodayAirQualityCard.tsx`.

### Task 2.3 — Directions to the next unstarted item (wave 2)

- **Files:** apps/web/src/components/trips/today/TodayDirections.tsx, apps/web/src/components/trips/today/TodayDirections.test.tsx
- **Action:** A component taking `{ previous, next }` from `nextUnstarted`. When either is null or
  either lacks a `place_id`, render the `Today.directions.unavailable` note and make no request —
  a hand-typed itinerary has no place IDs and this is the common case, not an error. Otherwise
  call `useRoute` and adapt the `RouteResponse` into the `data` prop the existing chat
  `RoutePanel` already takes, deriving the Google Maps deep link the same way
  `apps/api/app/streaming/panels/route.py` does. Render `RoutePanel` inside a height-bounded
  `Card`. Change nothing about `RoutePanel` itself — its props, its tests and its lazy maplibre
  import stay exactly as they are.
- **Verify:** `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/components/trips/today/TodayDirections.test.tsx src/components/chat/panel/RoutePanel.test.tsx`
- **Done:** Two placed items render a route through `RoutePanel`; a missing place renders the note and fires no request; `RoutePanel`'s own tests still pass untouched.
- **Criteria:** SC-6, SC-8
- **Interfaces:** Consumes `todaySelectors.ts` for nextUnstarted, `lib/query/today.ts` for the useRoute hook, `apps/web/messages/en.json` for the Today.directions strings, and the chat Route panel component that already exists. Produces `TodayDirections.tsx`.

### Task 3.1 — The Today tab on the trip page (wave 3)

- **Files:** apps/web/src/components/trips/today/TodayTab.tsx, apps/web/src/components/trips/today/TodayTab.test.tsx, apps/web/src/app/trips/[tripId]/page.tsx
- **Action:** Add `TodayTab({ tripId })` following the tab contract in
  `components/trips/map/MapTab.tsx`: a client component with its own translations and its own
  spinner / error / empty ladder inside a `Card`. It reads the trip, computes `todayIso` and
  `isWithinTrip`, and outside the window renders the "trip not in progress" state carrying the
  trip's dates (or the no-dates variant). Inside the window it fetches today's day plan and
  renders the ordered items with the `travel_to_next_minutes` the backend already annotates, then
  `TodayWeatherCard` and `TodayAirQualityCard` for `trip.city` — or the no-destination state when
  `city` is null — and `TodayDirections` for `nextUnstarted(items)`. Register it in the `Tab[]`
  list on the trip page. That list holds six tabs and this makes seven; the tablist already
  carries `overflow-x-auto` with `shrink-0` buttons, so the page cannot widen, but whether seven
  labels read well at 390px is a browser question — leave it to UAT and say in your report that it
  is unmeasured.
- **Verify:** `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/components/trips/today/TodayTab.test.tsx src/messages.parity.test.ts`
- **Done:** The trip page shows a Today tab; inside the trip window it renders the plan, weather, air and directions, and outside it renders the dated not-in-progress state.
- **Criteria:** SC-7, SC-9
- **Interfaces:** Consumes `todaySelectors.ts`, `lib/query/today.ts`, `apps/web/messages/en.json`, `TodayWeatherCard.tsx`, `TodayAirQualityCard.tsx` and `TodayDirections.tsx`. Produces `TodayTab.tsx` and `apps/web/src/app/trips/[tripId]/page.tsx` carrying one new tab entry.

## 5. Risks

- **The directions card will usually be absent on a real trip.** `GET /places/route` needs a
  `place_id` on both items and `TripItem.place_id` is nullable, so a hand-typed itinerary produces
  nothing. Task 2.3 makes that a first-class empty state rather than a failure, but it is the most
  likely UAT surprise — S2's map tab hit the same "a fresh trip has no data" wall. Seed a trip with
  catalog places before UAT.
- **`trip.city` is nullable**, so weather and air quality have their own empty state. No backend
  work; just do not assume the field.
- **Time-dependent tests are the classic false green here.** Selectors take `now` as a parameter
  precisely so a single pinned anchor cannot pass for proof.
- **Shared-file blast radius.** `app/trips/[tripId]/page.tsx` and both message catalogs are edited
  by every slice of this umbrella. Only task 1.3 touches the catalogs and only task 3.1 touches the
  page, so no two same-wave tasks overlap. This branch must merge before S4 starts.
- **Escalation trigger.** Any belief that a backend change is needed. Nothing found in research
  requires one; if implementation disagrees, stop and report rather than widening the slice.

## 6. Status Log

- 2026-09-09 — plan written; intake `normal`/`high`, research Standard with no external surface.
  Both research follow-ups decided in §1 without a backend change.
