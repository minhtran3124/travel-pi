---
type: architecture
title: Web app shell, routing and auth
description: How the Next.js App Router frontend is assembled — the single server layout and its load-bearing provider order, the client-side app shell and route map, the Supabase session middleware that refreshes cookies and gates user-scoped routes, the password, magic-link and OAuth sign-in flows with a same-origin return-path guard, the identity context, and the typed openapi-fetch client whose middleware attaches the bearer token and mints idempotency keys behind the /api/be proxy.
tags: [nextjs, app-router, frontend, supabase, auth, middleware, api-client, openapi-fetch, tanstack-query, providers]
sources:
  - id: openwiki-source-999f60ece775e48a66373ded
    resource: repo://apps/web/next.config.ts
  - id: openwiki-source-dc6002ce5eb8ee2f4f663847
    resource: repo://apps/web/src/app/auth/actions.ts
  - id: openwiki-source-815e739dd7ea9efa208c98ad
    resource: repo://apps/web/src/app/auth/callback/route.ts
  - id: openwiki-source-d732174e4b9f7ac6354c0cef
    resource: repo://apps/web/src/app/auth/confirm/route.ts
  - id: openwiki-source-b23522a72e7c020fb273ab0d
    resource: repo://apps/web/src/app/layout.tsx
  - id: openwiki-source-deba80bf5b4e6fbdad344120
    resource: repo://apps/web/src/app/page.tsx
  - id: openwiki-source-51b80d2a7d768b83011f1c09
    resource: repo://apps/web/src/components/app-shell/AppShell.tsx
  - id: openwiki-source-41f24a13437a7a645e688340
    resource: repo://apps/web/src/lib/api/client.test.ts
  - id: openwiki-source-a12105538dcb0232dfb18910
    resource: repo://apps/web/src/lib/api/client.ts
  - id: openwiki-source-8532eb9ca8b28041f9d4a26f
    resource: repo://apps/web/src/lib/api/errors.ts
  - id: openwiki-source-63d51b047cb5d370e4d6448c
    resource: repo://apps/web/src/lib/api/keys.ts
  - id: openwiki-source-a904737643796654e489f3cd
    resource: repo://apps/web/src/lib/auth/next-path.test.ts
  - id: openwiki-source-1848165c7f9fa6b85c8cec0d
    resource: repo://apps/web/src/lib/auth/next-path.ts
  - id: openwiki-source-c54711f4fce0970f093d0dc8
    resource: repo://apps/web/src/lib/identity/provider.test.tsx
  - id: openwiki-source-1c062bf7b9bbdb305cf8cd18
    resource: repo://apps/web/src/lib/identity/provider.tsx
  - id: openwiki-source-f4c9a4e1ae403d902376c464
    resource: repo://apps/web/src/lib/query/provider.tsx
  - id: openwiki-source-43fbd27c1dc5890f4dbeb1f5
    resource: repo://apps/web/src/lib/query/trips.ts
  - id: openwiki-source-c4bea233c871a8644932e8f8
    resource: repo://apps/web/src/lib/supabase/middleware.ts
  - id: openwiki-source-aaa506ea8cabfd250f14882d
    resource: repo://apps/web/src/middleware.ts
  - id: openwiki-source-ac7a0884b0d373d783827e69
    resource: repo://techstacks/frontend.md
generated: { by: "claude-code", at: "2026-09-21T09:36:49.315Z" }
verified:
  - by: openwiki/0.5.2
    at: 2026-09-21T09:36:49.315Z
---

# Web app shell, routing and auth

`apps/web` is a Next.js 16 App Router application (React 19, TypeScript, Tailwind v4). Its job is to render user-scoped pages over the FastAPI REST surface and to host the agent chat widget. `techstacks/frontend.md` is the review profile for this app and describes the same identity model as the code: a Supabase bearer token on both REST and SSE, and a middleware that redirect-gates protected route prefixes.

## The root layout and provider order

`src/app/layout.tsx` is the one async **server component**. It resolves the locale for the `<html lang>` attribute and translated metadata, then nests providers in an order the frontend profile calls load-bearing: `ThemeProvider` → `NextIntlClientProvider` → `IdentityProvider` → `QueryProvider` → `AppShell` with the page as children, plus the floating `ChatWidget` as a sibling of the shell so it is present on every page. `suppressHydrationWarning` on `<html>` accommodates the theme class applied before hydration (see [Internationalization and theming](i18n-and-theming.md)).

- **`IdentityProvider`** (`src/lib/identity/provider.tsx`) publishes `{ userId, status }` from the Supabase browser session: `status` starts as `loading` on both the server render and the first client tick (so there is no hydration mismatch), resolves to `signed-in` or `signed-out` after the first session lookup, and then tracks `onAuthStateChange` live across tabs, unsubscribing on unmount. There is no anonymous pseudo-identity anymore; consumers gate authenticated work on `status === "signed-in"` via `useIdentity()` / `useUserId()`.
- **`QueryProvider`** creates a TanStack Query client with a 30-second default `staleTime`, fresh per server request and a module-level singleton in the browser, so server requests never share cache between users while client re-renders keep theirs.

## Routes and the shell

`AppShell` (`src/components/app-shell/AppShell.tsx`) is a client component rendering the header with the brand link, the primary navigation (`/trips`, `/places`, `/flights`, `/hotels`, `/bookings`, with `aria-current` on the active prefix), the locale switcher, theme toggle, user menu and a mobile hamburger menu. **Auth screens render without any chrome**: for any path under `/auth` the shell returns the children bare. The home route (`/`) redirects to `/trips`. Feature routes live under `src/app/`: `trips/`, `trips/[tripId]/`, `bookings/`, `flights/`, `hotels/`, `places/` and `guide/[city]/`, plus `error.tsx` and `not-found.tsx` (see [Trips, bookings and catalog pages](trips-bookings-and-catalog-pages.md)). Route pages are mostly `"use client"` because they use query hooks and translations.

## Session middleware and route gating

`src/middleware.ts` runs `updateSession` from `src/lib/supabase/middleware.ts` on every request except static assets. It builds a server Supabase client over the request cookies, calls `getClaims()` (a fast local JWT verification; the comments warn that removing it can randomly sign users out under SSR), and writes any refreshed cookies back onto the response. When there are no claims and the path starts with one of the **protected prefixes** `/trips`, `/bookings`, `/expenses` or `/places`, it redirects to `/auth/login?next=<original path and query>`, copying the rotated cookies onto the redirect so browser and server stay in sync. Those prefixes are gated because their pages render only user-scoped data that the API would refuse to an anonymous caller anyway (see [Authentication and user tiers](../concepts/auth-and-tiers.md)); `/expenses` is listed pre-emptively although expenses render inside the trip page today.

## Sign-in flows

Auth pages (`/auth/login`, `/auth/sign-up`, `/auth/auth-code-error`) use React 19 `useActionState` with **server actions** in `src/app/auth/actions.ts`: `signInWithPassword`, `signUpWithPassword` (sends a confirmation email whose link returns to `/auth/confirm`), `signInWithMagicLink`, and OAuth helpers for Google and GitHub. Two route handlers complete the flows: `/auth/callback` exchanges an OAuth or PKCE `code` for a session cookie, and `/auth/confirm` verifies the email OTP `token_hash` and `type`; both redirect to the `next` path on success and to the shared error page on failure.

Every `next` value passes through `safeNextPath(value, origin)` (`src/lib/auth/next-path.ts`), which is an **allowlist, not a blocklist**: it resolves the candidate against the site origin with the WHATWG URL parser and keeps it only if the result stays on that origin, returning `/` otherwise. This defeats open redirects such as `/\evil.example` or a leading `@host` that string concatenation would turn into a foreign host; the login page echoes `next` back through a hidden field and the server action re-validates it before redirecting.

Supabase clients are constructed per call from `NEXT_PUBLIC_SUPABASE_URL` and the publishable key: a browser client (`supabase/client.ts`), a cookie-backed server client for server components and actions (`supabase/server.ts`), and the middleware variant. `authHeader()` fetches a fresh access token on every call and returns `{}` when signed out or on the server.

## The typed API client

`src/lib/api/client.ts` creates an `openapi-fetch` client typed against the generated `schema.d.ts` with `baseUrl: "/api/be"`; `next.config.ts` rewrites `/api/be/:path*` to `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`), so the browser never needs CORS for REST. Run `pnpm gen:api` against a running backend whenever the API contract changes; the schema file is generated output and never hand-edited (see [Monorepo overview](../architecture/monorepo-overview.md)). A single request middleware does two things on every call:

1. Attaches the Supabase bearer token from `authHeader()`, so a new trip-backed query cannot ship without authentication and public endpoints are unaffected when logged out. A unit test pins that no legacy `X-User-Id` header is sent.
2. Mints a UUID `Idempotency-Key` for `POST /trips` and `POST /trips/{trip_id}/items` when the caller has not supplied one, matched on the templated schema path, so a retried request or a double-click replays instead of duplicating (see [Trips, itinerary and budget](../domain/trips-itinerary-and-budget.md)).

`unwrap()` collapses the `{ data, error }` result into "throw the error or return the data". `streamBaseUrl()` returns the backend origin directly, because the agent's Server-Sent Events bypass the buffering proxy and hit the API with the JWT (see [Chat widget and streaming client](chat-and-streaming-client.md)).

Pages never call the client directly. Per-domain hooks in `src/lib/query/` (`trips.ts`, `items.ts`, `budget.ts`, `expenses.ts`, `bookings.ts`, `flights.ts`, `hotels.ts`, `places.ts`, `shortlist.ts`, `today.ts`, `guide.ts`, `agent.ts`, `feedback.ts`) wrap `useQuery` / `useMutation`, invalidate through the `qk` key factory in `src/lib/api/keys.ts` (readonly tuples where a no-argument prefix such as `qk.expenses(tripId)` doubles as the invalidation prefix for `qk.expenseSummary(tripId)`), and derive their types from `components["schemas"]`. `src/lib/api/errors.ts` maps backend `409` responses to typed `ConflictError` subclasses (`OverBudgetError`, `DuplicatePlaceError`, `AlreadyShortlistedError`) carrying the backend `hint`, so pages branch with `instanceof` and show a notice instead of crashing.
