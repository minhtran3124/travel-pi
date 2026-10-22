---
type: architecture
title: Trips, bookings and catalog pages
description: The feature pages of the web app and how they consume the REST surface through per-domain TanStack Query hooks — the trips list and the tabbed trip detail (today, itinerary, budget, expenses, bookings, shortlist, map), the bookings table with client-side filtering and cancellation, the flights and hotels search pages that reuse the chat's result cards, the saved-places page with its browse drawer and optimistic flags, the city guide, and the full-replace, optimistic-update and typed-conflict conventions the hooks follow.
tags: [frontend, trips, itinerary, bookings, flights, hotels, places, guide, tanstack-query, optimistic-updates, maplibre]
sources:
  - id: openwiki-source-621d24813dd05a6fb3383df4
    resource: repo://apps/web/src/app/bookings/page.tsx
  - id: openwiki-source-70e7e66dbc3a093aedb2d7a7
    resource: repo://apps/web/src/app/flights/page.tsx
  - id: openwiki-source-fda0d1e709798e0a1ff19587
    resource: repo://apps/web/src/app/guide/%5Bcity%5D/page.tsx
  - id: openwiki-source-8ea35b6954d393181a78567b
    resource: repo://apps/web/src/app/hotels/page.tsx
  - id: openwiki-source-640d5058c760e2782d350c7c
    resource: repo://apps/web/src/app/places/page.tsx
  - id: openwiki-source-3c0ffd4ada8943a7635c0106
    resource: repo://apps/web/src/app/trips/%5BtripId%5D/page.tsx
  - id: openwiki-source-52a4d74971cdf303017ad1e7
    resource: repo://apps/web/src/components/map/TripMap.tsx
  - id: openwiki-source-1f6b7c072452667ac8c6ceff
    resource: repo://apps/web/src/components/trips/itinerary/ItineraryTab.tsx
  - id: openwiki-source-16f6955a9a37a98563f3a8af
    resource: repo://apps/web/src/components/trips/map/MapTab.tsx
  - id: openwiki-source-ee52cbe8772be1786e6f7527
    resource: repo://apps/web/src/components/trips/today/todaySelectors.test.ts
  - id: openwiki-source-238f219fa156314b67fb52c8
    resource: repo://apps/web/src/components/trips/today/todaySelectors.ts
  - id: openwiki-source-2e60500d52066516f88a756f
    resource: repo://apps/web/src/components/trips/today/TodayTab.tsx
  - id: openwiki-source-ec627a6f83093a07c079429e
    resource: repo://apps/web/src/lib/query/bookings.test.tsx
  - id: openwiki-source-9a56249dcd2d2721b3f23d71
    resource: repo://apps/web/src/lib/query/bookings.ts
  - id: openwiki-source-cb00fc7ce54f398c1bc5a867
    resource: repo://apps/web/src/lib/query/guide.ts
  - id: openwiki-source-f32d685746f9076f028c7d72
    resource: repo://apps/web/src/lib/query/items.test.tsx
  - id: openwiki-source-bc6110a12323e2d581eee19f
    resource: repo://apps/web/src/lib/query/items.ts
  - id: openwiki-source-6765dac32f415925f97674ca
    resource: repo://apps/web/src/lib/query/places.test.tsx
  - id: openwiki-source-0a164b32baff82d14d91afbd
    resource: repo://apps/web/src/lib/query/places.ts
  - id: openwiki-source-673d983f7392c1ffda210c84
    resource: repo://apps/web/src/lib/query/shortlist.test.tsx
  - id: openwiki-source-d860b95b5796e49059efcc38
    resource: repo://apps/web/src/lib/query/shortlist.ts
  - id: openwiki-source-9438e85b22043066561334eb
    resource: repo://apps/web/src/lib/query/today.ts
generated: { by: "claude-code", at: "2026-09-25T03:45:43.723Z" }
verified:
  - by: openwiki/0.5.2
    at: 2026-09-25T03:45:43.723Z
---

# Trips, bookings and catalog pages

Every feature page in `apps/web/src/app/` is a `"use client"` component that renders a per-domain hook from `src/lib/query/` and composes domain components from `src/components/<domain>/` on top of the `ui/` primitives. Pages never call the API client directly; hooks own the query keys, invalidation and error typing described in [Web app shell, routing and auth](app-shell-and-routing.md). All of these routes are user-scoped and therefore behind the session middleware.

## Trips list and creation

`/trips` renders `useTrips()` (`GET /trips`, newest first) as `TripCard`s with skeletons while pending and an `EmptyState` with a call to action when the list is empty. `NewTripModal` submits through `useCreateTrip`, whose `POST /trips` automatically carries an `Idempotency-Key` from the client middleware, and invalidates the `trips` prefix on success; the page then routes to the new trip.

## Trip detail: one route, seven or eight tabs

`/trips/[tripId]` reads `useTrip(id)` (`GET /trips/{id}`, the enriched `TripDetail` with spend rollup, gaps and shortlist) and shows a skeleton header, an error card with a link back to the list, or `TripHeader` plus a `Tabs` control. Each tab is a self-contained component that receives only `tripId` and fetches its own data:

- **Today** (`components/trips/today/`) computes the browser-local calendar date with `todayIso` (never `toISOString`, which can roll the date back across midnight UTC), checks it against the trip window with `isWithinTrip` (inclusive on both ends; a null end date is open-ended), and inside the window renders `useDayPlan(tripId, date)` (`GET /trips/{id}/day-plan`), the day's weather and air quality by city (`useWeather`, `useAirQuality`) and directions between consecutive stops (`useRoute`). Pure selectors in `todaySelectors.ts` pick the next non-optional item and its predecessor and are unit-tested on their own.
- **Itinerary** (`components/trips/itinerary/`) adds, edits, deletes and reorders items through `useAddItem`, `useUpdateItem`, `useDeleteItem` and `useReorderItem`. An add that the backend rejects as over budget arrives as a typed `OverBudgetError` and is shown as a notice with the backend hint rather than crashing (see [Trips, itinerary and budget](../domain/trips-itinerary-and-budget.md)).
- **Budget** reads `useBudget(tripId)` and writes caps with `useSetBudget`, which invalidates both the budget and the trip so the header's remaining-budget figure updates.
- **Expenses** uses `useExpenseSummary` and `useExpenses` with add, update and delete mutations that invalidate the `["expenses", tripId]` prefix, which covers the summary key too.
- **Bookings** lists `useBookings({ trip_id })`, the trip-scoped filter of the bookings endpoint.
- **Shortlist** manages the trip's place links with `useShortlist`, `useAddToShortlist` (a duplicate arrives as `AlreadyShortlistedError` and is surfaced as a non-crashing notice) and `useRemoveFromShortlist`, which deletes by the entry's `link_id`, not the place id.
- **Map** (`components/trips/map/MapTab.tsx`) turns the trip's places into markers for `TripMap`, a MapLibre GL component loaded client-side only with its stylesheet, since the map is a canvas that cannot render on the server.
- **Research** (`components/trips/research/`) appears only when `researchEnabled()` is true. It starts, follows, revises and applies a trip-research run (see [Trip research UI](trip-research-ui.md)).

The active tab is initialized from `?tab=` and follows later changes to that parameter, so a link such as the chat's research-done card (`?tab=research`) opens the tab directly. An unknown or disabled tab id falls back to Itinerary rather than rendering an empty tab.

## Hook conventions worth knowing

- **PUT is a full replace.** `toUpdateBody(item)` builds a complete `TripItemUpdate` including every optional field normalized to `null`, because the backend's update schema equals its create schema and a partial body would wipe omitted fields. `useReorderItem` swaps two items' `sort_order` with two complete `PUT`s.
- **Optimistic updates** follow one shape: `onMutate` cancels in-flight queries, snapshots the cache and writes the optimistic value; `onError` restores the snapshot; `onSettled` invalidates so the true server state is refetched. `useReorderItem` does this on the `TripDetail` cache, and the saved-places favourite and visited flags do it across every cached saved-places query. Tests cover the rollback paths (`items.test.tsx`, `places.test.tsx`).
- **Items and the trip invalidate together**, because items live inside `TripDetail` and the budget rollup changes whenever items change.
- **Typed conflicts.** `throwOn409` converts a `409` into `OverBudgetError`, `DuplicatePlaceError` or `AlreadyShortlistedError` carrying the backend `hint`; everything else is thrown as the raw error.

## Bookings

`/bookings` loads the caller's bookings once with `useBookings()` (a paginated envelope) and does **search, type and status filtering and sorting entirely client-side** with no server query parameters, per the feature's design note. `BookingTable` rows open a `BookingDetailModal`, and cancellation goes through `useCancelBooking`, which invalidates the list and the individual booking so the cancelled status refetches (`bookings.test.tsx`). Booking creation is not on this page: the REST book routes are premium-only and are exercised from the flights and hotels pages, while most bookings originate in the chat (see [Bookings, flights and hotels](../domain/bookings-flights-and-hotels.md)).

## Flights and hotels search

`/flights` collects origin, destination and date and runs `useFlightSearch(filters)` (`GET /flights/search`); `/hotels` collects city, dates, rooms and party size and runs a local `useHotelAvailability` query against `GET /hotels/availability`. Both pages **reuse the chat side-panel result cards** (`FlightResultCard`, `HotelResultCard`) by mapping the REST response into the flat panel shapes, and wrap them in `PanelIntlProvider` with the current UI locale so the shared card strings resolve from the `Panel` catalog slice (see [Chat widget and streaming client](chat-and-streaming-client.md)).

## Saved places and browsing

`/places` shows the traveller's saved places (`useSavedPlaces(filters)`) as `SavedPlaceCard`s with favourite and visited toggles (`useSetFavorite`, `useSetVisited`, optimistic as above) and deletion. A `BrowseDrawer` searches the catalog (`usePlaceSearch`) and saving a catalog place maps it into a `SavedPlaceCreate` for `useCreateSavedPlace`; the backend's proximity de-duplication arrives as `DuplicatePlaceError` and is rendered as an informational notice naming the existing place. Cards link to the city guide.

## City guide

`/guide/[city]` composes three independent sections from `src/lib/query/guide.ts`: visa requirements (`useVisa`), local tips (`useTips`) and climate normals (`useClimate`), each with its own loading, error and empty state so a failure in one (for example the visa lookup) never blanks the others. The data comes from the read-only travel-information services described in [Destinations, places and travel information](../domain/destinations-places-and-travel-info.md).
