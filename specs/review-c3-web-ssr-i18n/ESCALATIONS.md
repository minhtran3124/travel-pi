# review-c3-web-ssr-i18n — Escalations

Default: **deny-on-no-response**. No recorded decision → work stays blocked.
(Enforced: `hooks/commit-quality-gate.sh` denies commits touching this slug while any `decision:` is `pending`.)

---

## E001

- raised_by: correctness-review (guard-completeness angle), 2026-09-08
- date: 2026-09-08
- trigger: hard-gate
- question: When the Supabase auth backend is unreachable or unconfigured, should the app degrade to "signed out" or hard-fail?
- context: `apps/web/src/proxy.ts:6` awaits `updateSession(request)` with no boundary. If `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` are unset in a preview or CI deploy — `lib/supabase/middleware.ts:29-30` non-null-asserts both, and `createServerClient` throws **synchronously** — or if `getClaims()` rejects on an unreachable JWKS host, the rejection escapes the proxy and Next returns **500 for every path the matcher covers**, including `/auth/login` and `/auth/callback`: the pages a user needs to recover. The `isProtected` guard correctly limits the auth *gate* to four prefixes, but it only runs on the success path; nothing bounds the failure path, so an auth outage takes the whole site rather than four prefixes.
- **This defect predates this branch.** `git show main:apps/web/src/middleware.ts` has the same unguarded await. This slice renamed that file to `proxy.ts` and composed a second step onto it, so the line is new at `proxy.ts:6` while the defect is inherited. It is recorded here rather than fixed because the fix is an auth/session-scope decision (Rule 4), and because silently hardening the session-refresh path inside a slice about chrome and skeletons is exactly what `rules/behavior.md` §3 forbids.
- options:
  - A) **Fix in a separate spec.** Wrap `updateSession` in try/catch; on failure log and return `NextResponse.next({ request })` for unprotected paths, and decide explicitly what protected paths do (fail closed to the login page, or fail open). Keeps this slice's boundary intact and gives the auth decision its own review.
  - B) **Fix here.** Add the boundary in this branch. Faster, but puts an unreviewed auth-behaviour decision inside a PR nobody will read for that.
  - C) **Accept as-is.** Record that an auth-backend outage 500s the site. Defensible only if the deploy pipeline guarantees the env vars and the Supabase host is treated as a hard dependency.
- default_if_no_response: BLOCK
- decision: **A — fix in a separate spec.** The boundary is not added to this branch. Intake for the
  follow-up is recorded at `specs/proxy-auth-failure-boundary/SUMMARY.md`, lane `high-risk` (the
  `auth` hard gate fires). This slice keeps its boundary: it renamed the convention file, it did not
  take ownership of the session-refresh failure path.
- decided_by: Minh Tran
- decided_at: 2026-09-08
