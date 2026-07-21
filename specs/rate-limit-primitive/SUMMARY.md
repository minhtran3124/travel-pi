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

**Waves 1–3 implemented and green** on branch `feat/rate-limit-primitive`; **wave 4 deferred**
(blocked on the `user-feedback-v1` feedback endpoint, which is not yet built).

- Wave 1 (`847cc63`): `RateLimitCounter` model + reversible migration (`d2f4b6a8c0e1` →
  `e1a2b3c4d5f6`), `RateLimitError(AppError, 429)` with `retry_after`, `feedback_rate_limit_*` settings.
- Wave 2 (`1b9bae2`): `RateLimitRepository.hit()` — atomic `UPDATE count = count + 1`, race-safe
  first-insert, elapsed-window prune, `RateLimitDecision(allowed/remaining/reset_at/retry_after)`.
- Wave 3 (`7615bb4`): `enforce_rate_limit()` core callable + reusable `rate_limit()` FastAPI
  dependency (subject seam for future per-IP), `errors.py` emits `Retry-After` for `RateLimitError`.

Wave 4 (`Depends(rate_limit(...))` on `POST /agent/feedback`) is ready to wire once that endpoint
exists — the primitive is endpoint-independent and the feedback route can also call
`enforce_rate_limit()` directly with its body-resolved anonymous subject.

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

- Rule 2 — `errors.py` emits only `Retry-After` for `RateLimitError` (not real `X-RateLimit-*`
  values as the plan's T3.1 wording suggested). The `_rate_limit_headers` middleware overwrites
  `X-RateLimit-*` on every response, so setting them in the handler would be clobbered; `Retry-After`
  is the actionable header and is untouched by that middleware. Commit `7615bb4`.
- Rule 2 — Used module-level `Depends` aliases in `rate_limit.py` (not inline `Annotated`) because
  Python 3.14 deferred annotations fail to resolve inline `Annotated[..., Depends(...)]` inside a
  nested dependency function. Matches the repo's `SessionDep`/`OptionalUserDep` convention. Commit `7615bb4`.
- Scope — Wave 4 not executed: it depends on the `POST /agent/feedback` endpoint from
  `specs/user-feedback-v1`, which is unimplemented. Recorded as a blocker, not silently skipped.
- Rule 1 (post-review hardening, commit `71638a5`) — an adversarial correctness review confirmed the
  core sound (window math, atomicity, rowcount) and found 4 defects, all fixed: (1) default subject
  resolver now limits authenticated callers only — dropped the spoofable query `user_id` fallback that
  enabled bypass + cross-user DoS; (2) the increment commits in its own transaction so erroring/blocked
  requests are still counted (was tied to the request UoW → under-count); (3/4) prune keeps a one-window
  grace margin so clock skew can't wipe the active window or trigger a `scalar_one` race.
- Test quality — rate-limit repo/migration tests switched from hard-coded SQLite to the `tmp_db`
  fixture, so `make test-docker` genuinely exercises them on Postgres (verified: 8 pass on the dev
  Postgres). The dependency test stays isolated SQLite by design (HTTP behaviour is engine-agnostic).

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Alembic round-trip | `DATABASE_URL=sqlite:///$tmp alembic upgrade head && alembic downgrade -1 && alembic upgrade head` | 0 | `d2f4b6a8c0e1` ↔ `e1a2b3c4d5f6` clean |
| Wave 1 tests | `pytest tests/db/test_rate_limit_migration.py tests/core/test_rate_limit_config.py -q` | 0 | 8 passed |
| Wave 2 tests | `pytest tests/db/test_rate_limit_repository.py -q` | 0 | 5 passed (limit boundary, window reset, subject/bucket isolation, prune) |
| Wave 3 tests | `pytest tests/api/test_rate_limit_dependency.py -q` | 0 | 4 passed |
| Error-envelope regression | `pytest tests/infra/test_errors.py + rate-limit suite -q` | 0 | 87 passed — errors.py change safe |
| Full-suite import sanity | `pytest --co -q` | 0 | 1790 tests collected, no import breakage from new model |
| tests/db full | `pytest tests/db -q` | 0 | 36 passed |
| Post-fix all-engines | `pytest <rate-limit suite> -q` | 0 | 19 passed on SQLite (incl. review-fix tests) |
| Postgres parity | `TEST_DATABASE_URL=…5433 pytest test_rate_limit_repository.py test_rate_limit_migration.py -q` | 0 | 8 passed on real Postgres (atomic increment + unique constraint) |

### Rollback

- Documentation only this turn: `rm -rf specs/rate-limit-primitive/` — no application data or runtime behavior changed.
- For implementation (when executed): `../../.venv/bin/alembic downgrade -1` to drop `rate_limit_counters`, then `git revert <sha>` for code; keep the table during operational rollback and downgrade only after backup.

### Harness-Delta

- none
