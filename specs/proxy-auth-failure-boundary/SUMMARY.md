# proxy-auth-failure-boundary — Summary

Lane: high-risk
Confidence: medium
Reason: the `auth` hard gate fires — the change is a failure-mode decision on the Supabase session-refresh path that runs in the proxy on every request. Confidence medium: the defect and its blast radius are established, but the intended failure behaviour (degrade to signed-out vs fail closed) is a product decision that has not been made.
Flags: auth, existing behavior, weak proof
Affects: apps/web/src/proxy.ts, apps/web/src/lib/supabase/middleware.ts
Input-type: change request

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

Raised by `correctness-review` (guard-completeness angle) during `review-c3-web-ssr-i18n`, and split
out by user decision on 2026-09-08 ("tach spec rieng ra"). Verbatim finding:

> `apps/web/src/proxy.ts:6` awaits `updateSession(request)` with no boundary. If
> `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` are unset in a preview or CI
> deploy — `lib/supabase/middleware.ts:29-30` non-null-asserts both, and `createServerClient` throws
> **synchronously** — or if `getClaims()` rejects on an unreachable JWKS host, the rejection escapes
> the proxy and Next returns **500 for every path the matcher covers**, including `/auth/login` and
> `/auth/callback`: the pages a user needs to recover. The `isProtected` guard correctly limits the
> auth gate to four prefixes, but it only runs on the success path; nothing bounds the failure path,
> so an auth outage takes the whole site rather than four prefixes.

Source: `specs/review-c3-web-ssr-i18n/ESCALATIONS.md` E001, decision A.

## What changed

<not started — intake record only>

### Rationale

<pending design>

### Alternatives considered

- pending

### Deviations

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| Defect reproduces on the current tree | `cd apps/web && grep -q "await updateSession(request)" src/proxy.ts && grep -q "process.env.NEXT_PUBLIC_SUPABASE_URL!" src/lib/supabase/middleware.ts` | 0 | both the unguarded await and the non-null assertion are present as described | |

### Not auto-verified

- "An auth-backend outage 500s every matched path" — reached **provenance** (read from the code and
  from `createServerClient`'s documented synchronous throw); not reproduced against a running
  deployment with the env vars removed. Reproducing it is the first task of this spec.

### Rollback

- Intake only: `git rm -r specs/proxy-auth-failure-boundary`.

### Harness-Delta

- none
