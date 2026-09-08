# proxy-auth-failure-boundary — Design

Status: approved by user 2026-09-08 (scope: both halves; outage behaviour: fail closed to login).
Lane: `high-risk` (auth hard gate) · Confidence: `high` (the fork below was resolved before design).
Branch is stacked on `feat/review-c3-web-ssr-i18n` (PR #168): the file this edits, `src/proxy.ts`,
exists only there — on `main` it is still `src/middleware.ts`.

## 1. Problem

`src/proxy.ts` awaits `updateSession(request)` with no boundary. Two different causes reach it, and
conflating them is why "what should happen?" reads as one question when it is two.

| Cause | Nature | Blast radius today |
|---|---|---|
| **Misconfiguration** — `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` unset | deterministic | 500 on every matched path, **including `/auth/login`**, plus a broken browser client and broken route handlers |
| **Outage** — JWKS host unreachable, Supabase down | transient | 500 on every matched path, including the pages a user needs to recover |

Both were verified, not assumed:

- `createServerClient(undefined, key, …)` **throws synchronously** — measured against the installed
  `@supabase/ssr`, message *"Your project's URL and Key are required to create a Supabase client!"*.
  So the message was never the problem; **where it surfaces** is.
- The `!` non-null assertions are in **three** files, not one: `lib/supabase/middleware.ts`,
  `lib/supabase/server.ts`, `lib/supabase/client.ts`. The escalation saw only the proxy.
- There is **no env validation anywhere** — no module, no build check, no `instrumentation.ts`.

## 2. The build-time constraint that shapes everything

`NEXT_PUBLIC_*` variables are **inlined at build time**, not read at runtime. From the Next 16 docs:

> Next.js can "inline" a value, at build time, into the js bundle that is delivered to the client,
> replacing all references to `process.env.[variable]` with a hard-coded value. … After being built,
> your app will no longer respond to changes to these environment variables.

And, decisively for how the validator may be written:

> Note that dynamic lookups will **not** be inlined, such as: `process.env[varName]` … `const env =
> process.env; setupAnalyticsService(env.NEXT_PUBLIC_ANALYTICS_ID)`

**Therefore `lib/env.ts` must reference each variable literally.** The natural shape for a
validator — iterate a list of names, look up `process.env[name]` — silently yields `undefined` in
the browser bundle and would *create* the outage it exists to prevent. This is the single most
likely way to get this change wrong.

Consequence: for these two variables, "fail fast at boot" means **fail at build**. A server-side
runtime check is still worth having, because it catches an image built without them being promoted
into an environment that expects them.

## 3. Design

### 3.1 `src/lib/env.ts` — one literal read, one clear failure

```ts
// Literal property access per variable: Next only inlines `process.env.NAME`,
// never `process.env[name]`. A loop here would ship `undefined` to the browser.
const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const SUPABASE_PUBLISHABLE_KEY = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;

export function requireSupabaseEnv(): { url: string; key: string } { … }
```

`requireSupabaseEnv()` throws one message naming **which** variable is missing and that it is
required at **build** time, not deploy time — the fact a reader needs and neither Supabase's message
nor a bare `!` provides.

The three call sites replace `process.env.X!` with `requireSupabaseEnv()`. Behaviour on a correct
configuration is identical; the change is what happens when it is wrong, and where you learn.

### 3.2 `src/instrumentation.ts` — fail the server at startup

Next runs `register()` once on server startup (docs: *"You can run code on server startup using the
`register` function"*). Calling `requireSupabaseEnv()` there turns a misconfigured deploy into one
loud startup failure instead of a 500 per user request. This does not help a *client* bundle built
without the vars — nothing can, they are already inlined — but it catches the server half at the
earliest possible moment.

### 3.3 `src/proxy.ts` — the outage boundary

```ts
export async function proxy(request: NextRequest) {
  let response: NextResponse;
  try {
    response = await updateSession(request);
  } catch (error) {
    return authUnavailable(request, error);
  }
  return applyLangParam(request, response);
}
```

`authUnavailable` implements the decided behaviour — **fail closed**:

| Path | Behaviour |
|---|---|
| protected (`/trips`, `/bookings`, `/expenses`, `/places`) | 307 to `/auth/login` — treated as not signed in |
| everything else, including `/` and `/auth/**` | `NextResponse.next({ request })` — renders normally |

The user cannot actually sign in while the backend is down, but they reach a page that renders and a
state they can understand, instead of a blank 500 — and critically, `/auth/login` itself stops
500ing, which is what made the current failure unrecoverable.

The error is logged once with `console.error` including the pathname. No `?lang=` handling runs on
this path: `applyLangParam` is skipped entirely, because a locale preference is not worth a second
failure mode during an outage.

**Why not fail open:** rendering the page would look signed-in but every API call 401s, and widening
an auth gate while the auth backend is unstable is the wrong direction.

**Why not a dedicated error page:** it needs a new route plus catalog entries in two languages for a
state that should be rare. `/auth/login` already exists, already renders, and already explains
itself. Revisit if outages prove common.

## 4. Scope boundary

`PROTECTED_PREFIXES` and `isProtected` stay in `lib/supabase/middleware.ts` and are exported for the
boundary to reuse — the list must not be duplicated, or the two copies will drift and the failure
path will protect a different set of routes than the success path.

Not in scope: retry/backoff on the auth call, a health probe, caching claims, or any change to what
`updateSession` does on the success path.

## 5. Error behaviour

- A missing variable: `register()` throws at **server start**, which is a different moment from
  `next build` — do not expect the build step itself to catch it. A client bundle built without the
  variables already has `undefined` inlined and nothing at runtime can recover it.
- A missing variable at runtime on the server: same message, at startup rather than per request.
- An auth outage: §3.3. No path returns 500.
- `authUnavailable` itself performs no I/O and reads only `request.nextUrl.pathname`, so it cannot
  throw and turn the boundary into the failure it catches.

## 6. Tests

| # | Check | Where |
|---|---|---|
| T1 | `requireSupabaseEnv()` returns both values when set; throws naming the missing variable when either is absent | `src/lib/env.test.ts` |
| T2 | `env.ts` contains no dynamic `process.env[...]` access — a grep gate, because the failure it prevents is invisible at runtime in tests (jsdom has no inlining step) | same |
| T3 | Proxy on an auth throw: a protected path 307s to `/auth/login` | `src/proxy.test.ts` |
| T4 | Proxy on an auth throw: `/` and `/auth/login` render (not a redirect, not a throw) | same |
| T5 | The success path is unchanged — the five existing `applyLangParam` branch cases still pass | existing `src/proxy.test.ts` cases |
| T6 | `isProtected` is imported, not re-implemented, in the failure path | grep gate in `src/proxy.test.ts` |

T2 and T6 exist because both failures they guard are invisible in a passing test run: an inlining
mistake only shows in a real browser bundle, and a duplicated prefix list only shows when someone
edits one copy.
