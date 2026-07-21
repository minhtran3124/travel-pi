# rate-limit-primitive — Summary

Lane: high-risk
Confidence: high
Reason: Hard gates fired — adds a DB table + Alembic migration (data model) and introduces an enforced 429 + Retry-After on a public endpoint (public contract); scope was confirmed with the user so direction is unambiguous.
Flags: data model, audit/security, public contract, existing behavior
Affects: apps/api Alembic migration head, POST /agent/feedback contract, shared AppError handler (app/core/errors.py)
Input-type: maintenance

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

User request (verbatim, chronological — scope-deciding turns):

- "draft plan thêm cho việc implement rate limit"
- Scope decision (Q: "Phạm vi của rate-limit này nên tới đâu?") → chose **"Primitive rate-limit tái dùng"** (a reusable rate-limit dependency/service usable across multiple endpoints, not feedback-only).
- Per-IP decision (Q: "Xử lý giới hạn cho người dùng ẩn danh (per-IP) thế nào?") → chose **"Per-user DB-count now, defer per-IP"** (enforce per effective user via durable DB count now; defer per-IP/device to a follow-up needing a shared store).
- "1" → run `/feature-intake` for `rate-limit-primitive` to create `SUMMARY.md` + assign the lane.

This work originates from `specs/user-feedback-v1/REVIEW.vi.md` gap #1: the feedback API contract
promises `429` but the repo has no rate-limit enforcement.

## What changed

Intake + planning only. No runtime code or schema changed this turn. `PLAN.md` (5 tasks / 4 waves)
was drafted for a reusable, DB-backed, per-effective-user rate-limit primitive (counter table +
migration, `RateLimitError` 429, atomic window-increment repository, reusable `rate_limit(policy)`
FastAPI dependency with a subject seam for future per-IP), applied to `POST /agent/feedback` first.
Implementation is **not started** and requires an explicit go-ahead + branch.

### Rationale

Reuse the repo's existing conventions instead of adding a dependency: DB row-counting like
`quota_service`, automatic `AppError → status_code` mapping (`QuotaExceededError` already maps 429),
and the `begin_nested()`/`IntegrityError` race pattern from `booking`/`trip` repositories. DB is the
shared store, so enforcement is durable and multi-worker safe without Redis. Per-IP is deferred
because a correct cross-worker per-IP limiter needs shared state the repo does not yet have.

### Alternatives considered

- Feedback-only limiter reusing existing domain rows (like `quota_service` counts messages) —
  rejected: not reusable across endpoints, contradicting the chosen "reusable primitive" scope.
- In-memory per-process token bucket — rejected for enforcement: non-durable, not shared across
  workers; kept only as the deferred per-IP option.
- New dependency (slowapi / Redis) — rejected for v1: unnecessary given DB-backed counting suffices.
- Descope the `429` from the feedback contract entirely — rejected: the user asked to implement it.

### Deviations

- none

### Verify

<!-- No checks run yet — this turn is intake + planning only. The re-runnable checks below are
     the per-task Verify commands defined in PLAN.md, to be executed during implementation. -->

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Intake docs only — nothing executed | `n/a` | — | No runtime/schema change this turn; PLAN.md Verify rows are the pending gates |

### Rollback

- Documentation only this turn: `rm -rf specs/rate-limit-primitive/` — no application data or runtime behavior changed.
- For implementation (when executed): `../../.venv/bin/alembic downgrade -1` to drop `rate_limit_counters`, then `git revert <sha>` for code; keep the table during operational rollback and downgrade only after backup.

### Harness-Delta

- none
