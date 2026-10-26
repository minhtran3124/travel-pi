# review-c3-web-ssr-i18n — Research Brief

**Depth: Deep** (upgraded from the intake mapping). Intake lane is `normal` → Standard.
Upgraded on evidence per `rules/research-depth.md` ("research may move up on evidence, never
down"): the change edits `src/middleware.ts`, the single entry point that runs Supabase session
refresh for **every** request, and it depends on version-specific framework API. That is both the
"entry point / shared runtime configuration" and the "auth/session scope adjacency" Deep signal.
The **lane is unchanged** — xia2 does not re-score risk, only research depth.

**External surface: yes.** No dependency is added or upgraded, but the change relies on
version-specific APIs of Next.js 16 and next-intl 4. Version-matched official docs were therefore
required, and they overturned two design decisions.

---

## Bottom Line

| Field | Value |
|---|---|
| **Recommendation** | **Adapt** — the design's shape survives, but two of its mechanisms do not and must be rewritten before planning |
| **Why this is the lightest credible path** | Every capability needed already ships in Next 16 and next-intl 4; nothing must be built or added. What research changed is *which* API each part uses |
| **Confidence** | 90% — the two corrections are quoted from version-matched official docs; the one remaining unknown (F5) is empirically checkable in minutes |
| **Next step** | Done: `design.md` amended (§3 rewritten, §4.2 added, §4.3 cond. 3 rewritten, §7/§8 rebuilt) → `writing-plans` |

**Three findings change the design. Two are blocking.**

---

## Feature Understanding and Assumptions

- **Requested feature:** close the measurable half of deep-review item 12 — loading affordance on
  navigation, English leaking through app chrome, no shareable per-language URL.
- **What success appears to mean:** clicking a nav item paints a skeleton immediately; a
  `?lang=vi` link shared to someone opens the app in Vietnamese; no hardcoded English in the
  header chrome.
- **Assumptions from the request:** client-fetch architecture stays (user-decided); `/auth/**` is
  out of scope (owned by `auth-pages-redesign`); visual half out of scope (parent E003-A).
- **Assumptions still needing confirmation:** F2 — whether the deprecated `middleware.ts` →
  `proxy.ts` rename belongs in this slice or a follow-up.

---

## Evidence Ledger

| Label | Evidence |
|---|---|
| `Docs` | **F1 (blocking).** Next.js strips internal Flight headers from the request object in proxy/middleware: *"During RSC requests, Next.js strips internal Flight headers from the `request` instance in Proxy. For example, headers like `rsc`, `next-router-state-tree`, and `next-router-prefetch` are **not exposed** through `request.headers`."* → `design.md` §4.3 condition 3 reads exactly those two headers and **cannot work as written**. |
| `Docs` | **F2 (blocking).** `middleware` is deprecated and renamed: version history row *"`v16.0.0` — Middleware is deprecated and renamed to Proxy. Proxy defaults to the Node.js runtime."* Export renames `middleware` → `proxy`; official codemod `npx @next/codemod@canary middleware-to-proxy .`. `Local`: repo is on `next 16.2.9` with `src/middleware.ts` exporting `middleware`, and no `proxy.ts` exists. |
| `Docs` | **F3.** next-intl v4 does use `react-server` conditional exports, but the actual restriction is narrower than `design.md` §3.3 claims: *"hooks cannot be called from `async` components."* Hooks work fine in non-async server components. → the §3.3 move rationale is wrong **for the second time**. |
| `Docs` | **F4 (opportunity).** `next/experimental/testing/server` ships `unstable_doesProxyMatch`, `isRewrite`, `getRewrittenUrl`, `getRedirectUrl` (since v15.1) for unit-testing proxy. `Local`: verified present at `apps/web/node_modules/next/experimental/testing/server.js`. |
| `Local` | **F8 (decisive, measured after the brief's first draft).** A browser probe on the running dev server showed `loading.tsx` **never paints** for a client-component page — with prefetch on *and* with `prefetch={false}` — but **does** paint for an `await`ing server component (`["loading-tsx","page-data"]`). Cause is neither prefetch nor F5: a `"use client"` page never suspends on the server, so the boundary resolves immediately. → the design's entire `loading.tsx` half was **removed**; see `design.md` §3.1. |
| `Local` | **F2 confirmed at runtime.** `apps/web/.next/dev/logs/next-development.log` contains `⚠ The "middleware" file convention is deprecated. Please use "proxy" instead.` — the deprecation is live, not merely documented. |
| `Docs` | **F5 (caveat — measured NOT to be the cause of F8).** *"If the layout accesses uncached or runtime data (e.g. `cookies()`, `headers()`…), `loading.js` will not show a fallback for it. Without Cache Components: navigation blocks until the layout finishes rendering."* `Local`: `app/layout.tsx` is `async` and calls `getLocale()` (reads cookies) and `generateMetadata` → `getTranslations`; `next.config.ts` does **not** enable Cache Components. |
| `Docs` | **F6 (confirms design).** *"Server Functions … are handled as POST requests to the route where they are used, so a Proxy matcher that excludes a path will also skip Server Function calls on that path."* → §4.3's Server-Action reasoning, previously `Inference`, is now `Docs`-confirmed. |
| `Docs` | **F7 (confirms design).** `loading.js` version history lists only `v13.0.0` — no behavioural change through Next 16. *"The Fallback UI is prefetched, making navigation immediate"* and *"Shared layouts remain interactive while new route segments load"* support the §3.1 value claim. |
| `Local` | `apps/web` stack: `next 16.2.9`, `react 19.2.4`, `next-intl ^4.13.0`, `@supabase/ssr ^0.12.0`, `@tanstack/react-query ^5.101`, `vitest ^2.1`, `jsdom ^25`, `typescript ^5`. Pinned exactly for `next`/`react`; carets elsewhere. |
| `Local` | `next.config.ts` wraps config in `createNextIntlPlugin("./src/i18n/request.ts")` and rewrites `/api/be/:path*` → FastAPI. No Cache Components, no PPR flags. |
| `Inference` | The `?lang=` seeding pattern itself has no canonical upstream implementation; next-intl's own docs for cookie-based locale cover only reading the cookie and switching it from a UI control. |

---

## Local Findings

- **Relevant files:** `src/middleware.ts`, `src/lib/supabase/middleware.ts`, `src/i18n/{config,locale,request}.ts`, `src/app/{trips,trips/[tripId],places,bookings}/page.tsx`, `src/components/trips/{TripCard,TripHeader}.tsx`, `src/components/bookings/BookingTable.tsx`, `src/components/{app-shell/AppShell,auth/UserMenu,ui/Spinner}.tsx`, `messages/{en,vi}.json`, `src/messages.parity.test.ts`.
- **Existing abstractions / extension points:** `isLocale()` as the shared validator; `LOCALE_COOKIE` + attribute set in `i18n/locale.ts`; the auth-gate redirect in `lib/supabase/middleware.ts:69-74` is a working, in-repo model for "build a redirect and carry the rotated cookies across"; `messages.parity.test.ts` auto-covers new catalog keys.
- **Conventions worth preserving:** one leading `SystemMessage`-style single source of truth for locale (cookie); `aria-hidden` + text-free skeletons; per-namespace message catalogs; `Spinner` reserved for in-place busy, skeletons for shaped content.
- **What can likely be reused:** the auth-gate cookie-copy pattern (verbatim shape), `isLocale`, `TripCardSkeleton`/`TripHeaderSkeleton` markup, `messages.parity.test.ts`, and — newly discovered — `next/experimental/testing/server` for the proxy tests.
- **What appears missing locally:** no `loading.tsx`, no `Suspense`, no tests under `src/app/`, no `Account` namespace, no `TripDetail` loading key, and no in-repo precedent for rendering an `async` server component under vitest.

---

## Upstream Findings

- **Repositories inspected:** `amannn/next-intl` discussions #2138 (cookie + browser-locale detection without i18n routing), #2205 (getting locale from cookie), #1135 (client cookies cannot switch locale), issue #1334 (changing locale in App Router without i18n routing).
- **Pattern already present upstream:** cookie-as-locale-source without routing is the documented, supported next-intl configuration — the repo's `i18n/request.ts` already matches it exactly.
- **Areas worth modeling:** none beyond what the repo already does. The `?lang=` seeding step is *not* an upstream pattern; every upstream discussion switches locale from an in-app control (a server action), which the repo already has in `LocaleSwitcher`.
- **How closely upstream matches:** the read side matches fully; the shareable-URL side has no upstream precedent, which is itself the finding — it means the design is building something genuinely un-templated and its own test coverage carries the whole burden.
- **Upstream gaps:** next-intl v4.0 changed cookie defaults (session cookie by default, set only when the chosen locale differs from `accept-language`). That governs *next-intl's own* `localeCookie`; this repo writes `LOCALE_COOKIE` itself with an explicit one-year `maxAge`, so it is unaffected — but the two must not be conflated later.

---

## Docs Findings

- **Official sources checked:** `nextjs.org/docs/messages/middleware-to-proxy`; `nextjs.org/docs/app/api-reference/file-conventions/proxy` (doc version 16.3.4); `nextjs.org/docs/app/api-reference/file-conventions/loading` (16.3.4); `next-intl.dev/docs/environments/server-client-components`; `next-intl.dev/docs/getting-started/app-router/without-i18n-routing`.
- **Version-matched vs latest-stable:** docs render at **16.3.4**, repo is on **16.2.9** — same major, docs slightly ahead. Every fact used here is anchored to a version-history row at or below 16.0.0, so the gap does not affect the conclusions.
- **Built-in capabilities that already support the feature:** `loading.js` (v13+, unchanged); `NextResponse.redirect` + `response.cookies.set`; proxy `matcher` `has`/`missing` for prefetch discrimination; `next/experimental/testing/server` for proxy unit tests; `getTranslations` from `next-intl/server` for async server components.
- **Current recommended APIs:** `proxy.ts` exporting `proxy` (Node runtime, `runtime` config option throws if set).
- **Important caveats / deprecations:** F1 (Flight headers stripped), F2 (middleware deprecated at v16.0.0), F5 (`loading.js` does not cover runtime data read in a layout), and — per the proxy docs — *"Always verify authentication and authorization inside each Server Function rather than relying on Proxy alone."*

---

## Recommendation

- **Primary recommendation: adapt.** Keep the design's structure — it survives review — and rewrite the two mechanisms that research falsified.

**Required amendments before `writing-plans`:**

1. **§4.3 condition 3 — rewrite (F1).** Drop `Next-Router-Prefetch` and `RSC` from the rule: Next
   strips them from `request.headers`, so the condition would silently never fire and the
   prefetch regression the design was guarding against would ship anyway. Rely on
   **`sec-fetch-dest === "document"`**, a standard browser header that Next does not strip and
   that distinguishes a document navigation from every RSC/prefetch/`fetch` request. Keep
   conditions (1) GET and (2) not `/api/`. Keep "absent header still redirects" for non-browser
   clients. The documented alternative — matcher `has`/`missing` on `next-router-prefetch` — is
   **not** usable here, because the same proxy must keep running Supabase session refresh on the
   requests it would exclude.
2. **§3.3 move rationale — correct it (F3).** The claim that importing `TripCard.tsx` into the
   server graph *fails to compile* is wrong; hooks are unavailable only inside `async`
   components, and the skeleton exports call none. State the move's real justification: the new
   container skeletons are server-rendered and should not drag `next/link` + next-intl hook
   modules into the server graph. It is a robustness choice, **not** a compile necessity. (This
   rationale has now been wrong twice; the corrected version is the one to keep.)
3. **§7 — use the shipped test utility (F4).** T1–T5b should use
   `next/experimental/testing/server` (`unstable_doesProxyMatch`, `getRedirectUrl`) rather than
   hand-rolled `NextRequest` fixtures. This also shrinks the "no in-repo pattern" risk the design
   flagged — though it does **not** solve it for T6/T7b, which still must render an `async` server
   component under vitest.
4. **§3.1 — record the F5 caveat.** The root layout is async and reads cookies, so `loading.tsx`
   provides no fallback *for the layout*. On soft navigations between sibling segments the layout
   is not re-rendered, so the design's value claim holds — but this should be verified empirically
   (see Risks) rather than asserted.

- **Why the next-best alternative lost:** *Build from scratch* (a hand-rolled prefetch detector,
  or bespoke proxy test fixtures) loses because both capabilities already ship — a standard
  `Sec-Fetch-Dest` header and a first-party test module. *Use built-in only* (matcher
  `has`/`missing`) loses because the matcher gates the entire proxy, which would disable Supabase
  session refresh on the excluded requests — a session bug traded for a locale bug.
- **What would change this recommendation:** if F5's empirical check shows `loading.tsx` never
  paints because of the async root layout, the loading half needs rework (wrap the layout's
  runtime data in its own `<Suspense>`, per the docs) and is no longer a cheap slice.

---

## Risks, Unknowns, and Follow-Up Questions

- **Technical risks:**
  - Writing new logic into a file deprecated at `v16.0.0` (F2) accrues migration debt in the
    highest-blast file in the app.
  - `sec-fetch-dest` is a browser header; any non-browser client (curl, a link-unfurling bot)
    omits it and takes the "absent → redirect" branch. That is intended, but it means an unfurler
    following a `?lang=vi` link gets a 307 — harmless, worth knowing.
  - `applyLangParam` returning a *new* response object in one branch is the one place a mistake
    silently logs every user out. The in-repo cookie-copy pattern must be followed literally.
- **Evidence gaps:** F5 is the only untested claim that could invalidate a design section.
  Verifying it costs one `pnpm dev` run plus a nav click with the network panel open.
- **Version uncertainties:** docs at 16.3.4 vs repo at 16.2.9. `next/experimental/testing/server`
  is explicitly *experimental* — its API may move within the major.
- **Follow-up questions — both answered by the user on 2026-09-08:**
  1. **F2 fork → decided: migrate.** `middleware.ts` → `proxy.ts` via the official codemod lands as
     task 1 of the plan, its own commit, verified on its own (`design.md` §4.2).
  2. **F5/F8 → decided: verify first.** It was verified before planning, and the measurement
     (F8) removed the `loading.tsx` half of the design entirely rather than confirming it. This is
     the single highest-value result of this research session: five rounds of adversarial document
     review had refined a mechanism that does not work, because no round ran it.

---

## Source Pack

- **Local files read:** `apps/web/package.json`, `next.config.ts`, `src/middleware.ts`,
  `src/lib/supabase/middleware.ts`, `src/i18n/{config,locale,request}.ts`,
  `src/app/{layout,page}.tsx`, `src/app/{trips,trips/[tripId],places,bookings}/page.tsx`,
  `src/app/auth/login/page.tsx`, `src/components/trips/{TripCard,TripHeader}.tsx`,
  `src/components/bookings/BookingTable.tsx`, `src/components/app-shell/{AppShell,LocaleSwitcher}.tsx`,
  `src/components/auth/UserMenu.tsx`, `src/components/ui/Spinner.tsx`, `messages/{en,vi}.json`,
  `pnpm-lock.yaml`, `docs/solutions/INDEX.md`, `docs/solutions/monorepo/phase1-architecture-decisions.md`,
  `docs/solutions/agent/side-panel-language-decisions.md`, `specs/review-c-web-experience/ESCALATIONS.md`,
  `specs/review-c3-web-ssr-i18n/{SUMMARY,design}.md`.
- **Upstream repositories or pages checked:**
  https://github.com/amannn/next-intl/discussions/2138 ·
  https://github.com/amannn/next-intl/discussions/2205 ·
  https://github.com/amannn/next-intl/discussions/1135 ·
  https://github.com/amannn/next-intl/issues/1334
- **Official docs domains or pages checked:**
  https://nextjs.org/docs/messages/middleware-to-proxy ·
  https://nextjs.org/docs/app/api-reference/file-conventions/proxy ·
  https://nextjs.org/docs/app/api-reference/file-conventions/loading ·
  https://next-intl.dev/docs/environments/server-client-components ·
  https://next-intl.dev/docs/getting-started/app-router/without-i18n-routing ·
  https://next-intl.dev/blog/next-intl-4-0

---

## Evidence Boundary

> **Confirmed from artifacts:** all version numbers (`package.json`, `pnpm-lock.yaml`); absence of
> `proxy.ts`; presence of `next/experimental/testing/server.js` in `node_modules`; absence of
> Cache Components in `next.config.ts`; the async root layout's `getLocale()`/`getTranslations`
> calls; every quoted docs sentence, each read from a version-matched official page.
>
> **Inferred from patterns:** that `sec-fetch-dest` is not stripped by Next (it is a standard
> request header, not a Flight header — the docs enumerate only Flight headers as stripped, and do
> not state an exhaustive strip list); that the `?lang=` seeding step has no upstream precedent
> (four next-intl discussions searched, none covers it — absence of evidence at this search depth).
>
> **Not checked:** runtime behaviour of `unstable_doesProxyMatch` against this repo's matcher; runtime behaviour of `unstable_doesProxyMatch` against this repo's matcher;
> Playwright suite behaviour under the change.
