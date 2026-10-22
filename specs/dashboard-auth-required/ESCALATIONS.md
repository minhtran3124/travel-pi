# dashboard-auth-required — Escalations

Default: **deny-on-no-response**. No recorded decision → work stays blocked.
(Enforced: `hooks/commit-quality-gate.sh` denies commits touching this slug while any `decision:` is `pending`.)

---

## E001

- raised_by: orchestrator (feature-intake)
- date: 2026-09-05
- trigger: hard-gate | low-confidence | ambiguous-direction
- question: The dashboard already has opt-in HTTP Basic username/password auth (`DASHBOARD_BASIC_USER`/`DASHBOARD_BASIC_PASSWORD`, review-A). Which of these is the intended change?
- context: all planning (brainstorming → xia2 → writing-plans) is blocked until the direction is chosen.
- options:
  - A) No code change — set the two env vars locally / in Docker; the browser prompts for user+pass on every `/dashboard/*` hit. Done in minutes, nothing to review.
  - B) Make auth mandatory in every environment — remove the "open in development when unset" branch (401 always, or refuse to start without creds). Small patch: `app/core/dashboard_auth.py`, `Settings` validator, 4-state test → 3-state, `.env.example`; keeps Basic auth.
  - C) Proper login page — `/dashboard/login` form, signed cookie session, logout link in `base.html`, still one operator user+pass from env. Replaces the browser Basic prompt; largest surface; review-A listed this as a deferred non-goal.
- default_if_no_response: BLOCK
- decision: C — build a proper login page (/dashboard/login form + signed cookie session + logout), single operator user/pass from env
- decided_by: Minh Tran (user, in-session)
- decided_at: 2026-09-05
