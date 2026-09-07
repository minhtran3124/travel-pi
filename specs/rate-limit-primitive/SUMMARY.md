# rate-limit-primitive — Summary

Lane: high-risk
Confidence: high
Reason: Hard gates fired — adds a DB table + Alembic migration (data model) and prepares an enforced
429 + Retry-After public contract; endpoint integration remains explicitly deferred to Task 4.1.
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
- Follow-up review of `83101fc..HEAD` requested remediation of P1–P3 correctness, migration,
  concurrency, HTTP-header, deployment-discovery, and audit-record findings without pulling the
  still-unimplemented feedback endpoint into scope.

This work originates from `specs/user-feedback-v1/REVIEW.vi.md` gap #1: the feedback API contract
promises `429` but the repo has no rate-limit enforcement.

## What changed

**Waves 1–3 and review-remediation Wave 5 are implemented** on branch
`feat/rate-limit-primitive`; **wave 4 remains deferred** (blocked on the `user-feedback-v1`
feedback endpoint, which is not yet built). Wave 5 evidence is tracked separately below so
historical results are not presented as proof of the new fixes.

- Wave 1 (`847cc63`): `RateLimitCounter` model + reversible migration (`d2f4b6a8c0e1` →
  `e1a2b3c4d5f6`), `RateLimitError(AppError, 429)` with `retry_after`, `feedback_rate_limit_*` settings.
- Wave 2 (`1b9bae2`): `RateLimitRepository.hit()` — atomic `UPDATE count = count + 1`, race-safe
  first-insert, elapsed-window prune, `RateLimitDecision(allowed/remaining/reset_at/retry_after)`.
- Wave 3 (`7615bb4`): `enforce_rate_limit()` core callable + reusable `rate_limit()` FastAPI
  dependency (subject seam for future per-IP), `errors.py` emits `Retry-After` for `RateLimitError`.
- Wave 5 Task 5.1: preserved committed revision `e1a2b3c4d5f6` and added descendant migration
  `f3b7c9d1e5a2`; versioned persisted policy identity by `window_seconds`, stored 64-bit epochs,
  persisted/indexed `prune_after` for row-specific expiry with a one-window clock-skew grace, and
  added real Alembic round-trip plus synchronized distinct-session concurrency coverage.
- Wave 5 Task 5.2: fail-fast pre-transaction enforcement prevents SQLite self-lock without
  committing caller work; enforced responses now publish truthful `X-RateLimit-*` metadata while
  non-enforced routes retain nominal headers.
- Wave 5 Task 5.3: advertised both feedback limiter environment defaults and refreshed this
  high-risk handoff with the review scope, evidence boundary, and exact rollback sequence.

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
  is the actionable header and is untouched by that middleware. Commit `7615bb4`. Wave 5 Task 5.2
  supersedes this accepted deviation by requiring truthful policy headers on enforced routes.
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
  Postgres). That historical run covered ORM shape/uniqueness and repository behavior, not a
  pytest-driven Alembic downgrade or synchronized concurrent hits; Wave 5 Task 5.1 closes those
  evidence gaps. The dependency test stays isolated SQLite by design, while Task 5.2 adds a
  production-middleware-stack regression for response headers and transaction ordering.
- Review remediation scope — Wave 5 Tasks 5.1–5.3 cover the P1–P3 findings: a descendant `f3`
  migration, stable policy identity, 64-bit epoch storage, indexed `prune_after`, real migration
  round-trips, cross-session concurrency, explicit SQLite transaction ordering, truthful
  enforced-route headers, discoverable env settings, and an exact audit/rollback handoff. Task 4.1
  remains the sole deferred endpoint integration item.

### Verify — historical waves 1–3

These rows preserve the results recorded when the original waves and first hardening pass landed.
They do not claim coverage of the later Wave 5 remediation.

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

### Verify — Wave 5 remediation

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Task 5.1 migration/repository evidence | `cd apps/api && review_db_dir="$(mktemp -d)" && DATABASE_URL="sqlite:///$review_db_dir/app.db" ../../.venv/bin/python -m pytest -p no:rerunfailures tests/db/test_rate_limit_migration.py tests/db/test_rate_limit_repository.py -q` | 0 | 10 passed, including real old-head → `f3` → old-head → `f3` Alembic coverage and synchronized distinct-session concurrency |
| Wave 5 integrated SQLite | `cd apps/api && review_db_dir="$(mktemp -d)" && DATABASE_URL="sqlite:///$review_db_dir/app.db" ../../.venv/bin/python -m pytest -p no:rerunfailures tests/api/test_rate_limit_dependency.py tests/core/test_rate_limit_config.py tests/db/test_rate_limit_migration.py tests/db/test_rate_limit_repository.py tests/infra/test_errors.py tests/test_db_models.py -q` | 0 | 49 passed |
| Wave 5 targeted PostgreSQL 17 | `cd apps/api && docker compose -f docker-compose.test.yml run --rm --entrypoint pytest tests -p no:rerunfailures tests/api/test_rate_limit_dependency.py tests/core/test_rate_limit_config.py tests/db/test_rate_limit_migration.py tests/db/test_rate_limit_repository.py tests/infra/test_errors.py tests/test_db_models.py -q` | 0 | 49 passed against ephemeral PostgreSQL, including migration round-trip and concurrent counter hits |
| Alembic metadata parity | `cd apps/api && review_db_dir="$(mktemp -d)" && DATABASE_URL="sqlite:///$review_db_dir/app.db" ../../.venv/bin/alembic upgrade head && DATABASE_URL="sqlite:///$review_db_dir/app.db" ../../.venv/bin/alembic current && DATABASE_URL="sqlite:///$review_db_dir/app.db" ../../.venv/bin/alembic check && ../../.venv/bin/alembic heads` | 0 | Sole head/current revision `f3b7c9d1e5a2`; no new upgrade operations detected |
| Wave 5 lint/format | `cd apps/api && ../../.venv/bin/ruff check app/core/errors.py app/core/middleware.py app/core/rate_limit.py app/db/models/rate_limit_counter.py app/exceptions.py app/repositories/rate_limit.py alembic/versions/f3b7c9d1e5a2_harden_rate_limit_counters.py tests/api/test_rate_limit_dependency.py tests/db/test_rate_limit_migration.py tests/db/test_rate_limit_repository.py tests/infra/test_errors.py && ../../.venv/bin/ruff format --check app/core/errors.py app/core/middleware.py app/core/rate_limit.py app/db/models/rate_limit_counter.py app/exceptions.py app/repositories/rate_limit.py alembic/versions/f3b7c9d1e5a2_harden_rate_limit_counters.py tests/api/test_rate_limit_dependency.py tests/db/test_rate_limit_migration.py tests/db/test_rate_limit_repository.py tests/infra/test_errors.py` | 0 | Ruff clean; all 11 checked files formatted, including the new descendant migration |
| Task 5.3 deploy/audit hygiene | `git diff --check -- apps/api/.env.example specs/rate-limit-primitive/SUMMARY.md` | 0 | Env defaults and audit handoff are whitespace-clean; run from repository root |
| Env-isolated full backend suite | `review_db_dir="$(mktemp -d)" && PYTHONPATH=apps/api DATABASE_URL="sqlite:///$review_db_dir/app.db" .venv/bin/python -m pytest -p no:rerunfailures apps/api/tests -q -k 'not test_city_route_unknown_origin_returns_404'` | 0 | 1802 passed, 1 deselected: the excluded pre-existing city-route case calls Open-Meteo for an unknown city and returns 502 when network is unavailable |

### Rollback

- Back up `rate_limit_counters` if its transient operational counts must be retained. While the
  descendant migration file still exists, run `../../.venv/bin/alembic downgrade d2f4b6a8c0e1`
  from `apps/api/`; the `f3` downgrade intentionally deletes counters before collapsing policy
  identities, then the `e1` downgrade drops the table.
- Wave 5 is currently uncommitted. After the database downgrade, discard its tracked owned-file
  edits with `git restore -- apps/api/.env.example apps/api/app/core/errors.py apps/api/app/core/middleware.py apps/api/app/core/rate_limit.py apps/api/app/db/models/rate_limit_counter.py apps/api/app/exceptions.py apps/api/app/repositories/rate_limit.py apps/api/tests/api/test_rate_limit_dependency.py apps/api/tests/db/test_rate_limit_migration.py apps/api/tests/db/test_rate_limit_repository.py apps/api/tests/infra/test_errors.py specs/rate-limit-primitive/PLAN.md specs/rate-limit-primitive/SUMMARY.md`, then remove only the new untracked descendant migration with `git clean -f -- apps/api/alembic/versions/f3b7c9d1e5a2_harden_rate_limit_counters.py`.
- From the repository root, revert the implemented historical code/test commits in safe reverse
  order: `git revert d9cadb8 b3b149b 853e3f4 735c3dc 71638a5 7615bb4 1b9bae2 847cc63`.
- Replace the worktree restore/clean commands above with the Wave 5 commit SHA after committing.
- Wave 4 has no rollback action because `POST /agent/feedback` is still deferred and no feedback
  route or event persistence was added on this branch.

### Harness-Delta

- None. Wave 5 changes application code, migration/tests, deployment documentation, and the feature
  audit record only; it does not change hooks, skills, tool registration, or harness policy.

### Verify

<!-- Retrofitted 2026-09-03 when this plan's status was retired from `active`. The rows below
     were RUN on that date against the shipped code — they are not a record of what was run
     during the original work, which predates the lane-evidence rule. -->

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| rate-limit dependency, config and repo | `cd apps/api && env OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/x.db ../../.venv/bin/python -m pytest tests/api/test_rate_limit_dependency.py tests/core/test_rate_limit_config.py tests/db/test_rate_limit_repository.py -q` | 0 | 27 passed |

### Not auto-verified

- Task 4.1 (wiring the limiter onto `POST /agent/feedback`) is still BLOCKED on
  `specs/user-feedback-v1` and is therefore unbuilt, not merely unverified. This is why the plan
  is `paused` rather than `shipped`.
