---
problem_type: knowledge
module: web
tags: nextjs-16, proxy, middleware, loading-tsx, suspense, rsc, sec-fetch-dest, supabase-ssr, session-cookies, client-fetch
severity: critical
applicable_when: Working on apps/web routing, the proxy/middleware convention file, a loading affordance, or anything that reads request headers before a page renders. Also before claiming a Next file convention behaves a given way — the two facts below were both established by measurement after review had accepted the opposite.
affects:
  - apps/web/src/proxy.ts
  - apps/web/src/lib/i18n/langParam.ts
  - apps/web/src/lib/supabase/middleware.ts
supersedes: null
confidence: high
confirmed_at: 2026-09-08

---
## Applicable When

Working on `apps/web` routing, the proxy/middleware convention file, a loading affordance, or
anything that reads request headers before a page renders. Also before *claiming* a Next file
convention behaves a given way — both facts below were established by measurement after review had
accepted the opposite.

## Pattern

Three things about this app's request path, each measured on `next@16.2.9`, not recalled.

**1. `loading.tsx` never paints for a client-fetch page.** It is the Suspense fallback for *server*
rendering of a segment. Every page here is `"use client"` and fetches through TanStack Query, so
nothing suspends on the server, the boundary resolves immediately, and the file is inert. Adding one
is not a small win — it is dead code plus tests asserting a transition that does not occur, plus a
strong signal to the next reader that this app has SSR when it does not.

Measured on a throwaway route pair against a running dev server, polling the DOM at 20 ms:

| `/probe-b` page | `<Link>` | Observed sequence | `loading.tsx` shown |
|---|---|---|---|
| client component, client-side wait | default prefetch | `["page-pending"]` | no |
| client component, client-side wait | `prefetch={false}` | `["page-pending","page-data"]` | no |
| **async server component**, `await` 1.5 s | `prefetch={false}` | `["loading-tsx","page-data"]` | **yes** |

Row 3 isolates the cause: not prefetching, and not the documented caveat about a layout reading
runtime data. Until a route does async server work, a loading affordance has to be client-side.

**2. Next strips its own Flight headers inside the proxy.** `rsc`, `next-router-prefetch` and
`next-router-state-tree` are **not exposed** through `request.headers` in `proxy.ts`. A condition
reading them silently never fires — and a unit test constructing them by hand passes anyway, so the
gap survives review. Use `sec-fetch-dest`, a standard browser header Next does not strip:
`document` for a navigation, `empty` for every fetch/RSC/prefetch.

**3. `middleware` is deprecated in Next 16.0.0**, renamed to `proxy`. `src/middleware.ts` →
`src/proxy.ts`, export `middleware` → `proxy`, and Proxy defaults to the Node.js runtime (setting
`runtime` throws). Having both files is a hard build error. The codemod is
`npx @next/codemod@canary middleware-to-proxy .`; `config.matcher` carries over unchanged.

## How to Use

Compose the proxy with session refresh first and everything else operating on the finished response:

```ts
// src/proxy.ts
export async function proxy(request: NextRequest) {
  const response = await updateSession(request)
  return applyLangParam(request, response)
}
```

Never run code between `createServerClient` and `getClaims()` — `lib/supabase/middleware.ts` carries
an explicit warning that doing so logs users out at random.

When a step returns a **new** response instead of the one `updateSession` produced, copy every
cookie across, with attributes:

```ts
const redirect = NextResponse.redirect(url)
for (const cookie of response.cookies.getAll()) redirect.cookies.set(cookie)
```

Dropping this logs out every user; dropping only `HttpOnly` still breaks the session. The in-repo
model is `lib/supabase/middleware.ts:72-74`.

## Gotchas

- **`proxy.ts` runs on every matched request, including route handlers.** `matcher` here excludes
  only static assets, so `/auth/callback` and `/auth/confirm` are matched. They are GET handlers
  outside `/api/`, so a naive "is this a document navigation?" check treats them as pages — and a
  redirect there replays a single-use OAuth `code` or magic-link `token_hash` instead of exchanging
  it. Exclude `/auth/` explicitly.
- **Server Functions are POSTs to the current page URL.** A `<form action={serverAction}>` submits
  to the page it sits on, so proxy logic keyed on method alone will see them.
- **`/api/be/*` is GET-dominant.** Excluding "non-GET" does not exclude the API rewrite; check the
  path prefix.
- **`URLSearchParams.delete()` re-serializes the whole query.** `?flag&q=a b&lang=vi` becomes
  `?flag=&q=a+b`. Harmless when every consumer reads through `URLSearchParams`, but do not claim
  the redirect preserves the rest of the URL verbatim.
- **An absent `sec-fetch-dest` is ambiguity, not evidence.** Treating it as a document navigation is
  a deliberate choice here (curl, link unfurlers); it also catches Sec-Fetch-less browsers.
- **Proxy unit-testing needs `// @vitest-environment node`.** Under jsdom,
  `NextResponse.next({ request })` throws on `Headers`. Next ships
  `next/experimental/testing/server` (`unstable_doesProxyMatch`, `getRedirectUrl`) for this.
- **Nothing type-checks the convention.** `tsc` cannot tell you Next resolves `src/proxy.ts`; only
  `pnpm build` does — look for `ƒ Proxy (Middleware)` in the route table.

## Related
- docs/solutions/streaming/agent-sse-on-nextjs.md
- docs/solutions/monorepo/phase1-architecture-decisions.md
