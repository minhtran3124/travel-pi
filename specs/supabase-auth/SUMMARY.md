# supabase-auth — Summary

Lane: high-risk
Confidence: high
Reason: Auth hard gate fired (login/session/JWT) on both apps/web and apps/api; plus authorization and weak-proof flags. Scope confirmed by human (E001/E002 decided), so confidence is high while the lane stays high-risk.
Flags: Auth, Authorization, External systems, Weak proof
Affects: new auth surface in apps/web (root middleware, auth routes/pages, Supabase clients in src/lib/supabase/*) AND new JWT verification in apps/api (FastAPI). No DB migration (no profiles table this slice).
Input-type: new initiative

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

<!-- Verbatim user request at intake. -->

"implementation auth feature for user using supabase"

Session context preceding this intake (foundation already laid, not yet wired):
- Installed `@supabase/supabase-js` and `@supabase/ssr` in apps/web.
- Added `src/lib/supabase/{client,server,middleware}.ts` via the Supabase shadcn registry
  (`@supabase/supabase-client-nextjs`).
- Set `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` in `.env.local`.
- Root `src/middleware.ts` NOT yet created — `updateSession` is not running.

## What changed

<!-- Filled at completion — nothing implemented yet; intake + escalation only. -->

Not started. Intake classified the work as high-risk and escalated for scope confirmation
(see ESCALATIONS.md, now decided). Confirmed scope + phasing:
- Phase 1 (this slice): apps/web email+password + magic link; apps/api Supabase-JWT
  verification via JWKS (asymmetric). No route protection, no profiles table.
- OAuth (Google/GitHub): code scaffolded but DEFERRED — blocked on Supabase dashboard
  provider config the user will do later. Ship email+magic-link first.
Next: research (xia2-lite) → writing-plans → using-git-worktrees → subagent-driven-development.

### Rationale

Auth is a hard gate under `rules/auto-correct-scope.md` Rule 4; the request is broad enough that
two engineers would build materially different things, so a human must narrow scope before a plan.

### Alternatives considered

- none yet (pending scope confirmation)

### Deviations

- none

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| (pending implementation) | — | — | — |

### Rollback

- `git revert <sha>` (per commit once implementation begins)

### Harness-Delta

- none
