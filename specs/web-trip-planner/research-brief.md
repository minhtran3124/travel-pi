---
slug: web-trip-planner
brief-depth: deep
created: 2026-06-26
feeds: specs/web-trip-planner/PLAN.md
---

# Research Brief — Phase 1 Frontend (Trip Planner + Agent Co-pilot)

> Deep-depth xia2 brief feeding the implementation plan. Every finding is labeled
> `Local` (read from this repo), `Upstream` (GitHub), `Docs` (official docs), or
> `Inference`. The backend contract is consumed **as-is** (design.md §2: no BE changes).

---

## Bottom Line

| Field | Value |
|---|---|
| **Recommendation** | **Adapt upstream** — wire `openapi-typescript` + `openapi-fetch` + TanStack Query v5 into the existing `apps/web` Next 16 scaffold; build the design system + chat widget from scratch against the confirmed BE contract. No backend work. |
| **Why this is the lightest credible path** | The BE contract is fully specified and stable (PagedResponse envelope, SSE framing already emits the right anti-buffering headers); the FE scaffold already has the `/api/be/*` proxy and Tailwind v4 CSS-first wiring, so the work is additive (deps + lib layers + components), not structural. |
| **Confidence** | 90% |
| **Next step** | Write `PLAN.md`: Wave 0 = deps + `gen:api` + providers + `@theme` tokens; then lib/api → lib/query → ui primitives → route shells → chat widget. Confirm the two open questions below before Wave 0. |

---

## Repo Snapshot

| Field | Detected |
|---|---|
| Repo type | pnpm + Turbo monorepo (`apps/*`, `packages/*`) |
| Primary language + runtime | TypeScript 5 / Node ≥20; backend Python (FastAPI) in `apps/api` |
| Frameworks / platforms | Next.js **16.2.9** (App Router), React **19.2.4**, Tailwind **v4** (CSS-first), FastAPI BE |
| Relevant packages | `@travel/web` (apps/web) — the FE target. BE exposes `/openapi.json`. |
| Detectable versions | next 16.2.9 · react 19.2.4 · tailwindcss ^4 · `@tailwindcss/postcss` ^4 · typescript ^5 · pnpm@11.9.0 · turbo v2 |
| Important constraints | design.md §2 non-goals: no BE changes, no real auth (local pseudo-identity), no `packages/sdk` yet (client lives in `apps/web`), reorder = full-replace PUT. CLAUDE.md: warm-coral chrome + lime chat overlay. |

---

## Feature Understanding and Assumptions

- **Requested feature:** A Deep research brief (research only — no code) for the Phase 1 FE described in `specs/web-trip-planner/design.md`, covering 5 areas: BE schemas/errors, agent SSE framing, `apps/web` scaffold state, openapi-ts + TanStack Query on Next 16, and DESIGN.md → Tailwind v4 `@theme` tokens.
- **What success appears to mean:** A scannable, concrete brief that the implementation plan can be written from without re-reading the BE or external docs — exact field names, the exact SSE parser contract, exact token hex values, and current library versions.
- **Assumptions from the request:** The BE is consumed as-is; the FE uses the `/api/be/*` proxy; single logical user via localStorage UUID.
- **Assumptions still needing confirmation:** (1) the `gen:api` script targets a *running* BE at `http://localhost:8000/openapi.json` (no committed spec checked in CI yet); (2) whether the SSE stream goes through the Next proxy or direct-to-origin in Phase 1 (design.md §11 leaves this conditional on observed buffering).

---

## Evidence Ledger

| Label | Evidence |
|---|---|
| `Local` | **PagedResponse envelope** = `{ total, limit, offset, results[] }` (`apps/api/app/schemas/pagination.py:12-18`) — used by every list endpoint. |
| `Local` | **PUT /trips/{id}/items/{itemId} is full-replace**: `TripItemUpdate` is identical to `TripItemCreate` and **includes `sort_order`** (`apps/api/app/schemas/trip.py`). Reorder MUST send the complete item body. |
| `Local` | **SSE framing** = `data: <chunk>\n\n` per event, terminal `data: [DONE]\n\n`, media_type `text/event-stream`, **payload is plain text not JSON** (`apps/api/app/core/streaming.py:18-26`). |
| `Local` | **Anti-buffering headers already set by BE**: `Cache-Control: no-cache`, `X-Accel-Buffering: no` (`apps/api/app/core/streaming.py:26`). |
| `Local` | **Only POST /trips and POST /trips/{id}/items read `Idempotency-Key`** (`apps/api/app/routers/trips.py:47-59,191-203`). Toggles/cancel are idempotent by design (no header). |
| `Local` | **Scaffold has the proxy**: `next.config.ts` rewrites `/api/be/:path*` → `${NEXT_PUBLIC_API_URL || http://localhost:8000}/:path*`. Tailwind v4 is CSS-first (`@import "tailwindcss"` + `@theme` in `globals.css`); no `tailwind.config`. |
| `Local` | **Scaffold is missing**: TanStack Query, openapi-typescript/openapi-fetch, vitest, playwright, `gen:api` script, any providers in `layout.tsx`, `.env`. |
| `Docs` | Current versions: openapi-typescript **7.13.0**, openapi-fetch **0.17.0**, @tanstack/react-query **5.101.1** (live npm registry). |
| `Docs` | Next 16 streaming guide confirms proxy/compression buffering defeats SSE; renamed `middleware` → `proxy` file convention; rewrites stay in `next.config`. |
| `Inference` | `EventSource` is GET-only / no headers / no body → unusable for `POST /agent/stream`; must use `fetch` + `ReadableStream` + `TextDecoder`. |

---

## Local Findings

### Area 1 — BE request/response schemas + error codes (`Local`)

**Pagination envelope (`apps/api/app/schemas/pagination.py:12-18`):** `PagedResponse[T]` = `{ total:int, limit:int (1–500, default 20), offset:int (≥0, default 0), results: T[] }`. List endpoints return named subclasses (`TripListResponse`, `ExpenseListResponse`, `SavedPlaceListResponse`, `BookingListResponse`, `PlaceSearchResponse`).

**Error envelope (`apps/api/app/schemas/error.py`):** every error → `{ error, message, status_code, path, hint?, errors? }`. `errors[]` (per-field) only on 422. Mapping: 404 NotFoundError · 409 ConflictError · 422 validation/DomainValidationError · 502 UpstreamError.

**Trips** (`schemas/trip.py`, `routers/trips.py`):
- `POST /trips` → 201, body `TripCreate{ title(req,1–200), city?, start_date?, end_date?, travelers(def 1,1–50), notes?(≤2000), items: TripItemCreate[] }`, resp `Trip`. **Reads `Idempotency-Key`.** 422.
- `GET /trips` → 200, query `limit/offset`, resp `TripListResponse` (PagedResponse[Trip]). No idempotency.
- `GET /trips/{id}` → 200/404, resp **`TripDetail`** = Trip + `total_spent:float` + `remaining_budget:float|null` (null if no cap) + `gaps:string[]` (e.g. "Day 3 has no accommodation") + `places: ShortlistEntry[]`.
- `PUT /trips/{id}` → 200/404, body `TripUpdate` (same fields as create minus `items`), resp `Trip`.
- `DELETE /trips/{id}` → 204/404.

**Trip items** (`schemas/trip.py`):
- `POST /trips/{id}/items` → 201/404/409, body `TripItemCreate{ day(req,≥1), kind(place|activity|meal|transport|note), status(pending|booked|constraint|optional, def pending), title(req,1–200), sort_order(int,def 0,≥0), place_id?, booking_id?, start_time?, notes?(≤1000) }`, resp `TripItem` (= create + `id`, `trip_id`). **Reads `Idempotency-Key`** (replaying same key on a *different* trip → 409). **409** when a linked `booking_id` would exceed a budget cap.
- `PUT /trips/{id}/items/{itemId}` → 200/404, body `TripItemUpdate` **≡ `TripItemCreate` (full replace, includes `sort_order`)**, resp `TripItem`. No idempotency header. **This is the reorder path — send the whole item with the new `sort_order`.**
- `DELETE /trips/{id}/items/{itemId}` → 204/404.

**Budget** (`schemas/trip.py`):
- `GET /trips/{id}/budget` → 200/404, resp `TripBudget{ trip_id, categories:{ flights,hotels,activities,buffer → each CategoryBudget{ cap:float|null, spent:float, remaining:float|null } }, total_cap?, total_spent, total_remaining?, over_budget:bool }`.
- `POST /trips/{id}/budget` → 200/404, body `TripBudgetSet{ flights?,hotels?,activities?,buffer? (each float|null,≥0) }` (**full replacement of caps**), resp `TripBudget`.

**Expenses** (`schemas/expense.py`, `routers/expenses.py`):
- `POST /trips/{id}/expenses` → 201/404, body `ExpenseCreate{ category(food|transport|accommodation|activities|shopping|entertainment|health|other), amount(req,>0), currency(req,ISO4217), description?, occurred_at?(ISO-8601, def now) }`, resp `Expense` (+ `id, trip_id, amount_usd, fx_rate, created_at, short_code (EXP-XXXXXX)`). No idempotency header.
- `GET /trips/{id}/expenses` → 200/404, query `limit/offset` + filters `category?, currency?, date_from?, date_to?` (ISO-8601 ≥/≤ on occurred_at), resp `ExpenseListResponse`.
- `PATCH /trips/{id}/expenses/{expenseId}` → 200/404, body `ExpenseUpdate` (all optional — partial), resp `Expense`.
- `DELETE /trips/{id}/expenses/{expenseId}` → 204/404.
- `GET /trips/{id}/expenses/summary` → 200/404, resp `ExpenseSummary{ expense_count, total_usd, by_category[], by_currency[], budget: ExpenseBudgetActuals{ total_cap?, booked_spent, expense_spent, total_spent, total_remaining?, over_budget } }`.

**Saved places** (`schemas/saved_place.py`, `routers/places.py:225-314`):
- `POST /places/saved` → 201/**409**/422, body `SavedPlaceCreate{ name(req), city?, country?, category?, address?, latitude?, longitude?, price_level?(1–4), notes?, links?[], duration?(≥0 min), favorite(def F), visited(def F) }`, resp `SavedPlace` (+ `id, created_at, short_code (SPL-XXXXXX)`). **409 on duplicate** (case-insensitive name within ~50m, or same city); 409 body includes `hint` = existing short_code.
- `GET /places/saved` → 200, query `limit/offset` + `city?, category?, favorite?, visited?`, resp `SavedPlaceListResponse`.
- `DELETE /places/saved/{id}` → 204/404 (accepts UUID or `SPL-` code; soft delete).
- `POST /places/saved/{id}/favorite` and `/visited` → 200/404/422, body `SavedPlaceFlag{ value:bool }`. **Idempotent SET (not toggle)** — client sends target boolean. No idempotency header needed.

**Place search** (`schemas/place.py`):
- `GET /places/search` → 200/422, query `limit/offset, city?(fuzzy), category?(attraction|restaurant|cafe|activity|nightlife|shopping), min_rating?(0–5, ""=none), price_level?(1–4, ""=none), recommended(bool,def F), sort(rating_desc|rating_asc|name|price_asc|price_desc|reviews_desc, def rating_desc)`. Resp `PlaceSearchResponse` = PagedResponse[Place] + echoed filter fields. Unknown city → `total: 0` (not 404). `Place{ id, name, city, country, category, description, address, rating, review_count, price_level, opening_hours?, image_url, tags[], is_recommended, latitude?, longitude?, short_code (PLC-XXXXXX) }`.

**Trip places / shortlist** (`schemas/trip.py`):
- `POST /trips/{id}/places` → 201/404/**409**, body `AddTripPlaceRequest{ place_id(req, UUID or PLC- code), source(def "catalog" | "saved") }`, resp `ShortlistEntry{ link_id, source, place: Place|SavedPlace }`. **409 already shortlisted.**
- `GET /trips/{id}/places` → 200/404, resp **`ShortlistEntry[]` (plain list, NOT paginated)**.
- `DELETE /trips/{id}/places/{link_id}` → 204/404 (delete by `link_id`, not place_id).

**Bookings** (`schemas/booking.py`):
- `GET /bookings` → 200, query `limit/offset` + `q?` (search id/confirmation/name/email), `type?`(flight|hotel), `sort?`(created_desc|created_asc|price_desc|price_asc). Resp `BookingListResponse`. NOTE: design.md §5 says Phase 1 does client-side filtering — but server-side `q`/`type`/`sort` exist if wanted later.
- `Booking{ id, type, reference_id, customer_name, customer_email, total_price, currency(def USD), status(confirmed|cancelled), created_at, details: FlightBookingDetails|HotelBookingDetails (discriminated by "kind"), notes?, confirmation_code (computed PNR), summary (computed one-liner) }`.
- `GET /bookings/{id}` → 200/404 (accepts UUID or 6-char confirmation code).
- `POST /bookings/{id}/cancel` → 200/404, **no body**, resp `Booking` (status=cancelled). **Idempotent** (re-cancel = no-op); no idempotency header.

**Agent** (`schemas/agent.py`):
- `POST /agent/chat` → 200/422, body `ChatRequest{ message(req,≥1), user_id(req), trip_id?, conversation_id? }`, resp `ChatResponse{ conversation_id, reply, current_flow? }`.
- `POST /agent/stream` → SSE (see Area 2). Same `ChatRequest` body.
- `GET /agent/manifest` → 200, resp `AgentManifest{ subagents: string[], tools: ToolManifestEntry[]{ name, description, read_only:bool, destructive:bool } }`. Source for the widget's quick-reply chips.

**Idempotency-Key summary (`Local`):** ONLY `POST /trips` and `POST /trips/{id}/items` read the header. Everything else either is naturally idempotent (flag SET, cancel) or is a create/patch without replay protection. So the FE should attach `Idempotency-Key` (a UUID) on **new-trip** and **add-item** mutations only.

### Area 2 — Agent /stream SSE framing (`Local` — CRITICAL)

Source: `apps/api/app/core/streaming.py` (the helper) + `apps/api/app/routers/agent.py:110-127` (the token generator).

- **media_type:** `text/event-stream`.
- **Framing:** each token is `f"data: {chunk}\n\n"`; completion is a terminal `data: [DONE]\n\n`. Delimiter between events is the blank line (`\n\n`).
- **Payload is PLAIN TEXT, not JSON.** There is exactly ONE event type — no `event:` field, no `token`/`tool_call`/`final` discrimination. Each `data:` carries a raw model token/string. The generator yields `chunk.content` from `graph.astream(..., stream_mode="messages")`, filtered to SUBAGENT nodes.
- **Anti-buffering headers already emitted by BE:** `Cache-Control: no-cache`, `X-Accel-Buffering: no` (`streaming.py:26`).
- **Non-streaming sibling:** `POST /agent/chat` returns JSON `ChatResponse{ conversation_id, reply, current_flow? }` — the widget's SSE-error fallback.

**Client parser contract the widget must implement (`Inference` from framing):**
1. `fetch("/agent/stream", { method:"POST", headers:{ "Content-Type":"application/json" }, body: JSON.stringify(ChatRequest), signal })` — NOT `EventSource` (POST + body needed).
2. `const reader = res.body.getReader(); const dec = new TextDecoder();` accumulate into a buffer.
3. Split buffer on `\n\n`; keep the trailing partial segment in the buffer.
4. For each complete segment starting `data: `, strip the 6-char prefix. If payload `=== "[DONE]"` → close/stop (don't render). Else **append the raw text** to the growing assistant bubble.
5. On fetch/stream error → fall back to `POST /agent/chat` and render `reply`.

> **Watch-out (`Inference`):** because chunks are raw text wrapped only as `data: {chunk}`, a token containing a newline would technically split the SSE frame. In practice LangGraph message tokens rarely contain `\n\n`; the parser should tolerate a `data:`-less continuation line by treating it as more of the current event rather than crashing. The brief flags this for the widget's parser tests.

### Area 3 — apps/web scaffold state (`Local`)

- **Versions:** Next **16.2.9**, React **19.2.4**, Tailwind **v4** (`tailwindcss ^4` + `@tailwindcss/postcss ^4`), TypeScript ^5. Node ≥20, pnpm@11.9.0, Turbo v2. Package name **`@travel/web`**.
- **Proxy (present):** `next.config.ts` rewrites `source: /api/be/:path*` → `destination: ${API_URL}/:path*` where `API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"`. Turbopack root pinned to monorepo root. No other rewrites; **no `proxy`/middleware file**.
- **Tailwind v4 wiring (present, CSS-first):** `apps/web/src/app/globals.css` does `@import "tailwindcss";` then a starter `@theme inline { --color-background, --color-foreground, --font-sans, --font-mono }` plus `:root` light/dark vars. `postcss.config.mjs` = `{ plugins: { "@tailwindcss/postcss": {} } }`. **No `tailwind.config.*` file** — config is CSS-first.
- **tsconfig:** path alias `@/* → ./src/*`, strict, target ES2017, jsx react-jsx.
- **layout.tsx:** Geist/Geist_Mono fonts, default "Create Next App" metadata, **no providers**. `page.tsx` is a demo server component fetching `/weather`.
- **Source tree:** only `app/{favicon, globals.css, layout.tsx, page.tsx}` — none of `lib/`, `components/`, `query/`, `identity/` exist yet.
- **Missing (all must be added):** `@tanstack/react-query`, `openapi-typescript`, `openapi-fetch`, `vitest` + RTL + MSW, `playwright`, a `gen:api` script, providers, `.env`/`.env.example`.

### Area 5 — DESIGN.md tokens → Tailwind v4 `@theme` (`Local` + `Docs`)

Token source of truth: `apps/api/DESIGN.md` ("Sunset Departures Board") + actual hex in `apps/api/app/templates/base.html` `:root`. Full vocabulary:

- **Coral brand:** bright `#ff6f5e` (focus/active/accent), deep `#c2410c` (primary fills under white text), soft `#ffa99c` (accent text on dark), on-accent ink `#3a0f08`, glow `rgba(255,111,94,0.16)`.
- **Surfaces:** void/bg `#1a1614`, panel `#221d1a`, panel-raised `#2e2723`, line `#3e342e`, line-soft `#2f2823`.
- **Text:** ink `#efe9e6`, muted `#a89c96`.
- **Status spectrum (closed, fixed meaning):** green `#34d399`, yellow `#fbbf24`, orange `#fb923c`, cyan `#38bdf8`, red `#f87171`, hotel `#2563eb`.
- **Topic palette:** transport `#fbbf24`, money `#34d399`, safety `#f87171`, culture `#c084fc`, food `#fb923c`, connectivity `#38bdf8`, health `#fb7185`, etiquette `#2dd4bf`, **best_time `#a3e635` (the lime — reused for the Kith chat accent per design.md §7)**, language `#818cf8`.
- **Typography:** Inter (system-ui fallback) display→label; Menlo mono. Scale: Display 2.4rem/800/-0.02em, Headline 1.35rem/800, Title 1.1rem/800, Body 0.9rem/400/1.6, Label 0.68rem/700/0.08em UPPERCASE, Mono 0.8rem. `tabular-nums` on all compared numbers.
- **Radii:** sm 8px, md 12px, pill 999px.
- **Spacing:** xs 4 / sm 8 / md 12 / lg 16 / xl 24 (px).
- **Shadows:** resting `0 2px 12px rgba(0,0,0,.45)`, lifted `0 14px 32px -8px rgba(0,0,0,.60), 0 4px 10px -4px rgba(0,0,0,.40)`.
- **Focus ring:** `0 0 0 3px rgba(255,111,94,0.35)` on every focusable control (`:focus-visible`).
- **Buttons:** 34px height; primary = coral-deep bg + white text + 8px radius + `0 18px` pad, hover `brightness(1.1)`, active `translateY(1px)`; ghost = transparent + 1px line border + muted text, hover → coral-soft text/coral-bright border. Inputs match 34px height, panel-raised bg.
- **Motion:** `tp-pop` entrance `0.16s ease-out` (from `opacity:0; translateY(8px) scale(.98)`); **every animation needs a `prefers-reduced-motion` near-instant (`.01ms`) alternative**.
- **Do/Don't:** coral reserved for brand/focus; pair every status/topic color with text or icon; tabular-nums on compared numbers; AA via `color-mix`; never add a new accent/status hue; no cream backgrounds, no gradient text, no uppercase eyebrows on every section, no decorative glassmorphism.

**Concrete starter `@theme` (Tailwind v4 CSS-first, drop into `globals.css` replacing the placeholder block) — `Docs` (v4 `@theme` syntax) + `Local` (values):**

```css
@import "tailwindcss";

@theme {
  /* coral brand */
  --color-coral-bright: #ff6f5e;
  --color-coral-deep:   #c2410c;
  --color-coral-soft:   #ffa99c;
  --color-on-accent:    #3a0f08;

  /* surfaces */
  --color-void:          #1a1614;
  --color-panel:         #221d1a;
  --color-panel-raised:  #2e2723;
  --color-line:          #3e342e;
  --color-line-soft:     #2f2823;

  /* text */
  --color-ink:    #efe9e6;
  --color-muted:  #a89c96;

  /* status spectrum (closed) */
  --color-status-confirmed: #34d399; /* green  */
  --color-status-estimated: #fbbf24; /* yellow */
  --color-status-delayed:   #fb923c; /* orange */
  --color-status-boarding:  #38bdf8; /* cyan   */
  --color-status-cancelled: #f87171; /* red    */
  --color-status-hotel:     #2563eb; /* hotel  */

  /* topic palette (incl. lime for the Kith chat accent) */
  --color-topic-transport:    #fbbf24;
  --color-topic-money:        #34d399;
  --color-topic-safety:       #f87171;
  --color-topic-culture:      #c084fc;
  --color-topic-food:         #fb923c;
  --color-topic-connectivity: #38bdf8;
  --color-topic-health:       #fb7185;
  --color-topic-etiquette:    #2dd4bf;
  --color-lime:               #a3e635; /* best_time → chat accent */
  --color-topic-language:     #818cf8;

  /* typography */
  --font-sans: "Inter", system-ui, sans-serif;
  --font-mono: "Menlo", "Consolas", "SF Mono", monospace;

  /* radii */
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-pill: 999px;

  /* spacing (extends the default scale with named steps) */
  --spacing-xs: 4px;
  --spacing-sm: 8px;
  --spacing-md: 12px;
  --spacing-lg: 16px;
  --spacing-xl: 24px;

  /* elevation */
  --shadow-card: 0 2px 12px rgba(0,0,0,.45);
  --shadow-lift: 0 14px 32px -8px rgba(0,0,0,.60), 0 4px 10px -4px rgba(0,0,0,.40);
}

/* coral focus ring — outside @theme (it's a utility, not a token) */
@layer base {
  *:focus-visible { box-shadow: 0 0 0 3px rgba(255,111,94,.35); outline: none; }
}

@keyframes tp-pop {
  from { opacity: 0; transform: translateY(8px) scale(.98); }
  to   { opacity: 1; transform: none; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: .01ms !important; transition-duration: .01ms !important; }
}
```

> Note (`Docs`): in Tailwind v4 the `@theme` namespaces are load-bearing — `--color-*` generates `bg-*`/`text-*`/`border-*` utilities, `--font-*` generates `font-*`, `--radius-*` generates `rounded-*`. The chat widget's lime is `--color-lime` so it reads as `bg-lime`/`text-lime`, reusing the existing `best_time` hue rather than introducing a foreign color (design.md §7).

---

## Upstream Findings

- **Repositories inspected (`Upstream`/`Docs`):** `openapi-ts/openapi-typescript` (the typegen + `openapi-fetch` companion), `TanStack/query`, `vercel/next.js` (streaming/SSE discussions #48427, #9965).
- **Pattern already present upstream:** the exact FE pattern this plan needs is the documented openapi-fetch happy path — `createClient<paths>({ baseUrl })`, `{ data, error }` returns (no throw on HTTP error), and a `Middleware.onRequest` to inject headers. Maps 1:1 to the design's `be(path, opts)` wrapper + `user_id`/`Idempotency-Key` injection.
- **Areas worth modeling:** openapi-fetch middleware-auth doc for the header seam; TanStack "Advanced SSR" `getQueryClient()` helper (server fresh / browser singleton).
- **Match to this repo:** very close — the BE serves a standard OpenAPI 3.x `/openapi.json`, and `apps/web` is a stock Next 16 App Router app, so no adaptation friction expected.
- **Upstream gaps:** SSE framing is not standardized by any of these libs — the widget's stream parser is bespoke (raw `data:`/`[DONE]` text), so reuse a tiny helper (`@microsoft/fetch-event-source`) only if POST-EventSource semantics are wanted; otherwise hand-roll per Area 2.

---

## Docs Findings

- **Official sources checked:** openapi-ts.dev (cli, openapi-fetch, middleware-auth), tanstack.com/query/v5 (advanced-ssr, ssr), nextjs.org/docs/app/guides/streaming (lastUpdated 2026-06-23).
- **Version-matched vs latest-stable:** all current as of June 2026 — openapi-typescript **7.13.0**, openapi-fetch **0.17.0**, @tanstack/react-query **5.101.1**, Next **16.2.9**. v7 openapi-typescript is ESM-first; Node 20.x+ recommended (not a hard pin); TS peer `^5`.
- **Built-in capabilities supporting the feature:**
  - **Typegen:** `npx openapi-typescript http://localhost:8000/openapi.json -o ./src/lib/api/schema.d.ts`; wire as `"gen:api"`. For CI without a live BE, point at a committed spec file.
  - **Typed client:** `openapi-fetch` `createClient<paths>` with typed `GET/POST/PUT/PATCH/DELETE`, path/query params typed, `{ data, error, response }` return, `client.use({ onRequest })` middleware for `user_id` + `Idempotency-Key`.
  - **TanStack v5 provider:** a `"use client"` Providers component using a `getQueryClient()` helper (`isServer` → fresh client; browser → singleton) wrapped in `layout.tsx`. For this client-heavy app, `HydrationBoundary`/prefetch is **optional** — a plain client provider suffices; `useState(() => new QueryClient())` is an acceptable simpler form.
- **Important caveats:**
  - **SSE-through-proxy buffering** is the headline risk. Next rewrites + compression re-buffer SSE (#48427, #9965). Cleanest fix: **call the FastAPI origin directly from the browser for `/agent/stream`** (use `NEXT_PUBLIC_API_URL`), keep the `/api/be/*` rewrite for non-streaming calls. The BE already sends `X-Accel-Buffering: no` + `no-cache`, which helps but does not override Next's own proxy buffering. If proxying is required, a Next route handler must pass `response.body` through with `runtime = "nodejs"`, `Cache-Control: no-cache, no-transform`, `X-Accel-Buffering: no`.
  - **Browser SSE consumption:** `EventSource` is GET-only and cannot send headers or a body → unusable for `POST /agent/stream`. Use `fetch` + `ReadableStream` + `TextDecoder` (supports POST/headers/`AbortController`). SSE framing is not auto-parsed by raw fetch — parse the `data:`/`\n\n`/`[DONE]` buffer manually (per Area 2).
  - Next 16 renamed the `middleware` file convention → `proxy`; `next.config` rewrites are unchanged.

---

## Recommendation

- **Primary recommendation:** **Adapt upstream + build the bespoke surface.** Add `openapi-typescript`/`openapi-fetch`/`@tanstack/react-query` (+ test deps) to the existing scaffold; generate `schema.d.ts` from the live `/openapi.json`; implement the `lib/api` `be()` wrapper (proxy base + `user_id` + conditional `Idempotency-Key`), `lib/query` hooks, `lib/identity`, the `@theme` design system, the route shells, and the self-contained chat widget with a hand-rolled SSE parser.
- **Why this is the lightest credible path:** the BE contract is fully nailed down (every schema, error code, the PagedResponse envelope, the exact SSE framing + anti-buffering headers), and the scaffold already ships the `/api/be/*` proxy and Tailwind v4 CSS-first wiring — so Phase 1 is additive, not structural, and needs zero backend change (design.md §2).
- **Why the next-best alternative lost:** a hand-written fetch layer (no openapi-fetch) was rejected — it forfeits the compile-time guarantee against OpenAPI drift, which is an explicit success criterion (design.md §3) and the cheapest insurance given a ~70-endpoint BE.
- **What would change this recommendation:** if the SSE stream cannot be made to flush through *either* the Next proxy or direct-origin (e.g. a deploy target that buffers regardless), the widget would fall back to `POST /agent/chat` non-streaming as the primary path, demoting the streaming parser to progressive enhancement.

---

## Risks, Unknowns, and Follow-Up Questions

- **Technical risks:**
  - **SSE through the Next proxy buffers** (Docs: #48427/#9965). Mitigation: stream direct-to-origin via `NEXT_PUBLIC_API_URL`; keep `/api/be/*` for JSON. The BE already sets `X-Accel-Buffering: no` + `no-cache`.
  - **OpenAPI drift:** `schema.d.ts` is generated from a *running* BE; if the BE changes without regen, types silently lie. Mitigation: commit `schema.d.ts`, add a Phase-2 CI check that `gen:api` produces no diff (design.md §11).
  - **Single-user identity assumption:** `GET /trips` returns *all* trips; the FE treats them as "mine" via a localStorage UUID. The `IdentityProvider` is the one seam to swap for real auth — no other layer derives identity (design.md §6).
  - **SSE token-with-newline edge case** (Inference): raw `data: {chunk}` framing could split if a token contains `\n\n`; the parser must tolerate continuation lines. Add a unit test.
  - **Full-replace PUT for reorder:** forgetting to send the complete `TripItemUpdate` body (all fields + new `sort_order`) would wipe item fields. Reorder mutation must read current item state and resend it whole.
- **Evidence gaps:** Context7 MCP was unavailable to the docs agent (used WebSearch/WebFetch + live `npm view` instead); versions are confirmed from the npm registry, doc *page* content from official sites. The TanStack tutorial's `environmentManager.isServer()` is tutorial-specific — prefer the exported `isServer`.
- **Version uncertainties:** openapi-typescript Node floor is a recommendation (20.x+), not a pinned `engines.node`. Confirm against the installed version after `pnpm add`.
- **Follow-up questions for the user (max 2):**
  1. For `/agent/stream`, do you want Phase 1 to go **direct-to-origin** (`NEXT_PUBLIC_API_URL`) from the start to dodge proxy buffering, or attempt the `/api/be/*` proxy first and fall back only if buffering is observed?
  2. Should `gen:api` target the live BE URL (requires BE running to regen) or a **committed `openapi.json`** snapshot (CI-friendly, but a manual refresh step)?

---

## Source Pack

- **Local files read:**
  - `specs/web-trip-planner/design.md`
  - `apps/api/app/schemas/{pagination,trip,expense,place,saved_place,booking,agent,error}.py`, `apps/api/app/enums.py`, `apps/api/app/exceptions.py`
  - `apps/api/app/routers/{trips,expenses,places,bookings,agent}.py`, `apps/api/app/services/trip_service.py`
  - `apps/api/app/core/streaming.py`
  - `apps/api/DESIGN.md`, `apps/api/app/templates/base.html`
  - `apps/web/package.json`, `apps/web/next.config.ts`, `apps/web/src/app/{layout.tsx,page.tsx,globals.css}`, `apps/web/postcss.config.mjs`, `apps/web/tsconfig.json`
  - root `package.json`, `pnpm-workspace.yaml`
- **Upstream repositories / pages checked:** github.com/openapi-ts/openapi-typescript · github.com/TanStack/query · github.com/vercel/next.js (discussions #48427, issue #9965)
- **Official docs domains / pages checked:** openapi-ts.dev (cli, openapi-fetch, api, middleware-auth, introduction) · tanstack.com/query/v5 (advanced-ssr, ssr) · nextjs.org/docs/app/guides/streaming

---

## Evidence Boundary

> **Confirmed from artifacts (Local):** every BE request/response shape, error code, and the Idempotency-Key surface (read from `apps/api/app/schemas` + `routers` + `trip_service.py`); the exact SSE framing `data: {chunk}\n\n` + `[DONE]` + media type + anti-buffering headers (`core/streaming.py`, `routers/agent.py`); the `apps/web` scaffold state (deps, proxy rewrite, Tailwind v4 CSS-first wiring, missing pieces); all DESIGN.md token hex values (`DESIGN.md` + `base.html :root`).
>
> **Inferred from patterns:** the browser SSE parser contract (fetch+ReadableStream over EventSource); the token-with-newline edge case; the `@theme` token-name → utility-name mapping; the recommendation that a plain client QueryProvider suffices for this client-heavy app.
>
> **Not checked (honest gaps):** the BE was not run, so `/openapi.json` was not generated or diffed against the schema reads — field names come from Pydantic source, not emitted JSON (a `gen:api` run could reveal serialization aliases/casing). SSE buffering through the Next proxy was not empirically reproduced (it is a documented risk, not an observed one here). openapi-typescript's exact installed Node floor and the TanStack `isServer` export were not verified against locally-installed versions (deps not yet added). Context7 MCP docs were unavailable; doc findings rest on WebFetch of official pages + live npm registry.
