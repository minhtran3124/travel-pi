# review-c-web-experience — Escalations

Default: **deny-on-no-response**. No recorded decision → work stays blocked.
(Enforced: `hooks/commit-quality-gate.sh` denies commits touching this slug while any `decision:` is `pending`.)

---

## E001

- raised_by: orchestrator (feature-intake)
- date: 2026-09-04
- trigger: ambiguous-direction
- question: How should section C be scoped for execution?
- context: blocks brainstorming/xia2 — the plan shape differs materially per option. Note item 10's "identity hai đầu" claim is already fixed on main by review-A (PR #129); only the E2E/CI half of item 10 remains.
- options:
  - A) **Three child specs, executed in order** (recommended): `review-c1-e2e-auth-ci` (login fixture, fix trip-smoke, add a CI e2e job), `review-c2-chat-resilience` (Stop button, interrupt persistence across reload, side-panel persistence, surface claim-403, close #109), `review-c3-web-ssr-i18n` (loading.tsx + server-component conversion where cheap, aria-label i18n, localized URL decision). Each gets its own SUMMARY/PLAN; this spec becomes the parent record.
  - B) One high-risk spec covering everything; single long PLAN.md.
  - C) Bugs-only slice now (E2E fix, Stop button, claim-403 surfacing, aria-label i18n, loading.tsx); defer interrupt persistence, localized URLs and the visual refresh to the roadmap.
- default_if_no_response: BLOCK
- decision: A — three child specs in order: review-c1-e2e-auth-ci → review-c2-chat-resilience → review-c3-web-ssr-i18n; this spec is the parent record.
- decided_by: Minh Tran
- decided_at: 2026-09-04

## E002

- raised_by: orchestrator (feature-intake)
- date: 2026-09-04
- trigger: hard-gate
- question: For "interrupt state survives reload", may the BE conversation read contract change?
- context: blocks the interrupt-persistence task in item 11. The FE keeps `InterruptState` in memory only; after reload the LangGraph checkpoint still holds the pending interrupt but the FE has no way to learn about it.
- options:
  - A) Extend `GET /agent/conversations/{id}/messages` (or add `GET /agent/conversations/{id}/state`) to return the pending interrupt payload — public-contract change, additive.
  - B) FE-only: persist the interrupt payload to localStorage alongside the conversation id and re-offer approve/reject on reload; no BE change, but a stale local copy can disagree with the checkpoint.
  - C) Out of scope for this section.
- default_if_no_response: BLOCK
- decision: A — extend the BE conversation read contract (additive) so the FE can rehydrate a pending interrupt after reload.
- decided_by: Minh Tran
- decided_at: 2026-09-04

## E003

- raised_by: orchestrator (feature-intake)
- date: 2026-09-04
- trigger: ambiguous-direction
- question: Is the item-12 visual half ("calm vs energetic", photography, coral token) in scope, and if so what is its acceptance criterion?
- context: blocks the design step for item 12. There is no verifiable criterion; without one the task cannot pass task-review.
- options:
  - A) Out of scope; record as a design backlog note in the parent SUMMARY.
  - B) In scope as a `brainstorming` design fork with a concrete deliverable (e.g. hero photography on `/` and `/trips` empty state, coral used for one named accent role) reviewed via screenshots.
- default_if_no_response: BLOCK
- decision: A — out of scope; recorded as a design backlog note in the parent SUMMARY.
- decided_by: Minh Tran
- decided_at: 2026-09-04
