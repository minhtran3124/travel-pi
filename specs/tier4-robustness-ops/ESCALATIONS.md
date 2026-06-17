# tier4-robustness-ops — Escalations

## Scope ambiguity (low confidence) — confirm before any work

- **Date:** 2026-06-17
- **Why escalated:** "Tier 4 — Robustness & ops" is five independent items, not one change.
  The single-sentence intent test fails (two engineers would build materially different things),
  so confidence is **low** → per the intake gate, confirm scope before touching code.
- **Decision needed from human:**
  1. Which of the five items to implement now (one, a subset, or all)?
  2. In what order? (Recommended first slice: `/healthz` + `/readyz` — lowest risk, fully additive.)
- **Policy conflict to resolve:** the **rate-limit headers** item conflicts with `CLAUDE.md`
  ("no auth, ORM, pagination, or rate limiting" per `mock-api-spec.md` §1). It needs an explicit
  waiver to proceed, or should be dropped from scope.
- **Hard-gate note:** **soft-delete for trips** changes `DELETE /trips/{id}` from hard to soft
  (data retention + behavior + public-contract change). If selected, it runs as its own
  high-risk-leaning story with a `### Rollback` recorded.
- **Status:** RESOLVED 2026-06-17 — human chose **all 5 items**, lowest-risk first.

## Resolution (2026-06-17)

- **Scope:** all five items approved.
- **Rate-limit waiver GRANTED:** the human selected the option naming the waiver. Interpretation
  recorded to keep it within project spirit: headers are **informational/static only**
  (`X-RateLimit-Limit/Remaining/Reset` reflecting a nominal advisory budget), **not enforced** —
  so "no rate limiting" (no enforcement) still holds; agents just get a hint to self-throttle.
  This is a deliberate, user-authorized exception to the `CLAUDE.md` scope note; if enforcement is
  ever wanted, that is a separate, re-escalated decision.
- **Soft-delete trips:** approved as a higher-risk story; will record a `### Rollback` and keep
  the row (status flag) rather than dropping data — confirmed it is hard-delete today.
- **Build order (lowest-risk first):** (1) `/healthz`+`/readyz` → (2) `operationId` sweep →
  (3) idempotency on mutating endpoints → (4) rate-limit headers → (5) soft-delete trips.
