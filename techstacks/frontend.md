<!-- Frontend counterpart to architecture.md / guidelines.md (those cover the FastAPI BE only).
     Authoritative profile for apps/web/ — read before implementing, debugging, or reviewing FE
     work. Reflects the codebase as of 2026-09-21 (Next 16.2.9). Design SoT stays repo-root
     DESIGN.md + PRODUCT.md; this file is the layer/pattern/convention SoT for review. -->

# Frontend Profile — travel-pi (`apps/web/`, Next.js)

The Next.js web client for the Travel Planner. Talks to the FastAPI BE over a typed REST client
and consumes the agent's SSE stream. Package `@travel/web`; pnpm workspace + Turborepo. **Run FE
commands from `apps/web/`** with **Node v24** (`.nvmrc` → `24.17.0`; the `nvm` default is 18).

## Stack

| Area | Choice |
|---|---|
| Framework | **Next.js 16.2.9** (App Router, Turbopack default), **React 19.2.4** |
| Language | TypeScript 5, strict, `moduleResolution: bundler`, single alias `@/* → ./src/*` |
| Server state | **TanStack Query v5** (`5.101`) |
| API client | **openapi-fetch** `0.17` + **openapi-typescript** `7.13` (generated `schema.d.ts`) |
| Auth | **Supabase SSR** (`@supabase/ssr` 0.12, `supabase-js` 2.108) |
| i18n | **next-intl 4.13** — cookie-based locale, **no `[locale]` URL segment** |
| Styling | **Tailwind CSS v4** (CSS-first, `@theme`), `next-themes` 0.4.6 (class dark mode) |
| Streaming | custom typed SSE parser + **streamdown** 2.5 (animated markdown) |
| Maps | **maplibre-gl** 5.24 (lazy, `ssr:false`) |
| Testing | **Vitest 2.1** + Testing Library 16 + **MSW 2.7** (unit/integration); **Playwright 1.49** (e2e) |

## Project Structure (`apps/web/src/`)

```
app/            # App Router: layout.tsx (providers), page routes, auth route handlers
  trips/ trips/[tripId]/ places/ flights/ hotels/ bookings/ guide/[city]/ auth/*  # feature routes ("use client" pages)
  layout.tsx    # server: locale, providers, AppShell + ChatWidget
  error.tsx not-found.tsx
middleware.ts   # Supabase session refresh + redirect-gates protected route prefixes
components/
  ui/           # design-system primitives (Button, Card, Modal, ConfirmDialog, Field,
                #   Select, Textarea, Tabs, Pill, Meter, EmptyState, Spinner)
  app-shell/ trips/ bookings/ places/ flights/ hotels/ map/ auth/ theme/   # domain components
  chat/         # agent chat widget + panel/ side-panels + useAgentStream.ts
lib/
  api/          # client.ts (openapi-fetch), schema.d.ts (generated), keys.ts (qk), errors.ts
  query/        # provider.tsx + per-domain TanStack Query hooks (trips, items, budget, …)
  supabase/     # client.ts (browser), server.ts, middleware.ts (updateSession)
  identity/     # Supabase-session identity provider (no anonymous pseudo-identity)
  stream/       # parseSSE.ts, panel.ts (typed SSE + panel contracts)
  cn.ts datetime.ts   # className join, UTC datetime helper
i18n/           # request.ts, config.ts (locales en/vi), locale.ts (cookie server actions)
test/           # setup.ts, msw.ts (Vitest harness)
messages/       # en.json / vi.json (at apps/web/messages/, not under src/)
```

## Layers & Responsibilities

- **Route pages (`app/`)** — mostly `"use client"` (they use Query hooks + `useTranslations`).
  `layout.tsx` is the one async **server component**; auth `callback`/`confirm` are route handlers.
- **Domain components (`components/<domain>/`)** — feature UI, composed from `ui/` primitives.
- **`ui/` primitives** — the only place base interactive elements are defined. Extend the system,
  never route around it (see DESIGN.md).
- **`lib/query/` hooks** — the sole interface pages use for server data. Pages never call the API
  client directly; they call a `useX` hook.
- **`lib/api/`** — the typed transport seam. `client.ts` owns request middleware; `keys.ts` owns
  query-key identity; `errors.ts` owns typed 409 branching.

## Request / Data Flow

- **REST:** page → `lib/query` hook → `unwrap(client.GET/POST(...))` → **openapi-fetch** →
  proxied `/api/be/*` rewrite (`next.config.ts` → `NEXT_PUBLIC_API_URL`, default `:8000`) →
  FastAPI. `identityMiddleware` attaches the Supabase **bearer token** (`authHeader()`) and an
  `Idempotency-Key` (whitelisted POSTs).
- **Agent SSE:** `useAgentStream` POSTs to `${streamBaseUrl()}/agent/stream` **direct-to-origin**
  (bypasses the buffering proxy) with the Supabase **JWT** (`authHeader()`) → `parseSSE` typed
  events → panels + streamed markdown.
- **Errors:** `unwrap()` throws the openapi error; `throwOn409` maps to typed `ConflictError`
  subclasses (`OverBudgetError`, `DuplicatePlaceError`, `AlreadyShortlistedError`); callers branch
  by `instanceof`. Loading/empty via `isPending`/`isError` → `Spinner` / `EmptyState`.

## Key Patterns

| Pattern | Implementation |
|---|---|
| Typed API | all domain types derive from generated `lib/api/schema.d.ts` (`components["schemas"][...]`) |
| Server state | TanStack Query v5, `staleTime: 30_000`, fresh `QueryClient` per server request, browser singleton |
| Query keys | `qk` factory of readonly tuples; **no-arg prefix (`qk.expenses`) doubles as invalidation prefix** |
| Optimistic updates | `onMutate` snapshot + `setQueryData`, rollback in `onError`, invalidate in `onSettled` (`places.ts`, `items.ts`) |
| Full-replace PUT | `toUpdateBody` builds the complete body — a partial PUT wipes fields |
| Auth token | Both REST and agent SSE authenticate on the Supabase **bearer token** (`authHeader()`); REST attaches it in `client.ts` middleware, SSE sends it direct-to-origin. No `X-User-Id` header |
| i18n | cookie-driven (`getRequestConfig` reads `locale` cookie); panels use a **nested** `NextIntlClientProvider` on backend-detected `panelLanguage` |
| SSE contract | `parseSSE.ts` / `panel.ts` mirror `apps/api/app/streaming/{events,panels}.py` — keep in lockstep |
| Design tokens | Tailwind v4 `@theme` (static) + `@theme inline` w/ CSS-var indirection for light/dark flip |

## Conventions

- **TS:** strict; single path alias `@/* → ./src/*` (mirrored in `vitest.config.ts`). Naive
  datetimes pinned to UTC via `lib/datetime.ts` `toUtcDate`.
- **Naming:** PascalCase components, `useX` hooks, `qk`/`unwrap` idioms, per-module query-type
  re-exports. `cn()` (`lib/cn.ts`) for class joins — **not** clsx/tailwind-merge (some primitives
  still use `.filter(Boolean).join(" ")`; prefer `cn`).
- **Providers (`app/layout.tsx`) — order is load-bearing:** `ThemeProvider` → `NextIntlClientProvider`
  → `IdentityProvider` → `QueryProvider` → `AppShell` + `ChatWidget`.
- **Forms:** native `<form>` + controlled inputs (domain UI) or React 19 `useActionState` + server
  actions (auth). No form library.
- **Regenerate types, never hand-edit:** after a BE contract change, run `pnpm gen:api`
  (`openapi-typescript http://localhost:8000/openapi.json -o src/lib/api/schema.d.ts`) with the BE
  running. `schema.d.ts` is generated output.

## Design (UI work)

Web design SoT is **repo-root `DESIGN.md` + `PRODUCT.md`** — read before any UI change; use
`/impeccable`. Build from `components/ui/` primitives + Tailwind `@theme` tokens (`bg-panel`,
`border-line`, `text-ink`/`muted`, `xs–xl` spacing, `rounded-{sm,md,lg,pill}`). Non-negotiables:
**Departure Lime `#cbf24a` ≤10% of screen** (active/selected only), **primary action is ink, never
lime**, **no `window.confirm/alert/prompt`** (use `ConfirmDialog`/`Modal`), honor
`prefers-reduced-motion` on every animation. `components.json` is shadcn "new-york" (its
`@/lib/utils` alias mismatches the real `@/lib/cn` — fix scaffolds).

## Testing

- **Vitest** (`jsdom`, `globals`, setup `src/test/setup.ts`, include `src/**/*.{test,spec}.{ts,tsx}`;
  Playwright excluded). Test files colocated (`*.test.tsx` next to source). `pnpm test`.
- **`src/test/setup.ts` is load-bearing:** sets dummy Supabase env (client throws without them),
  absolutizes relative `Request` URLs (undici rejects `/api/be/...`), and `server.listen(...)` at
  top level — MSW must patch fetch **before** the openapi-fetch client module imports.
- **MSW** (`src/test/msw.ts`): empty base handlers; register per-endpoint with `server.use(...)`
  against `BASE="/api/be"`. Per-test `QueryClient` with `retry: false` (else error-path tests hang).
- **Playwright** (`playwright.config.ts`, `./playwright/`): chromium only, boots `pnpm dev` on
  `:3000` (reuses a running server), assumes BE on `:8000`. `pnpm e2e`.

## Stack version notes (2025–2026)

- **Next 16 vs 15:** `params`/`searchParams` are **async-only** — always `await params`. Turbopack
  is the default for dev *and* build (a custom `webpack` config needs `--webpack`). React 19.2 is
  required. `middleware.ts` still works here; Next's newer `proxy.ts` (Node runtime) is the
  forward direction — keep middleware to session-refresh/redirects, no heavy per-request work.
- **React 19:** `ref` is a plain prop — no `forwardRef`. Guard stream/effect setup for **Strict
  Mode double-invoke** (dev runs effects twice — `useAgentStream` already uses `inFlightRef`/
  `hydratedRef` for this). `use(promise)` needs a *stable/cached* promise or it suspends forever.
- **TanStack Query v5:** single **object** signature (`useQuery({ queryKey, queryFn })`); `isPending`
  (not `isLoading`). Never share one `QueryClient` across server requests (leaks between users).
- **next-intl 4:** `getRequestConfig` **must return `locale`** (v4 breaking change). Reading the
  cookie makes routes dynamic (no static generation) — expected here.
- **Supabase SSR:** `getClaims()` = fast local JWT verify (used in middleware); `getUser()` when
  you need server-authoritative revocation. In middleware, always write refreshed cookies back onto
  the returned response, and put nothing between `createServerClient` and the auth call.
- **Tailwind v4:** `@theme inline` bakes values at build (static tokens only); runtime dark-mode
  flip uses raw channel vars under `:root`/`.dark` mapped by a non-`inline` `@theme`. Class dark
  mode needs the `@custom-variant dark (...)` opt-in (pairs with `next-themes attribute="class"`).

## Load-bearing invariants — do NOT break

1. **Provider nesting order** in `app/layout.tsx` (Theme → Intl → Identity → Query).
2. **Bearer-token auth:** both REST and agent SSE authenticate on the Supabase JWT (`authHeader()`);
   there is no `X-User-Id` header and no anonymous pseudo-identity. REST attaches it via `client.ts`
   middleware; SSE sends it direct-to-origin. (A legacy `travel.userId` in `localStorage` survives
   only to claim pre-auth anonymous chat history once — it is not the REST identity seam.)
3. **SSE goes direct-to-origin** (`streamBaseUrl()`); REST goes through the `/api/be` proxy — the
   proxy buffers and would break streaming.
4. **`Idempotency-Key`** is auto-added only for the whitelisted POST paths (`POST /trips`,
   `POST /trips/{trip_id}/items`).
5. **PUT is full-replace** — always build the complete body via `toUpdateBody`; the item reorder is
   knowingly non-atomic (two PUTs).
6. **`schema.d.ts` is generated** — change the BE + rerun `gen:api`, never hand-edit.
7. **`max-w-md` is broken** under this Tailwind v4 token setup (`--spacing-md` collapses it to
   12px) — use explicit widths (e.g. Modal's `max-w-[28rem]`).
8. **Query-key prefix overloading** — `qk.expenses(tripId)` / `qk.savedPlaces(...)` with no filter
   args is also the invalidation prefix; don't repurpose it.
9. **i18n has no locale URL segment** (cookie-based); side-panels render under a **separate nested
   intl provider** keyed on `panelLanguage`, which may differ from the app locale.
10. **`middleware.ts` redirect-gates protected prefixes** (`/trips`, `/bookings`, `/expenses`,
    `/places`) — a signed-out request to one is redirected to `/auth/login?next=<path>` (`isProtected`
    in `supabase/middleware.ts`); the API also scopes data on the bearer subject.
11. **SSE parser/panel types mirror the BE** (`streaming/events.py`, `panels.py`) — a BE event
    change must be mirrored in `lib/stream/`.
