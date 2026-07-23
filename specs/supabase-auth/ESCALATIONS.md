# supabase-auth — Escalations

Default: **deny-on-no-response**. No recorded decision → work stays blocked.

---

## E001

- raised_by: orchestrator
- date: 2026-06-26
- trigger: hard-gate
- question: Confirm we may build a Supabase user-auth surface in apps/web (a Rule-4 Auth hard gate).
- context: All implementation is blocked until a human authorizes crossing the Auth boundary and narrows scope.
- options:
  - A) Authorize a minimal email/password auth (sign-up, sign-in, sign-out, session via root middleware, one protected route) — smallest credible slice.
  - B) Authorize a broader scope (OAuth providers, magic link, profile table + RLS) — larger initiative, multiple PLANs.
- default_if_no_response: BLOCK
- decided_by: Minh Tran
- decided_at: 2026-06-26
- decision: AUTHORIZED — build the Supabase auth surface in apps/web; scope narrowed per E002.

## E002

- raised_by: orchestrator
- date: 2026-06-26
- trigger: ambiguous-direction
- question: Which auth method(s), which routes are protected, and is a profile/users table + RLS in scope?
- context: "auth feature for user using supabase" maps to materially different builds; a plan cannot be written until scope is fixed.
- options:
  - A) Email/password only, protect /trips/*, no extra DB table (rely on Supabase auth.users).
  - B) Email/password + OAuth (Google), protect /trips/*, add public.profiles table with RLS.
  - C) Other — user-specified scope.
- default_if_no_response: BLOCK
- decided_by: Minh Tran
- decided_at: 2026-06-26
- decision: |
    Scope fixed:
    - Auth methods: email+password, magic link (OTP), OAuth Google, OAuth GitHub.
    - Route protection: NONE yet (build login/logout + session plumbing only; gate routes later).
    - Profile table / RLS: NONE — rely on Supabase auth.users.
    - Backend: ALSO verify Supabase JWT in apps/api (FastAPI) — expands scope into the backend (second Auth gate).
