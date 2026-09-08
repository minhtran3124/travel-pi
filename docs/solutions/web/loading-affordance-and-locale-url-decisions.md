---
problem_type: decision
module: web
tags: skeletons, aria-live, accessibility, i18n, locale-url, next-intl, client-fetch, scope-boundary
severity: standard
applicable_when: Adding a loading affordance to an apps/web page, announcing a transient state to assistive technology, or making a user-chosen setting shareable through a URL.
affects:
  - apps/web/src/components/skeletons/
  - apps/web/src/lib/i18n/langParam.ts
  - apps/web/src/app/bookings/page.tsx
  - apps/web/src/app/places/page.tsx
supersedes: null
confidence: high
confirmed_at: 2026-09-08

---
## Applicable When

Adding a loading affordance to an `apps/web` page, announcing a transient state to assistive
technology, or making a user-chosen setting shareable through a URL.

## Context

A deep review named three defects together: no `loading.tsx`, hardcoded English `aria-label`s, and a
locale that lived only in a cookie so no link could carry it. Treating them as one item hid the fact
that they have different causes and different right answers.

## Options Considered

**Loading.** (a) Add `loading.tsx` per route. (b) Convert pages to server components so a boundary
has something to wait on. (c) Standardise client-side skeletons and ship no `loading.tsx`.

**The shared unit for a skeleton.** (a) Leaf card/row placeholders, with each caller supplying its
own wrapper. (b) A container component owning its wrapper.

**Announcing the loading state.** (a) Render an sr-only `role="status"` region inside the pending
branch. (b) Render the region unconditionally and change only its text.

**Shareable locale.** (a) `[locale]` path segments with next-intl routing. (b) `?lang=` seeding the
cookie then redirecting to a clean URL. (c) Defer.

## Decision & Rationale

**Loading → (c), and the review item stays open.** (a) is inert here — measured, see the related
knowledge doc. (b) is the only real answer and needs a server-side auth path that `authHeader()` is
deliberately built not to provide; that is its own `high-risk` spec. Choosing (c) means being
explicit that the item is *not* closed rather than shipping four files that never render.

**Skeleton → (b), container.** Forced by the bookings table: `BookingTable` renders
`div > table > thead + tbody`, so a bare `<tr>` placeholder dropped into a pending branch is invalid
nesting and warns in React. More importantly, if each side supplies its own wrapper, a test asserting
"both render the same placeholder" can pass while the two markups diverge. Putting the wrapper inside
the shared component makes that divergence unrepresentable instead of merely discouraged.

**Announcement → (b), hoisted.** (a) is the obvious shape and it is wrong: a live region announces
when its contents change *after* it exists. A region inserted already holding its text is not
reliably announced, so the feature is silent — which is what it was added to prevent. This was
missed by every review that read the code and caught only by an adversarial pass that asked what the
code does at runtime.

**Locale → (b), `?lang=`.** It delivers the outcome asked for — a link that opens in the sender's
language — without restructuring every route, rewriting every internal `<Link>`, touching the auth
middleware chain, or updating both Playwright specs. (a) buys `hreflang` and per-language indexing
that nobody requested; it stays the upgrade path if SEO becomes a requirement.

## Consequences

- The review item about `loading.tsx` remains open on the record, by design. A future reader should
  find the measurement, not re-argue the decision.
- Skeleton components under `components/skeletons/` are directive-free, hook-free, text-free,
  `aria-hidden`, and carry a `data-testid` — the testid is a deliberate exception to "no props",
  because an aria-hidden text-free node has no other handle a test can reach.
- Because skeletons are `aria-hidden`, the sr-only live region is the *only* signal assistive
  technology gets. Replacing a `Spinner` (which carried `role="status"` and a translated label) with
  a skeleton silently removes an announcement unless the region is added deliberately.
- `?lang=` is consumed on arrival and stripped by the redirect, so a user who then copies their
  address bar shares a locale-less URL. "Hand someone a built link" works; "share the page I am
  looking at" does not. Accepted, not solved.

## Related
- docs/solutions/web/nextjs-16-proxy-and-loading-boundaries.md
- docs/solutions/agent/side-panel-language-decisions.md
