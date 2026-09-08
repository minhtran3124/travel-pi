---
slug: review-c3-web-ssr-i18n
status: active
owner: Minh Tran
created: 2026-09-08
---

# Web chrome: skeletons, shareable language URL, chrome i18n

## 1. Motivation

Deep-review item 12, measurable half. Two of four pages place-hold with a shaped skeleton and two
spin; the app chrome leaks English through `aria-label`s and two visible strings; a chosen locale
lives only in a cookie, so no link can carry it. `design.md` §3.1 records the measurement that
removed the `loading.tsx` half of the original scope: it never paints for a client-fetch page.

## 2. Non-goals

- No `loading.tsx`. Measured inert under the client-fetch architecture (`design.md` §3.1).
- No server components, server prefetch, or server auth path. `authHeader()` and
  `lib/api/client.ts` are untouched.
- No `src/app/auth/**` changes. Owned by `specs/auth-pages-redesign/` (Auth hard gate, pending).
- No `[locale]` path segments, `hreflang`, or locale-aware SEO.
- No visual refresh (photography, coral token). Parent E003-A.
- `components/auth/SignOutButton.tsx` is dead code; it stays.

## Global Constraints

- Node 24 for every FE command: `export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH"`.
  The `nvm` default is 18 and pnpm 11 requires Node >= 22.13.
- Every `Verify` and Success-Criteria check is written to be run from the **repository root**.
  Rows that need the workspace begin `cd apps/web && …`; rows that only read a file use a
  root-relative `apps/web/...` path. Do not `cd` first and then run a root-relative row.
- Skeleton components under `src/components/skeletons/` carry no `"use client"` directive, no
  `next-intl` import, no props, and `aria-hidden="true"` on the root.
- Every `src/components/skeletons/` root also carries `data-testid="<kebab-case component name>"`
  (e.g. `data-testid="bookings-table-skeleton"`). This is a deliberate exception to the no-props
  rule and it is load-bearing: the roots are `aria-hidden` and text-free, so React Testing Library
  has no other query for them and each wave-4 implementer would otherwise invent a different
  handle.
- `applyLangParam` performs no I/O and never runs between `createServerClient` and `getClaims()`.
- Never read `rsc`, `next-router-prefetch`, or `next-router-state-tree` from `request.headers`:
  Next strips them in proxy. Use `sec-fetch-dest`.
- Any redirect built in the proxy copies every cookie off the response it replaces, or the
  Supabase session is lost.
- Stage and commit as separate commands (PreToolUse hook blocks compound `git add … && git commit`).
- No `Co-Authored-By: Claude` / `Claude-Session:` / `Generated with` trailers in commit messages.

## 3. Success Criteria

Every row names **exactly one** test file, or a command that cannot pass on an empty scan. This is
deliberate: measured on this repo (vitest 2.1.9), `vitest run fileA fileB` exits **0** when only
`fileA` matches, and `-t "<name that matches nothing>"` also exits 0 — but a single filter that
matches no file exits **1**. `--passWithNoTests` is set only on the `test` npm script, not in
`vitest.config.ts`, so `pnpm exec vitest run` does not inherit it.

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|------|-------------------------|-----------------------|------------|
| SC-1 | The proxy convention file is `src/proxy.ts` exporting `proxy`, and `src/middleware.ts` no longer exists | `test ! -f apps/web/src/middleware.ts && grep -q "export async function proxy" apps/web/src/proxy.ts` | exit 0 |
| SC-2 | `?lang=vi` writes the locale cookie with `setUserLocale`'s attributes and redirects to the same URL without `lang`; an unknown value writes nothing | `cd apps/web && pnpm exec vitest run src/lib/i18n/langParam.seed.test.ts` | exit 0 |
| SC-3 | A Supabase cookie on the incoming response survives onto the redirect, and an auth-gate 3xx gets the cookie without a second redirect | `cd apps/web && pnpm exec vitest run src/lib/i18n/langParam.cookies.test.ts` | exit 0 |
| SC-4 | A POST, a HEAD, an `/api/be/*` path, and `sec-fetch-dest` values `empty` and `image` are each returned untouched; a request with no `sec-fetch-dest` still redirects | `cd apps/web && pnpm exec vitest run src/lib/i18n/langParam.suppression.test.ts` | exit 0 |
| SC-5 | `/trips` renders the grid skeleton and an sr-only live region while pending | `cd apps/web && pnpm exec vitest run src/app/trips/page.test.tsx` | exit 0 |
| SC-6 | `/trips/[tripId]` renders the tab-bar shape, not the header alone, and an sr-only live region while pending | `cd apps/web && pnpm exec vitest run "src/app/trips/[tripId]/page.test.tsx"` | exit 0 |
| SC-7 | `/bookings` renders the table skeleton with no spinner, keeps its filter row live, and exposes an sr-only live region while loading | `cd apps/web && pnpm exec vitest run src/app/bookings/page.test.tsx` | exit 0 |
| SC-8 | `/places` renders the grid skeleton with no spinner, keeps its filter row live, and exposes an sr-only live region while loading | `cd apps/web && pnpm exec vitest run src/app/places/page.test.tsx` | exit 0 |
| SC-9 | All six new keys are present in **both** catalogs, and the two catalogs carry identical key sets | `cd apps/web && node -e "const f=require('fs'),n=['Nav.menuOpen','Nav.menuClose','Account.signIn','Account.menuLabel','Account.signOut','TripDetail.loadingLabel'];for(const p of ['messages/en.json','messages/vi.json']){const j=JSON.parse(f.readFileSync(p));for(const k of n){const s=k.split('.');if(!j[s[0]]||!j[s[0]][s[1]])throw new Error(p+' missing '+k)}}" && pnpm exec vitest run src/messages.parity.test.ts` | exit 0 |
| SC-10 | The hardcoded-string gate scans a non-zero number of files, passes on the tree, and rejects a known-bad fixture | `cd apps/web && pnpm exec vitest run src/i18n/no-hardcoded-strings.test.ts` | exit 0 |
| SC-11 | No `Spinner` caller omits `label`, and the whole workspace type-checks | `cd apps/web && pnpm exec tsc --noEmit` | exit 0 |
| SC-12 | The composed proxy preserves rotated Supabase session cookies on every branch of `applyLangParam`, including the one that returns a new response | `cd apps/web && pnpm exec vitest run src/proxy.test.ts` | exit 0 |

## 4. Tasks

### Task 1.1 — Migrate the proxy convention file (wave 1)

- **Files:** apps/web/src/middleware.ts, apps/web/src/proxy.ts
- **Action:** Run the official codemod from `apps/web/`:
  `npx @next/codemod@canary middleware-to-proxy .`
  It renames `src/middleware.ts` to `src/proxy.ts` and the export `middleware` to `proxy`.
  Leave `config.matcher` unchanged. Do **not** rename `src/lib/supabase/middleware.ts`: the
  codemod targets the convention file, not an imported helper.
  Set no `runtime` config — Proxy defaults to Node.js and the option throws if set.
  This lands first and alone because every later task in §4 edits this file, and because
  `middleware` is deprecated as of Next `v16.0.0` (the dev server logs the warning on boot).
- **Verify:** `test ! -f apps/web/src/middleware.ts && grep -q "export async function proxy" apps/web/src/proxy.ts`
- **Done:** `src/proxy.ts` exports `proxy`, `src/middleware.ts` is absent, `config.matcher` is byte-identical to its previous value.
- **Criteria:** SC-1
- **Interfaces:** Consumes the pre-existing src/middleware.ts convention file. Produces `apps/web/src/proxy.ts`.

### Task 2.1 — `applyLangParam` and its unit tests (wave 2)

- **Files:** apps/web/src/lib/i18n/langParam.ts, apps/web/src/lib/i18n/langParam.seed.test.ts, apps/web/src/lib/i18n/langParam.cookies.test.ts, apps/web/src/lib/i18n/langParam.suppression.test.ts
- **Action:** Write the tests first, then the function.
  Export `applyLangParam(request: NextRequest, response: NextResponse): NextResponse`
  implementing `design.md` §4.3 rows 1-5 in order:
  no `lang` → return `response`; `!isLocale(lang)` → return `response`; not a document navigation
  → return `response`; valid + document + `response.status` in [300,400) → set the cookie on
  `response` and return it; otherwise build `NextResponse.redirect` to the same URL minus `lang`,
  copy every cookie from `response` onto it, set the locale cookie, return it.
  A document navigation requires all of: `request.method === "GET"`; `pathname` does not start
  with `/api/`; `request.headers.get("sec-fetch-dest")` is `"document"` or `null`.
  Read the param as `searchParams.get("lang") ?? undefined` — do not widen `isLocale`.
  Cookie attributes must equal `i18n/locale.ts:17-21`: `path: "/"`, one-year `maxAge`,
  `sameSite: "lax"`.
  Split the tests across **three files** — `langParam.seed.test.ts` (rows 1, 2, 5),
  `langParam.cookies.test.ts` (rows 4, 5 cookie carry-over) and `langParam.suppression.test.ts`
  (row 3). Do **not** use one file with `vitest -t` name filters: measured on this repo
  (vitest 2.1.9), `vitest run <file> -t "<name that matches nothing>"` reports "skipped" and
  **exits 0**, so a renamed block would turn SC-2/SC-3/SC-4 green while asserting nothing. A
  missing *file* exits 1, so file-per-criterion fails loudly instead.
  Chain three single-file runs in this task's Verify too — a *directory* filter is a substring
  match and exits 0 when only one of the three files exists, which is the same defect the split is
  there to prevent.
  `langParam.suppression.test.ts` covers exactly six cases: (a) `POST` to a page URL → untouched;
  (b) `HEAD` → untouched; (c) GET `/api/be/trips?lang=vi` → untouched; (d) GET with
  `sec-fetch-dest: empty` → untouched; (e) GET with `sec-fetch-dest: image` → untouched;
  (f) GET with **no** `sec-fetch-dest` header → redirects with the cookie set.
  Use `next/experimental/testing/server` helpers (`getRedirectUrl`) rather than hand-rolled
  fixtures. Never construct `rsc` or `next-router-prefetch` headers in a test: Next strips them
  in production, so such a test would pass while production did the opposite.
- **Verify:** `cd apps/web && pnpm exec vitest run src/lib/i18n/langParam.seed.test.ts && pnpm exec vitest run src/lib/i18n/langParam.cookies.test.ts && pnpm exec vitest run src/lib/i18n/langParam.suppression.test.ts`
- **Done:** All three files exist and pass; `langParam.suppression.test.ts` contains exactly the six cases (a)-(f) listed in the Action, five asserting the response is returned by identity and case (f) asserting a redirect whose `Set-Cookie` names `locale`.
- **Criteria:** SC-2, SC-3, SC-4
- **Interfaces:** Consumes the pre-existing isLocale validator and LOCALE_COOKIE constant from src/i18n/config.ts. Produces `apps/web/src/lib/i18n/langParam.ts`, `apps/web/src/lib/i18n/langParam.seed.test.ts`, `apps/web/src/lib/i18n/langParam.cookies.test.ts`, `apps/web/src/lib/i18n/langParam.suppression.test.ts`.

### Task 2.2 — i18n the app chrome (wave 2)

- **Files:** apps/web/src/components/app-shell/AppShell.tsx, apps/web/src/components/auth/UserMenu.tsx, apps/web/messages/en.json, apps/web/messages/vi.json
- **Action:** Add to both catalogs: `Nav.menuOpen`, `Nav.menuClose`; a new `Account` namespace with
  `signIn`, `menuLabel`, `signOut`; and `TripDetail.loadingLabel` (consumed by Task 4.1).
  In `AppShell.tsx:85` replace the `menuOpen ? "Close menu" : "Open menu"` expression with the two
  `Nav` keys via the existing `useTranslations("Nav")`.
  In `UserMenu.tsx` introduce `useTranslations("Account")` — the component has none today — and
  replace `"Sign in"` (:64), `aria-label="Account menu"` (:78) and `"Sign out"` (:115).
  Leave `AgentAvatar.tsx:21` (`aria-label="Tin"`) unchanged: "Tin" is the assistant's brand name.
  Leave `src/app/auth/**` unchanged.
- **Verify:** `cd apps/web && node -e "const f=require('fs'),n=['Nav.menuOpen','Nav.menuClose','Account.signIn','Account.menuLabel','Account.signOut','TripDetail.loadingLabel'];for(const p of ['messages/en.json','messages/vi.json']){const j=JSON.parse(f.readFileSync(p));for(const k of n){const s=k.split('.');if(!j[s[0]]||!j[s[0]][s[1]])throw new Error(p+' missing '+k)}}" && pnpm exec vitest run src/messages.parity.test.ts`
- **Done:** The key-presence assertion exits 0 for all six keys in both catalogs, and the parity test passes. The parity test alone is not sufficient — it compares the two catalogs to each other and exits 0 on a tree where none of the six keys exists, so it cannot prove this task did anything. A missing `TripDetail.loadingLabel` would otherwise surface only at runtime, because Tasks 4.1-4.3 mock `next-intl`; no bare English string literal remains in `AppShell.tsx` or `UserMenu.tsx`; `src/app/auth/**` is untouched in the diff.
- **Criteria:** SC-9
- **Interfaces:** Consumes the pre-existing Nav namespace in both catalogs. Produces `apps/web/messages/en.json`, `apps/web/messages/vi.json`.

### Task 2.3 — Make `Spinner.label` required (wave 2)

- **Files:** apps/web/src/components/ui/Spinner.tsx
- **Action:** Remove the `= "Loading"` default on line 6 and make `label` a required prop in
  `SpinnerProps`. All eleven current call sites already pass a translated label, so no call site
  changes; the type now blocks a future caller from shipping an English default.
- **Verify:** `grep -q "label: string;" apps/web/src/components/ui/Spinner.tsx && ! grep -q "Loading" apps/web/src/components/ui/Spinner.tsx`
- **Done:** `SpinnerProps.label` is declared `string` with no `?`, and the literal `Loading` no longer appears in the file. The project-wide type-check that proves no caller broke is SC-11, run once at the end rather than per task, so two same-wave tasks never race a shared checkout.
- **Criteria:** SC-11
- **Interfaces:** Consumes nothing. Produces `apps/web/src/components/ui/Spinner.tsx`.

### Task 3.1 — Skeleton primitive and components (wave 3)

- **Files:** apps/web/src/components/ui/Skeleton.tsx, apps/web/src/components/skeletons/TripCardSkeleton.tsx, apps/web/src/components/skeletons/TripHeaderSkeleton.tsx, apps/web/src/components/skeletons/TripsGridSkeleton.tsx, apps/web/src/components/skeletons/SavedPlacesGridSkeleton.tsx, apps/web/src/components/skeletons/BookingsTableSkeleton.tsx, apps/web/src/components/skeletons/TripDetailPageSkeleton.tsx, apps/web/src/components/trips/TripCard.tsx, apps/web/src/components/trips/TripHeader.tsx, apps/web/src/app/trips/page.tsx, apps/web/src/app/trips/[tripId]/page.tsx
- **Action:** Add `components/ui/Skeleton.tsx`: a block primitive rendering `animate-pulse`
  `bg-panel-raised` `rounded-sm` with a `className` passthrough.
  Move `TripCardSkeleton` out of `TripCard.tsx` and `TripHeaderSkeleton` out of `TripHeader.tsx`
  into their own files under `components/skeletons/`, bodies transplanted **verbatim** so the move
  stays reviewable as a move. Update the import statement in each of the two consuming pages —
  `app/trips/page.tsx` and `app/trips/[tripId]/page.tsx` — and change nothing else in those four
  files. The two pages are in this task's Files set because removing an export without updating
  its importers does not compile; their *rendering* changes belong to Task 4.1.
  This task runs alone in its wave: its verify is a project-wide type-check, which would race a
  same-wave task mid-edit on the shared checkout.
  Add four new components, each owning its own wrapper element so no caller can supply a
  different one: `TripsGridSkeleton` (grid wrapper + 6 `TripCardSkeleton`),
  `SavedPlacesGridSkeleton` (grid wrapper + 6 card placeholders),
  `BookingsTableSkeleton` (`div > table > tbody` mirroring `BookingTable.tsx:150-177` including
  its `max-sm:block` classes, + 6 row placeholders), and `TripDetailPageSkeleton`
  (`TripHeaderSkeleton` + a tab-bar shape).
  `BookingsTableSkeleton` owning the `<table>` is load-bearing: a bare `<tr>` in a pending branch
  is invalid DOM nesting and warns in React.
  Give every root a `data-testid`, exactly: `trip-card-skeleton`, `trip-header-skeleton`,
  `trips-grid-skeleton`, `saved-places-grid-skeleton`, `bookings-table-skeleton`,
  `trip-detail-page-skeleton`. Wave 4 asserts on these exact strings.
- **Verify:** `cd apps/web && pnpm exec tsc --noEmit`
- **Done:** Seven files exist under `components/{ui,skeletons}/`; each `components/skeletons/` file contains no `use client`, no `next-intl` import, and both `aria-hidden="true"` and its assigned `data-testid` on its root; `TripCard.tsx` and `TripHeader.tsx` no longer export a skeleton; the type-check reports zero errors.
- **Criteria:** SC-5, SC-6, SC-7, SC-8
- **Interfaces:** Consumes the pre-existing skeleton markup inside components/trips/TripCard.tsx and components/trips/TripHeader.tsx. Produces `apps/web/src/components/skeletons/TripsGridSkeleton.tsx`, `apps/web/src/components/skeletons/BookingsTableSkeleton.tsx`, `apps/web/src/components/skeletons/SavedPlacesGridSkeleton.tsx`, `apps/web/src/components/skeletons/TripDetailPageSkeleton.tsx`, `apps/web/src/components/ui/Skeleton.tsx`.

### Task 4.1 — Trips pages: container skeleton and live region (wave 4)

- **Files:** apps/web/src/app/trips/page.tsx, apps/web/src/app/trips/[tripId]/page.tsx, apps/web/src/app/trips/page.test.tsx, apps/web/src/app/trips/[tripId]/page.test.tsx
- **Action:** In `trips/page.tsx` replace the inline grid at :110 with `<TripsGridSkeleton />`,
  keeping the existing sr-only `role="status"` region at :107-109 as-is (:105 is the `isPending ?`
  branch opener, :106 the fragment).
  In `trips/[tripId]/page.tsx:30-32` return `<TripDetailPageSkeleton />` instead of
  `<TripHeaderSkeleton />` so the tab bar no longer appears only after the header resolves, and add
  an sr-only `role="status"` region using the new `TripDetail.loadingLabel` key from Task 2.2.
  Add the two page tests. `src/app/` has no page tests today, so establish the harness here:
  mock the TanStack Query hook and `next-intl`, and for the detail page also `useParams`.
  Chain two single-file runs rather than passing both paths to one `vitest run`: a multi-filter
  invocation exits 0 when only a subset of its filters match (measured), so one missing file would
  pass silently.
- **Verify:** `cd apps/web && pnpm exec vitest run src/app/trips/page.test.tsx && pnpm exec vitest run "src/app/trips/[tripId]/page.test.tsx"`
- **Done:** The trips list test asserts `getByTestId("trips-grid-skeleton")` resolves while pending; the detail test asserts `getByTestId("trip-detail-page-skeleton")` resolves while pending; both assert an element with `role="status"` carrying the `sr-only` class.
- **Criteria:** SC-5, SC-6
- **Interfaces:** Consumes `apps/web/src/components/skeletons/TripsGridSkeleton.tsx`, `apps/web/src/components/skeletons/TripDetailPageSkeleton.tsx` and `apps/web/messages/en.json`. Produces `apps/web/src/app/trips/page.test.tsx`, `apps/web/src/app/trips/[tripId]/page.test.tsx`.

### Task 4.2 — Bookings page: table skeleton and live region (wave 4)

- **Files:** apps/web/src/app/bookings/page.tsx, apps/web/src/app/bookings/page.test.tsx
- **Action:** Replace the bare centred `<Spinner>` at `:119-122` with `<BookingsTableSkeleton />`
  plus an sr-only `role="status"` region using the existing `Bookings.loadingLabel` key. The
  header and filter row stay live during loading — do not hoist the branch to a whole-page return.
  Add the page test using the harness pattern from Task 4.1.
- **Verify:** `cd apps/web && pnpm exec vitest run src/app/bookings/page.test.tsx`
- **Done:** The test asserts `getByTestId("bookings-table-skeleton")` resolves while `isLoading`; that the branch contains no element with the `animate-spin` class (stated as the class, not as `role="status"`, because the new sr-only live region also carries `role="status"`); that the filter row is still rendered; and that an element with `role="status"` carrying the `sr-only` class exists.
- **Criteria:** SC-7
- **Interfaces:** Consumes `apps/web/src/components/skeletons/BookingsTableSkeleton.tsx`. Produces `apps/web/src/app/bookings/page.test.tsx`.

### Task 4.3 — Places page: grid skeleton and live region (wave 4)

- **Files:** apps/web/src/app/places/page.tsx, apps/web/src/app/places/page.test.tsx
- **Action:** Replace the bare centred `<Spinner>` at `:185-188` with `<SavedPlacesGridSkeleton />`
  plus an sr-only `role="status"` region using the existing `Places.loadingLabel` key. The header
  and filter row stay live during loading.
  Add the page test using the harness pattern from Task 4.1.
- **Verify:** `cd apps/web && pnpm exec vitest run src/app/places/page.test.tsx`
- **Done:** The test asserts `getByTestId("saved-places-grid-skeleton")` resolves while `isLoading`; that the branch contains no element with the `animate-spin` class (stated as the class, not as `role="status"`, because the new sr-only live region also carries `role="status"`); that the filter row is still rendered; and that an element with `role="status"` carrying the `sr-only` class exists.
- **Criteria:** SC-8
- **Interfaces:** Consumes `apps/web/src/components/skeletons/SavedPlacesGridSkeleton.tsx`. Produces `apps/web/src/app/places/page.test.tsx`.

### Task 5.1 — Wire `applyLangParam` into the proxy (wave 5)

- **Files:** apps/web/src/proxy.ts
- **Action:** Compose the two steps in `proxy`, with `updateSession` first:
  `const response = await updateSession(request); return applyLangParam(request, response)`.
  `applyLangParam` runs only on the finished response — never between `createServerClient` and
  `getClaims()`, per the warning at `lib/supabase/middleware.ts:50-52`.
  Leave `config.matcher` unchanged.
- **Verify:** `grep -q "applyLangParam(request, response)" apps/web/src/proxy.ts && cd apps/web && pnpm exec tsc --noEmit`
- **Done:** `src/proxy.ts` contains the literal call `applyLangParam(request, response)`; `config.matcher` is unchanged; `src/lib/supabase/middleware.ts` is absent from the diff; the project-wide type-check reports zero errors. The grep is here because re-running the `langParam` tests would pass identically whether or not this task edited `proxy.ts` — they import `langParam.ts` only. The type-check is here because this is the last task that changes source, and Task 3.1's wave-3 run predates six new files and three edited pages.
- **Criteria:** SC-1, SC-11
- **Interfaces:** Consumes `apps/web/src/lib/i18n/langParam.ts` and `apps/web/src/proxy.ts`. Produces the wired `apps/web/src/proxy.ts`.

### Task 6.1 — Hardcoded-string gate (wave 6)

- **Files:** apps/web/src/i18n/no-hardcoded-strings.test.ts
- **Action:** Add a test that scans `src/` and fails on either leak class.
  First: any bare-string `aria-label="…"`, excluding `src/app/auth/**` (owned by
  `auth-pages-redesign`), `components/chat/AgentAvatar.tsx` (brand name), and `*.test.tsx` —
  the test exclusion is required, since `ChatWidget.test.tsx:39,63` and
  `ChatWidget.auth.test.tsx:43` use bare `aria-label`s as fixture selectors and are correct.
  Second: any bare English visible string literal in JSX text position under
  `components/app-shell/**` or in `components/auth/UserMenu.tsx`. This second class exists
  because an `aria-label`-only gate would have missed `"Sign in"` and `"Sign out"`.
  This runs in its own wave, after Task 5.1's type-check, so the gate scans a finished tree.
  The gate must additionally assert, **per detector, not once for the test**:
  (a) that the detector's own scanned-file count is greater than zero, and
  (b) that the detector flags an inline known-bad fixture — `<button aria-label="Close menu">` for
  detector 1, and `<span>Sign out</span>` for detector 2.
  Both are required for both detectors. Detector 1's `src/` scan would satisfy a single
  test-wide file-count assertion on its own, hiding a detector 2 whose glob resolves to nothing;
  and after Task 2.2 lands the tree contains **no** specimen of detector 2's class, so without its
  own positive control a no-op detector 2 finds zero violations and the gate still exits 0. That
  matters here specifically: detector 2 exists because an `aria-label`-only gate missed
  `"Sign in"` and `"Sign out"` (`design.md` §7 T8b).
- **Verify:** `cd apps/web && pnpm exec vitest run src/i18n/no-hardcoded-strings.test.ts`
- **Done:** For each of the two detectors the test asserts: its scanned-file count is greater than zero; it returns zero violations across the tree; and it returns exactly one violation for its own inline fixture (`<button aria-label="Close menu">` for detector 1, `<span>Sign out</span>` for detector 2). Six assertions total, all in the one file SC-10 runs.
- **Criteria:** SC-10
- **Interfaces:** Consumes the chrome i18n keys added to both catalogs in Task 2.2. Produces `apps/web/src/i18n/no-hardcoded-strings.test.ts`.

### Task 6.2 — Standing test for the proxy composition (wave 6)

- **Files:** apps/web/src/proxy.test.ts
- **Action:** Add the first test that actually loads `src/proxy.ts`, so the composition is covered
  by something other than a grep.
  Mock `@supabase/ssr` so `getClaims()` invokes `setAll()` with rotated `sb-*-auth-token` cookies,
  then call `proxy()` directly and assert those cookies survive on **every** branch of
  `applyLangParam`: no `lang`; an unknown `lang`; a non-document request; the auth-gate 307; and
  the row-5 case that builds a **new** `NextResponse.redirect`. The last one is the point of the
  test — it is the only path that discards the object `updateSession` returned.
  Assert attributes, not just name/value: a copy that drops `HttpOnly` or `Max-Age` is still a
  broken session.
  The file needs `// @vitest-environment node`. Under jsdom, `NextResponse.next({ request })`
  throws on `Headers`.
  **Added mid-execution** under `rules/auto-correct-scope.md` Rule 2: the plan's §5 names session
  loss as the top risk and claimed SC-3 covered it, but SC-3 exercises `langParam.ts` in isolation.
  The three `langParam.*.test.ts` files import that module directly and never load the proxy, so
  they pass identically whether or not the wiring exists. A task-5.1 reviewer proved the
  composition correct at runtime, but deleted the proof.
- **Verify:** `cd apps/web && pnpm exec vitest run src/proxy.test.ts`
- **Done:** The file exists, declares the node environment, and contains five cases — one per
  `applyLangParam` branch — each asserting a rotated `sb-` cookie is present on the returned
  response with its `HttpOnly` and `Max-Age` attributes intact. Removing the cookie-copy loop from
  `langParam.ts` turns the row-5 case red.
- **Criteria:** SC-12
- **Interfaces:** Consumes `apps/web/src/proxy.ts`. Produces `apps/web/src/proxy.test.ts`.

## 5. Risks

- **Session loss.** `applyLangParam` returns a new response object in row 5. Missing the cookie
  copy logs every user out. Mitigated by SC-3 and by following the in-repo pattern at
  `lib/supabase/middleware.ts:72-74`.
- **A test that passes while production does the opposite.** Constructing `rsc` or
  `next-router-prefetch` headers in a unit test is possible even though Next strips them in the
  real proxy. The Global Constraints forbid it; Task 2.1 restates it.
- **New test territory.** `src/app/` has no page tests today. Task 4.1 establishes the mock
  harness and 4.2 / 4.3 copy it; if 4.1 slips, wave 4 serialises.
- **Codemod on the auth entry point.** Task 1.1 renames the file that refreshes every session. It
  is mechanical and lands alone so a revert is one commit.
- **Item 12 stays open.** "0 `loading.tsx`" remains true after this plan, by decision
  (`design.md` §3.1). Closing it requires the RSC fork, which is a separate high-risk spec.

## 6. Checks that deliberately sit outside the SC table

Two checks from `design.md` §7 are real but cannot be Success-Criteria rows, because an SC check
must finish in under 60 s and must never be a whole suite. They run at
`finishing-a-development-branch` and are named here so they are not silently dropped:

- **`cd apps/web && pnpm build`** — the only check that proves Next actually picks up the renamed
  `src/proxy.ts` convention file. `tsc --noEmit` cannot: it type-checks the module but knows
  nothing about file-system conventions. Run it after wave 1 and again before opening the PR.
- **`cd apps/web && pnpm e2e`** — the two existing Playwright specs, as regression only. No task
  adds or edits a spec; the plan's claim is that they still pass, not that they cover new ground.

## 7. Status Log

- 2026-09-08 — tasks 6.1, 6.2 complete; commits e922573, 62a625f, plus a8e24b1 applying review
  findings. Suite 47 files / 246 tests, `tsc` exit 0, `pnpm lint` 0 errors, `pnpm build` still
  lists the Proxy entry. All 12 success criteria hold. Review: pass/approved.
  The reviewer replicated both detector regexes in a scratch script and ran 15 realistic
  TS/JSX constructs against the generics strip — nested generics, `<T,>`, `<Select<Option>/>`,
  `title="a > b"`, `a.length<b.length && c>d` — and every one still flags a leak, so the
  false-positive fix is a precision fix and not a blind spot. It also injected real leaks into two
  real files and ran three mutations against the proxy test, including unwiring `proxy.ts`.
  Three Minors, all fixed in a8e24b1. The substantive one: the proxy cases named for rows 1-3
  asserted only that the session cookie survived, which row 5 also satisfies — so a guard falling
  through would have left them green while the named branch was never taken. They now assert no
  redirect was built, proven by making the row-2 guard fall through.
  Declined, with reason: widening the string gate to all of `components/auth/` (the reviewer's
  first option for the SignOutButton gap). That directory holds `AuthHero.tsx` and
  `OAuthButtons.tsx`, both with zero `useTranslations`, belonging to the auth surface owned by
  `auth-pages-redesign` behind an Auth hard gate. Widening would make the gate fire on files this
  slice must not touch. The gap is documented in the test instead.

- 2026-09-08 — task 5.1 complete; commit 74ffd25 (3 lines). Verify exit 0, suite 45/235,
  `pnpm build` still lists the Proxy entry, `config.matcher` byte-identical to its pre-rename
  value. Review: pass/approved, no findings — the reviewer mocked `@supabase/ssr` and traced a
  rotated session cookie through all five `applyLangParam` branches, including the row-5 path that
  returns a new response; attributes survive, not just name/value.
  That review also surfaced a coverage boundary rather than a defect: nothing checked in loads
  `src/proxy.ts`, so the composition was protected only by the Verify grep. Task 6.2 was added to
  close it (Rule 2, declared).

- 2026-09-08 — tasks 4.1, 4.2, 4.3 complete; commits f058cd8, 669703f, 95045ad, plus 82b8274
  applying review findings. Suite 45 files / 235 tests, `tsc --noEmit` exit 0; SC-5 to SC-8 each
  pass as a single-file run.
  Reviews: all three pass/approved. Reviewers ran 16 mutations between them and 15 bit.
  The one that did not is the finding that mattered: replacing `t("loadingLabel")` with a
  hardcoded English string left the trip-detail test green, because `next-intl` is mocked as an
  identity function and no test asserted on the rendered text. Fixing it revealed the gap was on
  all four pages, not only the page that happened to be mutated — each is now negative-controlled.
  Second Minor, accepted and fixed: the places spinner assertion was page-wide and passed only
  because `BrowseDrawer` was closed; it is now scoped to the loading region. The bookings query
  stays page-wide by choice — that page has no second spinner, so it is not brittle.

- 2026-09-08 — task 3.1 complete; commit 4aed124 (11 files, +178/-50). `tsc --noEmit` exit 0,
  suite 41 files / 228 tests. Review: spec pass / quality approved.
  One Minor accepted as-is: the moved `TripCardSkeleton` doc comment changed
  `{@link TripCard}` to plain `TripCard`, so the move is not byte-for-byte. The edit is correct —
  `TripCard` is not imported in the new file, so the link would dangle — but the implementer
  report's claim that the only delta was `data-testid` was inaccurate, and the controller's own
  spot-check could not have caught it: its `sed` range began at the `export` line, placing the
  preceding doc comment outside the compared text. Recorded so the next reviewer of a "verbatim
  move" compares whole files, not symbol bodies.

- 2026-09-08 — tasks 2.1, 2.2, 2.3 complete; commits 1554be7, c4f69ba, 3d14594, plus b1850d5
  applying review findings. Suite after the wave: 41 files / 228 tests pass, `tsc --noEmit`
  exit 0 (closes the reviewer's Minor note on SC-11 at task scope).
  Reviews: 2.2 pass/approved with no findings; 2.3 pass/approved (11 Spinner call sites
  independently recounted, plus a repo-wide sweep for non-JSX consumers — none).
  2.1 first pass returned quality `needs_fixes`: SC-2 claims the cookie carries `setUserLocale`'s
  attributes but only its value was asserted, and the suppression cases asserted response identity
  only, which an implementation that set the cookie and returned the same instance would satisfy.
  Both closed in b1850d5 and mutation-proven on re-review (max-age, sameSite, path, and an
  identity-preserving impostor implementation each turn a test red); `langParam.ts` itself was
  never edited. Re-review: pass/approved, no findings.
  Accepted as-is: the row-1 `lang === undefined` guard is behaviourally redundant with
  `isLocale(undefined)` but is mandated verbatim by design §4.3's row ordering.

- 2026-09-08 — task 1.1 complete; commit 72f50ad. Verify exit 0; `pnpm build` clean and the
  Next deprecation warning is gone. Reviewer: spec pass / quality approved. One Minor finding
  (review-package hunk header) dismissed as a false positive — `review_package.py` renders
  `git diff -U10`, so a 12-line file legitimately shows `@@ -1,12 +1,12 @@`; changed lines match
  `git diff -U10` exactly.
- 2026-09-08 — Plan written. Intake `normal` / `medium`; design approved and then amended after
  xia2 research removed the `loading.tsx` half on measured evidence.
