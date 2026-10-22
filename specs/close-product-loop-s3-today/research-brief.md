# Research Brief — close-product-loop S3 "Today" tab

Depth: **Standard** (intake lane `normal` → Standard per `.claude/rules/research-depth.md`).
No upgrade: no migration/schema work, no high-blast file, no new dependency, no auth/session change,
no shared runtime-config contract. Every Deep signal was checked and none fired.

---

## Bottom Line

| Field | Value |
|---|---|
| **Recommendation** | **Reuse** — one new query-hook module mirroring `lib/query/guide.ts`, one new tab mirroring `MapTab`, and the existing `RoutePanel` (via a pure adapter) for the directions card. Two small weather/AQI cards are the only genuinely new render code. |
| **Why this is the lightest credible path** | All four REST routes are already in the generated openapi types, and the tab/hook/i18n conventions the slice needs already exist and were exercised one slice ago (S2). |
| **Confidence** | 88% |
| **Next step** | `writing-plans` → a `PLAN.md` with a pure-selector task (unstarted-item + today-window logic, anchor-swept tests) before the render tasks. |

---

## Repo Snapshot

| Field | Detected |
|---|---|
| Repo type | pnpm + Turborepo monorepo — FastAPI `apps/api`, Next.js `apps/web` |
| Primary language + runtime | TypeScript 5 / Node 24 (FE); Python ≥3.10 (BE, untouched here) |
| Frameworks / platforms | Next 16.2.9 App Router (client components), React 19.2.4, TanStack Query ^5.101, openapi-fetch ^0.17, next-intl ^4.13, Tailwind v4, maplibre-gl ^5.24 |
| Relevant packages | `@tanstack/react-query`, `openapi-fetch`, `next-intl`, `maplibre-gl` (all already present) |
| Detectable versions | `apps/web/package.json`; `TECHSTACKS.md` |
| Important constraints | `CLAUDE.md` (Node 24 for FE work); design §2 "Today = online web page only, no offline cache, no push"; design §4B slices are sequential (this branch edits the shared tab host); SUMMARY.md fixes "unstarted" = `pending \| booked \| constraint`, ordered by `sort_order` |

---

## Feature Understanding and Assumptions

- **Requested feature:** a **Today** tab on `/trips/[tripId]`, visible only while
  `start_date ≤ today ≤ end_date`; otherwise a "trip not in progress" empty state showing the trip
  dates. Content: today's ordered day plan with travel-time annotations
  (`GET /trips/{id}/day-plan?date=`), current `GET /weather` + `GET /air-quality` for the
  destination, and `GET /places/route` from the previous item to the next unstarted item.
- **What success appears to mean:** a traveller mid-trip opens the trip, sees today's stops in
  order, the weather/air right now, and how to get from where they are to what's next — with zero
  backend change and both locales at parity.
- **Assumptions from the request:** the "unstarted" rule is settled (SUMMARY.md) and not reopened;
  the slice adds no BE; `Tabs.tsx` already tolerates a seventh tab.
- **Assumptions still needing confirmation:**
  1. English-only weather/AQI prose under the `vi` locale is acceptable (see Risks — the REST routes
     return English `description`/`category`; VI localization exists only on the SSE panel path).
  2. "Today" may be the *browser's* calendar date rather than the destination's (see finding 5).

---

## Evidence Ledger

| Label | Evidence |
|---|---|
| `Local` | All four routes are already in the generated types: `/places/route` (`schema.d.ts:735`), `/weather` (`:953`), `/air-quality` (`:1006`), `/trips/{trip_id}/day-plan` (`:1224`), with response models `RouteResponse`, `WeatherResponse`, `AirQualityResponse`, `DayPlanResponse`. **No `pnpm gen:api` run is needed.** |
| `Local` | The claimed `Tabs.tsx` overflow fix is **real and verified**: `apps/web/src/components/ui/Tabs.tsx` has `flex gap-md overflow-x-auto border-b …` on the `role="tablist"` container and `-mb-px shrink-0 …` on each button, with a comment recording the 390px measurement. A seventh tab is safe. |
| `Local` | `apps/web/src/app/trips/[tripId]/page.tsx` holds a flat `const tabs: Tab[]` of six entries + a `{activeTab === "x" ? <XTab tripId={tripId}/> : null}` ladder; `useState("itinerary")` only, no URL sync. S2 added Map by appending one `Tab` literal and one ladder line. |
| `Local` | `RoutePanel` is a **projection of `RouteResponse`**: `apps/api/app/streaming/panels/route.py:_gmaps_dir_url` + `RoutePanel.from_route_response` add only `gmaps_url` (a keyless Google-Maps deep link built from lat/lng) and rename `latitude/longitude` → `lat/lng`. So the FE `RoutePanel.tsx` is reachable from REST with a ~15-line pure adapter. |
| `Local` | `WeatherPanel` / `AirQualityPanel` are **panel-coupled**: their props (`WeatherPanelData`, `AirQualityPanelData` in `lib/stream/panel.ts`) require BE-computed `emoji`, `condition`, `band`, `advice`, and labelled `pollutants[]` that `WeatherResponse`/`AirQualityResponse` do not carry (`apps/api/app/streaming/panels/weather.py`, `air_quality.py`, 154 + 190 lines of mapping). |
| `Local` | `TripMap` (`components/map/TripMap.tsx`, created by S2) is genuinely shared/presentational: props `{markers, route?, className, ariaLabel}`, lazy `import("maplibre-gl")`, no fetching. `RoutePanel` already renders it. |
| `Local` | Root `app/layout.tsx:41` wraps the app in `NextIntlClientProvider` with the full catalog, so the `Panel` namespace `RoutePanel` uses is available outside the chat drawer (`PanelIntlProvider` exists only to override the locale with the BE-detected conversation language). |
| `Local` | FE "today" convention already exists twice: `tripVisuals.tsx:todayUTC()` (`Date.UTC(n.getFullYear(), n.getMonth(), n.getDate())` — the **browser's local calendar date** pinned to UTC midnight) feeding `tripStatus(t, start, end) → {phase: "now"\|"upcoming"\|"past"}`, and `ItineraryTab.tsx:todayDayNumber()` using the identical formula. `app/trips/page.tsx:21` disagrees (`new Date().toISOString().slice(0,10)` = the **UTC** date). |
| `Local` | REST has **no timezone plumbing**: `today_in_timezone` / `resolve_travel_date` (`apps/api/app/core/dates.py:262,282`) are used only by agent tools, and the tz itself comes from the client (`useAgentStream.ts:467` sends `Intl.DateTimeFormat().resolvedOptions().timeZone`; `routers/agent.py:215 _resolve_timezone`). `GET /trips/{id}/day-plan` takes an explicit `date` and knows nothing about zones. |
| `Local` | `TripService.get_day_plan` (`services/trip_service.py:603`) orders by `sort_order`, 409s when `start_date is None` **and** when `date < start_date`, and already annotates `travel_to_next_minutes/_mode` between consecutive items that both carry a geo-located `place_id` (routing failures are swallowed to `None`). |
| `Local` | `GET /weather` takes `city: string` (+ optional `days`), `GET /air-quality` takes `city: string` — **no coordinate form**. `TripDetail.city` is `string \| null`. `GET /places/route` takes `origin`/`destination` **place IDs**, and `TripItem.place_id` is `string \| null`. |
| `Local` | `messages.parity.test.ts` compares dot-delimited leaf-key sets both ways — every new key must land in `en.json` **and** `vi.json`, same shape (arrays are terminal). Namespaces are flat top-level (`Map`, `Guide`, `TripBookings` …). |
| `Local` | `docs/solutions/harness/verify-against-invented-rule.md`: time-dependent behaviour tested from a single pinned anchor is a tautology — sweep anchors, assert invariants. Directly applicable to the today-window and next-unstarted selectors. |
| `Upstream` | TanStack Query docs: `refetchInterval` polls on its own clock independent of `staleTime`; the project default is `staleTime: 30_000` (`lib/query/provider.tsx`). No polling is needed for an online-only tab — the existing default plus refetch-on-mount is the convention, and adding an interval would be new behaviour nothing asked for. |
| `Inference` | Because the tab only renders when `start_date ≤ today ≤ end_date`, the two 409 branches of `get_day_plan` (no start date; date before start date) are unreachable from the tab — but the hook should still surface an error state rather than assume that. |

---

## Local Findings

**Relevant files, modules, tests**

- Host: `apps/web/src/app/trips/[tripId]/page.tsx`; `apps/web/src/components/ui/Tabs.tsx`.
- Tab contract to copy: `apps/web/src/components/trips/map/MapTab.tsx` (+ `MapTab.test.tsx`) and
  `components/trips/expenses/ExpensesTab.tsx` — client component, own `useTranslations` namespace,
  `Spinner → EmptyState(error) → EmptyState(empty) → content` ladder inside a `Card`.
- **Hook module to mirror exactly: `apps/web/src/lib/query/guide.ts`.** It is the closest analogue —
  several independent read-only `GET`s with query params, `unwrap(client.GET(...))`, keys from
  `qk`, and an `enabled:` guard for the "we don't have the input yet" case. `lib/query/trips.ts` is
  the mutation-carrying shape and is not what this slice needs.
- Keys: `apps/web/src/lib/api/keys.ts` (`qk`), each key a `readonly` tuple factory.
- i18n: `apps/web/messages/{en,vi}.json` + `apps/web/src/messages.parity.test.ts`.
- Existing render code worth reading: `components/chat/panel/RoutePanel.tsx`,
  `WeatherPanel.tsx`, `AirQualityPanel.tsx`, `components/map/TripMap.tsx`.

**Existing abstractions / extension points**

- `Tab[]` + ladder on the trip page (S2's exact insertion point).
- `TripMap` — shared presentational map with an optional route line, already consumed by `RoutePanel`.
- `tripStatus()` / `tripDays()` in `components/trips/tripVisuals.tsx` — the trip-window vocabulary
  (`phase: "now" | "upcoming" | "past"`) already used by the trip cards and header.
- `unwrap` / `throwOn409` / `throwOn403` in `lib/api/{client,errors}.ts`.

**Conventions worth preserving**

- Every API date is naive `YYYY-MM-DD`; formatting is pinned to `timeZone: "UTC"` so the calendar day
  never shifts (`tripVisuals.fmt`, `ItineraryTab.dayDate`, `lib/datetime.toUtcDate`).
- One hook module per resource; no fetching inside components.
- New strings into both catalogs in the same edit; never `t.has`.
- `max-w-md` is forbidden (Tailwind v4 spacing shadows the container scale) — use `max-w-[28rem]`.

**What can likely be reused**

| Need | Reuse | Cost |
|---|---|---|
| Directions card | `RoutePanel` + a pure `routeResponseToPanel(RouteResponse)` adapter (`gmaps_url` = the two-line deep link from `panels/route.py`) | ~15 lines; needs a height-bounded wrapper because `RoutePanel` is `h-full flex-col` |
| Map inside it | `TripMap`, transitively via `RoutePanel` | 0 |
| Day-plan / weather / AQI / route fetching | `lib/query/guide.ts` shape | new `lib/query/today.ts` |
| Tab shell, empty/error states | `MapTab`, `Card`, `EmptyState`, `Spinner` | 0 |
| Trip-window classification | `tripStatus()` | 0 (or a local `isTodayWithin` sharing `todayUTC`'s formula) |

**What appears missing locally**

- No `lib/query/` module for weather, air quality, day plan, or place routes — the chat is the only
  consumer today and it gets them as SSE panel artifacts, not REST.
- No REST-fed weather/AQI presentational component. The two chat panels cannot be reused as-is.
- No shared "today" helper: the formula is copy-pasted in `tripVisuals.tsx` and `ItineraryTab.tsx`,
  and a third file (`app/trips/page.tsx`) uses a *different* one.

### Answers to the eight questions asked

1. **Response shapes / type coverage — covered, no codegen needed.**
   - `DayPlanResponse { trip_id, date, day, items?: DayPlanItem[], weather_score?: number|null }`;
     `DayPlanItem { item: TripItem, travel_to_next_minutes?: number|null, travel_to_next_mode?: string|null }`;
     `TripItem { id, trip_id, day, kind, status, title, sort_order, place_id?, booking_id?, start_time?, notes? }`;
     `TripItemStatus = "pending" | "booked" | "constraint" | "optional"`. Query param `date` (required),
     path `trip_id`. Responses 200/404/409/422.
   - `WeatherResponse { location: WeatherLocation{name,country?,latitude,longitude,timezone}, current: CurrentWeather{time,temperature_c,apparent_temperature_c,relative_humidity,wind_speed_kmh,weather_code,description}, daily: DailyForecast[], attribution }`. Query `city` (required), `days?`. 200/404/422/502.
   - `AirQualityResponse { location, time, us_aqi?, category, pm2_5?, pm10?, ozone?, nitrogen_dioxide?, sulphur_dioxide?, carbon_monoxide?, forecast: AirQualityDay[], attribution }`. Query `city`. 200/404/422/502.
   - `RouteResponse { origin: RouteEndpoint{kind,id,name,latitude,longitude}, destination, straight_line_km, recommended_mode: "walk"|"bike"|"car", legs: RouteLeg[], source: "openrouteservice"|"estimate", geometry?: number[][]|null, attribution }`. Query `origin`, `destination` (**place IDs**). 200/404/422/502.
2. **Hook conventions — mirror `apps/web/src/lib/query/guide.ts`.** New module `lib/query/today.ts`
   with `useDayPlan(tripId, date)`, `useWeather(city)`, `useAirQuality(city)`,
   `usePlaceRoute(origin, destination)` — each `useQuery({queryKey: qk.…, queryFn: () => unwrap(client.GET(…)), enabled: …})`,
   plus four `qk` factories. Types re-exported as `components["schemas"]["…"]`, as `guide.ts` does.
3. **How S2 added Map / what Today must do identically.** One `{ id: "map", label: t("tabs.map") }`
   entry appended to `tabs`, one ladder line `{activeTab === "map" ? <MapTab tripId={tripId}/> : null}`,
   one `tabs.map` key in both catalogs, and the tab itself under
   `components/trips/map/`. Today does exactly that with `id: "today"`. **Two deviations are forced:**
   the tab is conditional (only push the `Tab` when the trip window contains today — a hidden tab is
   better than a tab that always renders an empty state), and the design still requires the
   "trip not in progress" state, which belongs in the tab body when the tab *is* reachable. Simplest
   honest shape: always register the tab, let `TodayTab` render either the day or the
   not-in-progress state. *The `Tabs.tsx` overflow claim was verified in the file, not taken on trust.*
4. **Panel extractability.** `RoutePanel` — **adaptable and worth reusing**; it is a pure render over
   a shape that is a mechanical projection of `RouteResponse`. `WeatherPanel` / `AirQualityPanel` —
   **panel-coupled**; they need `emoji`, `condition`, `band`, `advice`, `pollutants[]` computed on the
   BE. **`TripMap` should not be used directly for the directions card**: `RoutePanel` already renders
   `TripMap` *plus* the mode chips, the recommended-leg summary and the keyless Google-Maps link, all
   of which the Today card wants. Reuse `RoutePanel`; `TripMap` comes along for free.
5. **Timezone / "today".** There is **no** tz plumbing on the REST path — `today_in_timezone` and the
   client-sent `timezone` exist only for the agent. The honest FE approach is the one already in the
   codebase: the **browser's local calendar date** (`Date.UTC(n.getFullYear(), n.getMonth(), n.getDate())`,
   `tripVisuals.todayUTC`), formatted `YYYY-MM-DD` for the `date` query param, and compared as a
   string against the naive `start_date`/`end_date`. Do **not** copy
   `app/trips/page.tsx:21`'s `toISOString().slice(0,10)` — that is the UTC date and is wrong for a
   traveller in UTC+7 before 07:00. Do **not** introduce a destination timezone: `WeatherResponse.location.timezone`
   only arrives *after* the weather call, so it cannot decide which day to fetch without a
   circular dependency, and using it would need a BE change to be honest for the day plan.
6. **Message parity.** `messages.parity.test.ts` fails if any leaf key path exists in one catalog and
   not the other, in either direction. New `Today` namespace keys must be added to both files in the
   same edit, with identical nesting. Placeholders/plurals are next-intl ICU, unchecked by the test.
7. **Weather / AQI inputs.** Both take a **city name string only** (no lat/lng form). The Today tab
   gets it from `TripDetail.city` — which is nullable. When it is null, the weather and air cards
   render their own empty state; do not guess from the trip title, and do not fall back to a place's
   coordinates (the routes cannot accept them).
8. **Risks that would force backend work** — see below. **None of the identified risks does**, so the
   slice stays `normal`.

---

## Upstream Findings

- **Repositories inspected:** this repo's own immediately-preceding slices are the load-bearing
  upstream here — S1 (`components/{flights,hotels}/*ResultCard` extracted out of two chat panels)
  and S2 (`components/map/TripMap.tsx` extracted out of `RoutePanel`, plus
  `specs/close-product-loop-s2-guide-and-map/PLAN.md`). Both prove the "lift a presentational piece
  out of a chat panel, keep the panel's tests green" move that this slice needs for `RoutePanel`.
- **Pattern already present upstream:** TanStack Query's documented split between `staleTime`
  (freshness) and `refetchInterval` (polling on its own clock).
- **Files worth modeling:** `lib/query/guide.ts`, `components/trips/map/MapTab.tsx`,
  `specs/close-product-loop-s2-guide-and-map/PLAN.md` §4 task shape.
- **How closely it matches:** exactly — same app, same slice family, one commit-series old.
- **Gaps / uncertainties:** none material. The external polling pattern is deliberately *not*
  adopted: design §2 fixes the tab as an online page, and the project default `staleTime: 30_000`
  with refetch-on-mount is the existing convention.

---

## Docs Findings

- none (local-only; **no external surface**) — the slice adds no dependency, upgrades none,
  integrates no external system, and relies on no version-specific API. The Open-Meteo and
  OpenRouteService calls behind `/weather`, `/air-quality` and `/places/route` are already-shipped
  backend integrations that this slice does not touch.
- One official page was read anyway while checking the polling question (TanStack Query "Polling"),
  and is listed under Source Pack for traceability; it changed nothing.

---

## Recommendation

- **Primary recommendation: reuse.**
  1. `apps/web/src/lib/query/today.ts` — four hooks mirroring `guide.ts`; four `qk` factories.
  2. `apps/web/src/components/trips/today/` — `TodayTab.tsx` mirroring `MapTab.tsx`, plus small
     presentational `TodayWeatherCard` / `TodayAirQualityCard` built directly from the REST fields,
     and a `TodayDirections` wrapper that adapts `RouteResponse` → `RoutePanelData` and renders the
     existing `RoutePanel` inside a height-bounded `Card`.
  3. A **pure selector module** (`todaySelectors.ts`) holding: `todayIso()` (browser-local calendar
     date), `isWithinTrip(todayIso, start, end)`, and
     `nextUnstarted(items) → { previous, next }` implementing the SUMMARY decision — first
     `DayPlanItem` in `sort_order` whose `item.status` is `pending | booked | constraint`, with the
     item immediately before it as the route origin, and `null` unless **both** carry a `place_id`.
     Every function takes its "now" as an argument so tests can sweep anchors.
  4. One `Tab` entry + one ladder line on the trip page; a `Today` namespace in both catalogs.
- **Why this is the lightest credible path:** every dependency, type, key factory, tab contract,
  empty/error ladder and map already exists and was exercised last slice; the only new render code is
  two small cards over fields the REST responses already return.
- **Why the next-best alternative lost:** *adapting the chat weather/AQI panels* would mean porting
  `panels/weather.py` + `panels/air_quality.py` (≈340 BE lines of WMO→emoji/condition and
  AQI→band/advice/pollutant-label mapping) into TypeScript — an adapter larger than the cards it
  feeds, and a second copy of a mapping that would then silently drift from the BE's. *Adding the
  enrichment to the REST responses instead* is a public-contract change that would push the slice to
  `high-risk` for a cosmetic gain. *Rebuilding the directions card on `TripMap` alone* was rejected
  the other way: it would re-write the mode chips, the recommended-leg summary and the Google-Maps
  deep link that `RoutePanel` already has.
- **What would change this recommendation:** if the user requires Vietnamese weather/air-quality
  prose in the Today tab, the choice reopens — either port the BE's `WEATHER_VI` map to the FE
  (duplication, but still no BE change and still `normal`) or add a language parameter to
  `/weather` (public contract → `high-risk`, escalate).

---

## Risks, Unknowns, and Follow-Up Questions

**Technical risks**

- **The directions card will often be absent.** `GET /places/route` needs two **place IDs**, and
  `TripItem.place_id` is nullable; a hand-typed itinerary has none. The card must degrade to nothing
  (or to the day plan's own `travel_to_next_minutes`, which the BE already computes) rather than
  showing a broken state. Not a blocker; it is the most likely UAT surprise — S2's map tab hit the
  same "fresh trip has no data" wall.
- **`trip.city` is nullable** → weather and air cards must have their own empty state. No BE work.
- **Locale gap.** Under `vi`, `WeatherResponse.current.description` and `AirQualityResponse.category`
  arrive in English; the VI translations live only on the SSE panel path
  (`panels/weather.py:WEATHER_VI`, localized by `streaming/panel_localizer.py`). S2's precedent is to
  render API text verbatim. Decide explicitly rather than by accident.
- **Time-dependent tests.** Per `docs/solutions/harness/verify-against-invented-rule.md`, a single
  pinned "today" proves nothing. Selectors must take `today` as a parameter and be swept over
  anchors: before the trip, first day, mid-trip, last day, after the trip, and a trip with only a
  `start_date`. No `new Date()` inside a tested unit.
- **Blast radius on a shared file.** `app/trips/[tripId]/page.tsx` and both message catalogs are the
  files every slice of this umbrella edits (design §4B). This branch must merge before S4 starts.
- **Nothing found that forces backend work**, so no escalation trigger fires. The two 409 branches of
  `get_day_plan` are unreachable behind the trip-window gate, `/weather` and `/air-quality` accept the
  city the trip already carries, and all four routes are already typed.

**Evidence gaps**

- Not measured: the trip page at 390px with **seven** tabs. The row scrolls within itself (verified in
  `Tabs.tsx`), so the page-widening bug S2 fixed cannot recur, but whether seven labels read well is a
  browser question for UAT.
- Not run: the FE suite, `tsc --noEmit`, or any browser session — this was a read-only research pass.
- Not checked: whether `weather_score` on `DayPlanResponse` is worth surfacing (the design does not
  ask for it).

**Version uncertainties**

- None. No dependency is added, upgraded, or pinned.

**Follow-up questions (max 2)**

1. Under the `vi` locale, is English weather/air-quality prose acceptable for now (matching the guide
   page's verbatim-API convention), or should the FE carry a Vietnamese description map?
2. Should the Today tab be hidden entirely outside the trip window, or always visible and rendering
   the "trip not in progress" state? The design specifies the empty state; hiding the tab would
   contradict it, so the plan assumes always-visible unless told otherwise.

---

## Source Pack

- **Local files read:**
  - `specs/close-product-loop/design.md`, `specs/close-product-loop-s3-today/SUMMARY.md`,
    `specs/close-product-loop-s2-guide-and-map/{PLAN.md,SUMMARY.md}`
  - `AGENTS.md`, `CLAUDE.md`, `TECHSTACKS.md`, `.claude/rules/research-depth.md`,
    `.claude/skills/xia2/SKILL.md`, `.claude/skills/xia2/references/research-brief-template.md`
  - `docs/solutions/INDEX.md`, `docs/solutions/critical-patterns.md`,
    `docs/solutions/harness/verify-against-invented-rule.md`
  - `apps/web/src/app/trips/[tripId]/page.tsx`, `apps/web/src/app/trips/page.tsx`,
    `apps/web/src/app/layout.tsx`
  - `apps/web/src/components/ui/Tabs.tsx`, `apps/web/src/components/trips/map/MapTab.tsx`,
    `apps/web/src/components/trips/tripVisuals.tsx`,
    `apps/web/src/components/trips/itinerary/ItineraryTab.tsx`,
    `apps/web/src/components/map/TripMap.tsx`,
    `apps/web/src/components/chat/panel/{RoutePanel,WeatherPanel,PanelIntlProvider}.tsx`
  - `apps/web/src/lib/query/{guide.ts,trips.ts,provider.tsx}`, `apps/web/src/lib/api/{keys.ts,schema.d.ts}`,
    `apps/web/src/lib/stream/panel.ts`, `apps/web/src/lib/datetime.ts`,
    `apps/web/src/messages.parity.test.ts`, `apps/web/messages/en.json`, `apps/web/package.json`
  - `apps/api/app/services/trip_service.py`, `apps/api/app/core/dates.py`,
    `apps/api/app/routers/agent.py`, `apps/api/app/streaming/panels/{route.py,weather.py}`
- **Upstream repositories or pages checked:**
  - in-repo precedent — `specs/close-product-loop-s2-guide-and-map/PLAN.md` (S2), S1's extracted
    `components/{flights,hotels}` result cards
  - https://tanstack.com/query/latest/docs/framework/react/guides/polling
  - https://tanstack.com/query/v5/docs/framework/react/guides/important-defaults
- **Official docs domains or pages checked:** `- none (local-only; no external surface)`

---

## Evidence Boundary

> **Confirmed from artifacts:** the four routes and their response models are present in
> `apps/web/src/lib/api/schema.d.ts` (no codegen needed); `Tabs.tsx` carries `overflow-x-auto` +
> `shrink-0` with the 390px comment; the trip page's tab-registration shape; `RoutePanel`'s data
> shape is a pure projection of `RouteResponse` plus a derivable `gmaps_url`; `WeatherPanel` /
> `AirQualityPanel` require BE-computed enrichment absent from REST; `TripMap` is presentational and
> already shared; `/weather` and `/air-quality` accept a city string only and `/places/route` accepts
> place IDs only; `TripDetail.city`, `TripItem.place_id` and `TripItem.start_time` are nullable;
> `get_day_plan` orders by `sort_order` and 409s without a `start_date`; REST carries no timezone and
> the FE's existing "today" is the browser's local calendar date, with `app/trips/page.tsx`
> disagreeing; the parity test's exact rule; the root layout provides the `Panel` namespace globally.
>
> **Inferred from patterns:** that the two `get_day_plan` 409 branches are unreachable behind the
> trip-window gate; that porting the BE weather/AQI enrichment would cost more than two purpose-built
> cards (sized from the BE files' line counts, not from a written adapter); that seven tabs read
> acceptably at 390px given the scroll fix.
>
> **Not checked:** the tab row at 390px with seven tabs in a browser; any test, typecheck or lint run;
> `AirQualityPanel.tsx` read only via its type contract and imports, not line by line;
> `DayPlanResponse.weather_score`'s provenance; whether any Playwright e2e touches the trip tab list.
