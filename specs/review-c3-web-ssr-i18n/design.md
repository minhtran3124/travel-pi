# review-c3-web-ssr-i18n — Design

Status: approved by user 2026-09-08; amended 2026-09-08 after xia2 research (see `research-brief.md`).
The `loading.tsx` half was **removed** on empirical evidence — §3.1 records the measurement.
Lane: `normal` · Confidence: `medium` (see `SUMMARY.md`).
Parent: `specs/review-c-web-experience/` (child 3 of 3 per parent E001-A; c1 and c2 are `ready_to_merge`).

## 1. Purpose

Close the measurable half of deep-review item 12 for `apps/web`: no loading affordance on
navigation, English strings leaking through the app chrome, and no shareable per-language URL.

The review framed this as "no SSR". This design deliberately does **not** convert pages to server
components. Section 3 explains why, and names the condition under which that decision should be
revisited.

## 2. Constraints and non-goals

**Architectural constraint (decided).** The app keeps client-side data fetching. Every page is a
client component reading through TanStack Query against `/api/be`, and `lib/api/client.ts` attaches
the Supabase bearer via `authHeader()`, which returns `{}` server-side by design. Server-side data
fetching would require a new server auth path; that is an architecture change, not this slice.
Nothing here touches `authHeader()`, `lib/api/client.ts`, or the React Query provider.

**Out of scope, with reasons:**

| Excluded | Reason |
|---|---|
| `apps/web/src/app/auth/**` (login, sign-up, auth-code-error) | Owned by `specs/auth-pages-redesign/` (lane `high-risk`, Auth hard gate, `decision: pending`). All three pages have zero `useTranslations` — a full i18n pass belongs with the redesign that will rewrite them. Touching them here would also trip the block-mode `auth` gate at lane `normal`. |
| The "calm vs energetic" visual half (photography, coral token) | Parent E003-A: out of scope, design backlog. (An earlier draft of this section claimed `grep -rn coral apps/web/src` returns 0. That was wrong — it returns **21** non-test hits: the token is defined in `app/globals.css:31-34,109-111,168-170` and already used in `TripCard.tsx:61`, `TripHeader.tsx:188`, `SavedPlaceCard.tsx:58`, `AuthHero.tsx:122`, `tripVisuals.tsx:139`, both chat panels and both auth pages. The exclusion rests on E003-A alone, not on the token being unused.) |
| `[locale]` path segments, `hreflang`, locale-aware SEO | Section 4 chooses the query-param approach instead. Backlog note recorded there. |
| Server components / server prefetch / `HydrationBoundary` | Per the architectural constraint above. |

**Boundary note.** `components/auth/UserMenu.tsx` lives under `components/auth/` but is header
chrome rendered by `AppShell` on every page, not an auth *page*. It is in scope. The exclusion
above is by route (`src/app/auth/**`), not by directory name.

## 3. Loading: standardise the skeletons (no `loading.tsx`)

### 3.1 What was measured, and what it ruled out

An earlier revision of this design specified four `loading.tsx` files and built its case on the
claim that a nav click leaves the previous page on screen until the segment's client bundle
arrives, and that `loading.tsx` fills that gap. **That claim was tested against this app and is
false.**

Probe: two throwaway public routes on the running dev server (Next 16.2.9, real async root
layout), polling the DOM at 20 ms through the transition.

| `/probe-b` page | `<Link>` | Observed paint sequence | `loading.tsx` shown |
|---|---|---|---|
| client component, client-side wait | default prefetch | `["page-pending"]` | **no** |
| client component, client-side wait | `prefetch={false}` | `["page-pending","page-data"]` | **no** |
| **async server component**, `await` 1.5 s | `prefetch={false}` | `["loading-tsx","page-data"]` | **yes** |

Row 3 isolates the cause. It is not prefetching, and it is not the async root layout (the
documented `loading.js` caveat about layouts reading runtime data). `loading.tsx` is the Suspense
fallback for **server rendering of the segment**; a `"use client"` page with no server data never
suspends on the server, so the boundary resolves immediately and the fallback is never used.

**Therefore this slice ships no `loading.tsx`.** Under the client-fetch architecture fixed in §2,
those files would be inert: four components that never render, plus tests asserting a transition
that does not occur, plus a strong signal to the next reader that this app has SSR when it does
not.

**Revisit condition.** `loading.tsx` becomes meaningful the moment any of these pages does server
work — a server prefetch, an `await`ed server component, a `generateMetadata` that fetches. At
that point add it, and re-run the probe above rather than re-deriving the argument.

### 3.2 What is actually wrong today

The loading affordance is inconsistent, and two pages are worse than the other two:

| Page | Pending affordance today |
|---|---|
| `app/trips/page.tsx:105` | sr-only `role="status"` + an inline grid of 6 `TripCardSkeleton` — the good case |
| `app/trips/[tripId]/page.tsx:30-32` | early `return <TripHeaderSkeleton />` — header only, so the tab bar pops in afterwards |
| `app/bookings/page.tsx:119-122` | header/filters live, then a bare centred `<Spinner>` |
| `app/places/page.tsx:185-188` | header/filters live, then a bare centred `<Spinner>` |

Two pages place-hold with a shaped skeleton; two spin. That is the defect this section fixes.

### 3.3 Units

New directory `apps/web/src/components/skeletons/`. Every file in it is a pure presentational
unit: no `"use client"` directive, no `useTranslations`, no props, `aria-hidden="true"` on the
root. Text-free by rule, which keeps them out of the translation surface. (The no-props part
covers `components/skeletons/` only — `components/ui/Skeleton.tsx` is a styling primitive and takes
a `className`.)

| Unit | Contents | Source |
|---|---|---|
| `components/ui/Skeleton.tsx` | Block primitive: `animate-pulse` + `bg-panel-raised` + `rounded-sm`, `className` passthrough. Consumed by the four new skeleton files below; the two moved files are not refactored onto it | New; extracted from the repeated `<div className="h-4 w-20 rounded-sm bg-panel-raised" />` idiom (e.g. `TripHeader.tsx:241`) |
| `components/skeletons/TripCardSkeleton.tsx` | Card placeholder | **Moved** from `components/trips/TripCard.tsx` |
| `components/skeletons/TripHeaderSkeleton.tsx` | Trip header placeholder | **Moved** from `components/trips/TripHeader.tsx` |
| `components/skeletons/TripsGridSkeleton.tsx` | The grid wrapper + 6 × `TripCardSkeleton` | New |
| `components/skeletons/SavedPlacesGridSkeleton.tsx` | The grid wrapper + 6 card placeholders | New |
| `components/skeletons/BookingsTableSkeleton.tsx` | `div > table > tbody` matching `BookingTable.tsx:150-177` (including its `max-sm:block` responsive geometry) + 6 row placeholders | New |
| `components/skeletons/TripDetailPageSkeleton.tsx` | `TripHeaderSkeleton` + tab-bar shape | New |

**Why the container, not a bare row.** `BookingTable.tsx:150-177` renders `div > table > thead +
tbody`, so a `<tr>` placeholder dropped straight into a pending branch is invalid DOM nesting and
warns in React. Each list route's shared unit therefore owns its own wrapper. The two grid routes
follow the same shape for consistency.

**Why the two moves.** `TripCard.tsx` and `TripHeader.tsx` import `useTranslations` and
`useFormatter` from `next-intl` for their *other* exports, and neither carries a `"use client"`
directive. This is a robustness choice, **not** a compile necessity: next-intl v4's restriction is
that its hooks cannot be called from `async` components, and the skeleton exports call no hooks, so
importing those modules would not in fact fail. The move exists so the skeleton files carry zero
coupling to `next/link` and next-intl — which matters if these are ever pulled into a server graph
by the §3.1 revisit condition. Bodies are transplanted **verbatim**, so the move stays reviewable
as a pure move; importers are updated; nothing else in those two source files changes.

### 3.4 Page-side changes

Each page keeps its existing structure and changes only what it renders inside the branch it has:

| Page | After |
|---|---|
| `app/trips/page.tsx:105` | sr-only status + `TripsGridSkeleton` (the inline grid markup moves into that component) |
| `app/trips/[tripId]/page.tsx:30-32` | early `return <TripDetailPageSkeleton />` + sr-only status — the tab bar no longer pops in after the header |
| `app/bookings/page.tsx:119-122` | header/filters live, then `BookingsTableSkeleton` + sr-only status |
| `app/places/page.tsx:185-188` | header/filters live, then `SavedPlacesGridSkeleton` + sr-only status |

The two list pages branch on TanStack Query's `isLoading`, the other two on `isPending`; this
design changes neither, and "pending" is used as the generic word throughout.

`Spinner` is **not** removed and **not** merged into `Skeleton`. The two have different jobs:
`Skeleton` place-holds content whose shape is known; `Spinner` marks an in-place busy action (a
submitting button, a cancelling row). The nine remaining `Spinner` call sites keep it.

### 3.5 Screen-reader announcement

Skeletons are `aria-hidden` shapes, so the loading state must be announced separately or it is
silent for screen-reader users. Today only `/trips` does this (`app/trips/page.tsx:107-109`:
`<span role="status" className="sr-only">`), and the two `Spinner` sites being replaced carry
`role="status"` + a translated `aria-label` that would be lost with them.

The `/trips` pattern is therefore applied to all four pending branches, reusing each page's
existing translated loading key (`Trips.loadingTripsStatus`, `Places.loadingLabel`,
`Bookings.loadingLabel`) plus a new `TripDetail.loadingLabel`.

## 4. Shareable language URL: `?lang=` seeds the cookie

### 4.1 Contract

```
GET /trips?lang=vi   →  Set-Cookie: locale=vi  →  307  →  /trips
```

The locale mechanism itself is unchanged: `i18n/request.ts` keeps reading the `locale` cookie, and
`app/` keeps its current structure. `?lang=` is purely an entry point that writes that cookie.

### 4.2 First, migrate `middleware.ts` → `proxy.ts`

`middleware` is deprecated as of Next `v16.0.0` and renamed to `proxy`; the repo runs `next 16.2.9`
and the dev server emits the warning on every boot (observed in
`apps/web/.next/dev/logs/next-development.log`):

> `⚠ The "middleware" file convention is deprecated. Please use "proxy" instead.`

Because this slice adds logic to exactly that file, the rename lands **first, as its own commit**,
via the official codemod:

```bash
npx @next/codemod@canary middleware-to-proxy .
```

It renames `src/middleware.ts` → `src/proxy.ts` and the export `middleware` → `proxy`. The
`config.matcher` is unchanged. Proxy defaults to the Node.js runtime and the `runtime` config
option throws if set — the repo sets none. `src/lib/supabase/middleware.ts` keeps its filename:
the codemod targets the convention file, not an imported helper, and renaming a helper is
unrelated churn.

Doing this as commit 1 keeps a mechanical framework migration separable from the feature, and
means the feature is not written into a deprecated convention.

### 4.2b Composition order

```ts
// src/proxy.ts
export async function proxy(request: NextRequest) {
  const response = await updateSession(request)
  return applyLangParam(request, response)
}
```

Ordering is load-bearing. `lib/supabase/middleware.ts:50-52` carries an explicit warning against
running code between `createServerClient` and `getClaims()`; `applyLangParam` therefore operates
only on the finished response and never inside `updateSession`.

### 4.3 `applyLangParam` behaviour

New unit `apps/web/src/lib/i18n/langParam.ts`, exporting
`applyLangParam(request: NextRequest, response: NextResponse): NextResponse`.

"Already a redirect" means `response.status >= 300 && response.status < 400`.

| # | Case | Behaviour |
|---|---|---|
| 1 | No `lang` param | Return `response` untouched. |
| 2 | `lang` present but `!isLocale(lang)` | Return `response` untouched — no cookie, no redirect, param left in the URL. Chosen over "strip and redirect" because a no-op cannot loop. |
| 3 | Not a document navigation (see rule below) | Return `response` untouched. |
| 4 | `lang` valid, GET, `response` already a redirect | Set the locale cookie on that existing redirect and return it. **Do not** add a second redirect. |
| 5 | `lang` valid, GET, normal response | Build `NextResponse.redirect` to the same URL with only `lang` removed; copy every cookie from `response` onto it; set the locale cookie; return it. |

**Row 3 — what counts as a document navigation.** All three of the following must hold; otherwise
row 3 returns untouched:

1. `request.method === "GET"`;
2. `request.nextUrl.pathname` does not start with `/api/`;
3. `request.headers.get("sec-fetch-dest")` is `"document"` **or absent** (absent covers non-browser
   clients such as curl or a link unfurler, which are genuine navigations).

**Do not test `Next-Router-Prefetch` or `RSC` here.** An earlier revision did, and it cannot work:
the Next.js proxy docs state that *"During RSC requests, Next.js strips internal Flight headers
from the `request` instance in Proxy. For example, headers like `rsc`, `next-router-state-tree`,
and `next-router-prefetch` are not exposed through `request.headers`."* Such a condition would
silently never fire, and — worse — a unit test that constructs those headers by hand would pass
while production did the wrong thing. `Sec-Fetch-Dest` is a standard browser request header, not a
Flight header, and is not stripped; it is `document` for a navigation and `empty` for every
`fetch`/RSC/prefetch request, which is exactly the distinction needed.

The documented alternative — a `matcher` with `missing: [{type:'header',key:'next-router-prefetch'}]`
— is **not** usable here, because the matcher gates the entire proxy: excluding those requests
would also skip Supabase session refresh on them, trading a locale bug for a session bug.

Method alone is not sufficient, which an earlier draft got wrong. The `matcher` in `middleware.ts`
excludes only static assets, so middleware also sees:

- Server Action `POST`s, which submit to the *current page URL* (`signOut` via
  `<form action={signOut}>` at `UserMenu.tsx:108`) — caught by (1); a 307 preserves method and body,
  so redirecting one would replay the action.
- The `/api/be/:path*` rewrite (`next.config.ts`), which is overwhelmingly **GET** — caught by (2),
  not by (1).
- `next/link` RSC prefetches, also GET. Without (3), merely hovering a `?lang=vi` link would write
  the locale cookie and silently switch the user's language without a navigation.

Accepted consequence of (3): an in-app **soft** navigation to a `?lang=` URL (a client-side
`<Link href="/trips?lang=vi">` click, which sends the `RSC` header) is also suppressed and becomes
a silent no-op. No such link exists in the app today, and the feature's purpose is inbound shared
links, which are hard navigations. Recorded so that adding one later is not a mystery bug — such a
link should call `setUserLocale` directly instead.

`request.nextUrl.searchParams.get("lang")` returns `string | null` while
`isLocale(value: string | undefined)` takes `undefined`; the call site passes `?? undefined`.
Do **not** widen `isLocale` — it is the shared validator in `i18n/config.ts`.

**Cookie attributes must match `i18n/locale.ts` exactly**: name `LOCALE_COOKIE`, `path: "/"`,
`maxAge` one year, `sameSite: "lax"`. `applyLangParam` validates through `isLocale` before writing,
so no unknown value can reach the cookie *by this path*.

> Observed, not fixed here: the pre-existing writer does **not** validate.
> `LocaleSwitcher.tsx:22` casts with `event.target.value as Locale`, and `setUserLocale`
> (`i18n/locale.ts:15-22`) is a `"use server"` action that writes its argument straight through.
> Practical impact is nil because every *reader* falls back to `defaultLocale` via `isLocale`.
> Tightening that server action is unrelated to this slice and is left alone (behavioral rule 3).

**Supabase cookie preservation is mandatory.** `updateSession` may have rotated session cookies
onto its response. Returning a fresh redirect without copying them logs the user out — the exact
failure the existing auth-gate redirect already guards against at
`lib/supabase/middleware.ts:72-74`. `applyLangParam` follows that same copy pattern.

**Composition with the auth gate.** A signed-out visitor opening `/trips?lang=vi` hits the auth
redirect to `/auth/login?next=%2Ftrips%3Flang%3Dvi`. Row 4 sets the locale cookie on that redirect,
so the login page renders in Vietnamese, and `lang` survives inside `next` to be re-applied after
sign-in. No extra code: the two rules compose.

**Loop safety.** The redirect removes `lang`, so the follow-up request takes row 1. The `matcher`
in `middleware.ts` is unchanged.

### 4.4 Accepted trade-off

The final URL carries no locale, so this delivers shareability but not `hreflang` or per-language
indexing. Recorded as a backlog item; `[locale]` segments remain the upgrade path if SEO becomes a
requirement.

## 5. i18n leaks in the app chrome

Scope is the chrome only, per §2. The review counted three hardcoded `aria-label`s; a grep for
`aria-label="` misses expression forms, and the real in-scope set is different
(cf. `docs/solutions/harness/negative-grep-is-not-absence.md`).

| Site | String(s) | Action |
|---|---|---|
| `components/app-shell/AppShell.tsx:85` | `"Close menu"` / `"Open menu"` | → `Nav.menuClose` / `Nav.menuOpen`. Missed by the review's grep (expression form). |
| `components/auth/UserMenu.tsx:64,78,115` | `"Sign in"`, `aria-label="Account menu"`, `"Sign out"` | → new `Account` namespace: `signIn`, `menuLabel`, `signOut`. The component has **no** `useTranslations` today; this introduces it. Two are visible text, not just a11y. |
| `components/ui/Spinner.tsx:6` | `label = "Loading"` default | Remove the default; make `label` **required**. All 11 call sites already pass a translated label, so nothing breaks, and `tsc` now blocks a future caller from silently shipping English. |
| `components/chat/AgentAvatar.tsx:21` | `aria-label="Tin"` | **No change.** "Tin" is the assistant's brand name (`min-60-chatbot-branding`); it is correct in every locale. |
| `app/auth/login/page.tsx:70` | `aria-label="Sign-in method"` | **No change here.** Handed to `auth-pages-redesign` (§2) — that page has ~10 untranslated strings, not one. |

**Catalog delta — the complete set of new keys**, landing in both `messages/en.json` and
`messages/vi.json`:

| Namespace | Keys | Note |
|---|---|---|
| `Nav` | `menuOpen`, `menuClose` | namespace already exists |
| `Account` | `signIn`, `menuLabel`, `signOut` | **new** namespace |
| `TripDetail` | `loadingLabel` | required by the §3.2b live region; `TripDetail` today has no loading key of any kind |

`Trips.loadingTripsStatus`, `Places.loadingLabel` and `Bookings.loadingLabel` already exist and are
reused as-is. `src/messages.parity.test.ts` (T10) covers all six additions with no change.

## 6. Error behaviour

Unchanged in every case. This slice adds no new failure mode.

- Data errors keep rendering the existing `isError` branches (`EmptyState`, trip-detail error card).
  Skeletons cover *pending*, never *failed*.
- `app/error.tsx` and `app/not-found.tsx` already exist and are untouched.
- An invalid `?lang=` is not an error: it is ignored (§4.3 row 2), and the page renders in the
  currently-effective locale.
- An uncaught throw in the Next proxy returns a 500 for that request — it does **not** fail open.
  `applyLangParam` is therefore written to be total: it performs no I/O and reads only
  `request.method`, `request.nextUrl`, `request.headers`, `response.status` and `response.cookies`
  (row 5's copy step). `method`, `nextUrl` and `status` are always present; `request.headers` is
  always present as an object, and every header §4.3 row 3 consults is read through `.get()`, which
  returns `null` for a missing header — the absent case is a defined branch of the rule, not an
  error; `response.cookies` is always present on a `NextResponse`, with `.getAll()` returning `[]`.

## 7. Tests

All offline; no network, no live Supabase. Vitest for units, existing Playwright specs for
regression only.

**Use the framework's own proxy test utilities.** `next/experimental/testing/server` ships
`unstable_doesProxyMatch`, `isRewrite`, `getRewrittenUrl` and `getRedirectUrl` (since v15.1), and is
present in this repo at `apps/web/node_modules/next/experimental/testing/server.js`. T1–T5b use it
rather than hand-rolled `NextRequest` fixtures. It is marked experimental, so pin the usage to
those four helpers.

| # | Check | Where |
|---|---|---|
| T0 | After the §4.2 codemod: `src/proxy.ts` exists exporting `proxy`, `src/middleware.ts` is gone, and the dev server no longer logs the deprecation warning | `pnpm build` + a grep of the dev log; commit 1's own verify |
| T1 | `?lang=vi` sets the `locale` cookie with the same attributes as `setUserLocale`, and redirects to the URL without `lang` | `lib/i18n/langParam.test.ts` |
| T2 | Supabase cookies present on the incoming response are all carried onto the redirect | same |
| T3 | `?lang=xx` (unknown) sets no cookie and issues no redirect | same |
| T4 | A 3xx response in (auth gate) gets the cookie set and is returned as-is — exactly one redirect, not two | same |
| T5 | No `lang` param → the response is returned by identity | same |
| T5b | Row 3 suppression: a `POST` to a page URL, an `/api/be/*` path, and a request whose `sec-fetch-dest` is `empty` are each returned untouched. A sixth case asserts that a request with **no** `sec-fetch-dest` still redirects | same — added because §4.3 names row 3 as the sub-rule an earlier draft got wrong, and its regression is invisible in manual testing |
| T6 | `/bookings` and `/places` render their shared container skeleton (not a bare `Spinner`) while loading, with header and filter row still live; `/trips/[tripId]` renders `TripDetailPageSkeleton` including the tab bar | `app/{bookings,places,trips/[tripId]}/page.test.tsx` — **new**; `src/app/` has no page tests today |
| T7 | All four pending branches expose an sr-only `role="status"` live region (§3.5) | the four `app/**/page.test.tsx` |
| T8 | No bare-string `aria-label="…"` remains under `src/`, excluding `src/app/auth/**`, `AgentAvatar.tsx`, and `*.test.tsx` | `src/i18n/no-hardcoded-strings.test.ts` (new grep gate). The test exclusion is required, not cosmetic: `ChatWidget.test.tsx:39,63` and `ChatWidget.auth.test.tsx:43` use bare `aria-label`s as fixture selectors and are correct as-is |
| T8b | `components/app-shell/**` and `components/auth/UserMenu.tsx` contain no bare English *visible* string literal in JSX text position | same file — added because §5's real leak class included `"Sign in"`/`"Sign out"`, which an `aria-label`-only gate would not catch |
| T9 | `Spinner` has no caller omitting `label` | `pnpm exec tsc --noEmit` from `apps/web/` — `package.json` has no `typecheck` script, so the command is named in full |
| T10 | Both message catalogs carry identical key sets after the additions | `src/messages.parity.test.ts` — already exists; covers the new keys with no change |
| T11 | The two Playwright specs still pass | `pnpm e2e` — regression only, no new spec |

T8/T8b are what keep this design from decaying: they forbid the next hardcoded string. T8 alone
would have missed two of the five leaks §5 found, which is why T8b exists.

**No test asserts `loading.tsx` behaviour, because §3.1 removed it.** The probe that established
that decision is recorded in §3.1 as a table of measurements; it is not re-runnable as a unit test
and is not claimed to be.

## 8. Files touched

Paths are repo-real and relative to `apps/web/`.

**New — source (8):** `src/components/ui/Skeleton.tsx`; `src/components/skeletons/` ×6
(`TripCardSkeleton`, `TripHeaderSkeleton`, `TripsGridSkeleton`, `SavedPlacesGridSkeleton`,
`BookingsTableSkeleton`, `TripDetailPageSkeleton`); `src/lib/i18n/langParam.ts`.

**New — tests (6):** `src/lib/i18n/langParam.test.ts`;
`src/app/{trips,trips/[tripId],places,bookings}/page.test.tsx` (4);
`src/i18n/no-hardcoded-strings.test.ts`.

**Renamed (1):** `src/middleware.ts` → `src/proxy.ts` (codemod, §4.2), then edited to add the
`applyLangParam` call.

**Modified (11):** `src/components/trips/TripCard.tsx`; `src/components/trips/TripHeader.tsx`
(skeleton exports moved out of both); `src/app/{trips,trips/[tripId],places,bookings}/page.tsx`
(4 — import path / Spinner → container skeleton / sr-only status);
`src/components/app-shell/AppShell.tsx`; `src/components/auth/UserMenu.tsx`;
`src/components/ui/Spinner.tsx`; `messages/en.json`; `messages/vi.json`.

Total **26** files (8 + 6 + 1 + 11). The counts are stated exactly because
`hooks/blast-radius-check.sh` corroborates a task's declared Files set against the diff.

Untouched by design: `src/lib/api/client.ts`, `src/lib/supabase/middleware.ts` (keeps its
filename — see §4.2), `src/i18n/request.ts`, `src/i18n/config.ts`, `src/i18n/locale.ts`,
`src/components/app-shell/LocaleSwitcher.tsx`, `src/app/auth/**`, `src/app/layout.tsx`,
`src/app/globals.css`, `next.config.ts`, everything under `apps/api/`.

No backend change. No public API contract change. No migration.

**Unrelated dead code, noticed and deliberately not touched:** `src/components/auth/SignOutButton.tsx`
has zero importers. Removing it is not part of this slice (behavioral rule 3).
