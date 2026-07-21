---
slug: rate-limit-primitive
status: proposed
owner: minhtran
created: 2026-07-21
---

# Reusable Rate-Limit Primitive (per-user, DB-backed)

## 1. Motivation

`specs/user-feedback-v1` promises `429 — Dedicated feedback abuse limit exceeded` in its API contract
(`DESIGN.md §5.2`, `RESEARCH.md §9/§10`), but the repo has **no rate-limit enforcement** — only
informational, unenforced `X-RateLimit-*` headers (`app/core/middleware.py:65-75`), as CLAUDE.md
states. The daily `check_quota` guard (`app/services/quota_service.py`) is a per-day turn budget, not an
abuse limiter. Without this, the feedback endpoint's `429` is fiction and anonymous callers (whose id is
client-asserted) can flood feedback.

This plan builds a **reusable, durable, per-effective-user rate-limit primitive** — a generic
sliding/fixed-window counter usable by any endpoint — and wires it into `POST /agent/feedback` first.
It reuses the existing conventions: DB row counting (like `quota_service`), the `AppError → status_code`
mapping (`QuotaExceededError` already maps to 429 via `app/core/errors.py`), and the atomic
`begin_nested()`/`IntegrityError` race pattern from `repositories/booking.py`/`trip.py`.

Chosen scope (per decision): **reusable primitive** (not feedback-only) with **per-user enforcement via
DB count now; per-IP/device deferred** to a follow-up once a shared store (e.g. Redis) exists. The
subject resolver is a seam so per-IP can be added without reworking the primitive.

**Lane: high-risk** — adds a DB table + Alembic migration (hard gate) and introduces a new enforced
`429` on a public endpoint. Additive and reversible. Run `/feature-intake` to record `SUMMARY.md` and
branch before executing.

## 2. Non-goals

- No per-IP/device limiting in this PR (deferred — needs shared cross-worker state).
- No new dependency (no slowapi/Redis); DB is the shared store.
- No global middleware limiter on every route; enforcement is opt-in per endpoint via a dependency.
- No change to the existing informational `X-RateLimit-*` header middleware behavior beyond emitting
  real values on limited routes.
- No change to the daily `check_quota` budget.

## 3. Success Criteria

- A reusable `rate_limit(policy)` FastAPI dependency exists and can be attached to any route.
- The N+1th request from one effective user within the window returns `429` with a `Retry-After`
  header; requests after the window resets are allowed again.
- Enforcement is durable and correct across multiple workers (DB-backed atomic increment), not
  per-process memory.
- `POST /agent/feedback` is rate-limited for both JWT and anonymous principals, and a rejected request
  creates **no** `feedback_event` row.
- Migration upgrades/downgrades cleanly on SQLite and Postgres.
- The subject resolver is documented as the seam for a future per-IP limiter.

## 4. Tasks

### Task 1.1 — Counter model + reversible migration (wave 1)

- **Files:** apps/api/app/db/models/rate_limit_counter.py, apps/api/app/db/models/__init__.py, apps/api/alembic/versions/<revision>_add_rate_limit_counters.py, apps/api/tests/db/test_rate_limit_migration.py
- **Action:** Add a `RateLimitCounter` model with columns `bucket` (policy name, string), `subject`
  (effective actor id, string), `window_start` (integer epoch seconds), `count` (integer), plus repo
  timestamp mixin. Unique constraint `(bucket, subject, window_start)`; index `(bucket, subject,
  window_start)` for lookups and `(window_start)` for pruning. Add a migration descending from the
  single current head `d2f4b6a8c0e1` that creates the table with constraints/indexes on SQLite and
  Postgres; downgrade drops it.
- **Verify:** `cd apps/api && ../../.venv/bin/alembic upgrade head && ../../.venv/bin/alembic downgrade -1 && ../../.venv/bin/alembic upgrade head && ../../.venv/bin/python -m pytest tests/db/test_rate_limit_migration.py -q`
- **Done:** Migration applies and reverses cleanly on both engines; unique/index present; model imports.

### Task 1.2 — 429 error type + tunable policy settings (wave 1)

- **Files:** apps/api/app/exceptions.py, apps/api/app/core/config.py, apps/api/tests/core/test_rate_limit_config.py
- **Action:** Add `RateLimitError(AppError)` with `status_code = 429` carrying a `retry_after: int`
  (seconds) so the error handler can emit `Retry-After`. Add settings
  `feedback_rate_limit_max` (default 30) and `feedback_rate_limit_window_seconds` (default 60), plus a
  generic default so other policies can be declared later. Keep values env-overridable like the
  existing `agent_free_daily_turn_limit`.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/core/test_rate_limit_config.py -q`
- **Done:** `RateLimitError('x', retry_after=60).status_code == 429`; settings load with defaults and
  env overrides.

### Task 2.1 — RateLimitRepository: atomic window increment (wave 2)

- **Files:** apps/api/app/repositories/rate_limit.py, apps/api/tests/db/test_rate_limit_repository.py
- **Action:** Implement `hit(*, bucket, subject, now_epoch, limit, window_seconds) -> RateLimitDecision`
  (`allowed: bool`, `remaining: int`, `reset_at: int`). Compute `window_start = now_epoch -
  (now_epoch % window_seconds)`. Perform an **atomic** upsert-increment (`INSERT ... ON CONFLICT
  (bucket, subject, window_start) DO UPDATE SET count = count + 1 RETURNING count`) so concurrent
  workers cannot exceed the limit; recover from `IntegrityError` via the existing `begin_nested()`
  savepoint convention if the dialect path needs it. Opportunistically delete counter rows with
  `window_start < now_epoch - window_seconds` to bound table growth. `allowed = returned_count <= limit`.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/db/test_rate_limit_repository.py -q`
- **Done:** Increment is atomic; the limit+1th hit in a window is `allowed=False`; a hit in the next
  window resets; expired rows are pruned; SQLite/Postgres parity holds.

### Task 3.1 — Reusable dependency + Retry-After mapping (wave 3)

- **Files:** apps/api/app/core/rate_limit.py, apps/api/app/core/errors.py, apps/api/tests/api/test_rate_limit_dependency.py
- **Action:** Add a dependency factory `rate_limit(*, name, limit, window_seconds, subject=default)`
  returning a FastAPI dependency that resolves the subject (default = effective user id via the same
  precedence as `_effective_user_id`; IP resolver left as a documented seam), calls
  `RateLimitRepository.hit`, and raises `RateLimitError(retry_after=reset_at-now)` on `allowed=False`.
  Update the `AppError` handler in `core/errors.py` so a `RateLimitError` response includes
  `Retry-After` and real `X-RateLimit-*` values (Remaining/Reset), without altering other error
  envelopes.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/api/test_rate_limit_dependency.py -q`
- **Done:** A route guarded by the dependency allows up to `limit`, then returns `429` with
  `Retry-After`; the subject seam is unit-covered; other error responses are unchanged.

### Task 4.1 — Enforce on POST /agent/feedback (wave 4)

- **Files:** apps/api/app/routers/feedback.py, apps/api/tests/api/agent/test_feedback_rate_limit.py
- **Action:** Attach `Depends(rate_limit(name="feedback", limit=settings.feedback_rate_limit_max,
  window_seconds=settings.feedback_rate_limit_window_seconds))` to the feedback route so it runs
  **before** service/persistence — a rejected request must not append a `feedback_event`. Ensure both
  JWT and anonymous principals are limited by their effective subject. Depends on the feedback endpoint
  from `specs/user-feedback-v1` Task 2.1 existing.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_feedback_rate_limit.py -q`
- **Done:** The limit+1th feedback POST in the window returns `429` + `Retry-After`; no event row is
  written for the rejected call; after window reset the caller can post again; authenticated and
  anonymous both enforced.

## 5. Risks

- **Fixed-window burst:** a fixed window allows up to 2×limit across a boundary. Acceptable for a coarse
  abuse limit; note it and switch to a sliding window later if abuse patterns demand.
- **Counter table growth:** unbounded without pruning; Task 2.1 prunes expired windows opportunistically.
  If prune coverage is uneven under load, add a periodic cleanup later.
- **Cross-worker atomicity:** relies on DB-level `ON CONFLICT ... RETURNING` atomicity; verify parity on
  Postgres via `make test-docker`, not only SQLite.
- **Anonymous weakness:** the subject is a client-asserted anonymous id, so a determined attacker can
  rotate ids to evade per-user limits. Documented gap; per-IP/device is the deferred hardening.
- **Ordering vs persistence:** the dependency must execute before the feedback service writes; if wired
  after, spam still creates events. Task 4.1 asserts no row on rejection.
- **Schema-change gotcha:** after adding the table, rebuild `travel.db` or the suite fails (lifespan
  seeds the real DB); run `make test-docker` for engine parity. See memory
  `stale-travel-db-breaks-suite-on-schema-change`.
- **errors.py blast radius:** editing the shared `AppError` handler is sensitive; keep the change scoped
  to adding headers for `RateLimitError` only and assert other envelopes are unchanged.

## 6. Status Log

- 2026-07-21 — Plan drafted from `specs/user-feedback-v1/REVIEW.vi.md` gap #1. Scope decided: reusable
  DB-backed primitive, per-user enforcement now, per-IP deferred. Implementation not started;
  `/feature-intake` + branch required before executing (high-risk lane).
- 2026-07-21 — Intake: high-risk / high-confidence (`SUMMARY.md`). Branch `feat/rate-limit-primitive`
  off `v3`.
- 2026-07-21 — Waves 1–3 shipped and green. Commits: 1.1+1.2 `847cc63`, 2.1 `1b9bae2`, 3.1 `7615bb4`.
  Verify: alembic round-trip clean; 87 tests pass (rate-limit suite + error-envelope regression);
  1790 tests collect with no import breakage.
- 2026-07-21 — Task 4.1 **BLOCKED**: depends on `POST /agent/feedback` from `specs/user-feedback-v1`,
  which is not yet implemented. Wire `Depends(rate_limit(...))` (or call `enforce_rate_limit()` with
  the body-resolved anonymous subject) when that endpoint lands.
