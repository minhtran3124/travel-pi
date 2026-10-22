# gh-198-booking-duplicate-check-atomic — Escalations

Default: **deny-on-no-response**. No recorded decision → work stays blocked.
(Enforced: `hooks/commit-quality-gate.sh` denies commits touching this slug while any `decision:` is `pending`.)

---

## E001

- raised_by: orchestrator (feature-intake)
- date: 2026-09-15
- trigger: hard-gate | low-confidence
- question: Which mechanism makes the duplicate-intent check atomic?
- context: all implementation is blocked; each option has a different hard gate and different coverage.
- options:
  - A) Partial unique index on active rows (owner, type, reference, match key) WHERE status != 'cancelled' → IntegrityError mapped to DuplicateBookingError. Needs new columns (check_in/check_out, passengers) + Alembic migration + backfill from `details`; index creation **fails if duplicates already exist** (needs a dedupe decision = data-loss gate). Enforces for REST too → REST starts returning 409 (reopens gh-194 E001 C public contract). Strongest guarantee.
  - B) (Recommended) Per-owner transaction-scoped lock around check + insert, only when `check_duplicate=True`: `pg_advisory_xact_lock(hash(user_id))` on Postgres, `BEGIN IMMEDIATE` (or a no-op) on SQLite. No schema change, REST untouched; session-scope gate. Covers agent calls across threads/tabs.
  - C) Serialize `book_*` tool calls inside the booking specialist. Smallest diff, no DB change. Only covers one super-step, not two threads at once. Only worth doing if xia2 confirms ToolNode really runs them in parallel.
  - D) Accept the window and document it (the issue scored the risk 50: real but rare). Close with a note in the docstring and in docs/solutions.
- default_if_no_response: BLOCK
- decision: B — per-owner transaction-scoped lock around check + insert, only when check_duplicate=True (user, verbatim: "ok, dong y vs de xuat")
- decided_by: Minh Tran
- decided_at: 2026-09-15

## E002

- raised_by: orchestrator (feature-intake)
- date: 2026-09-15
- trigger: ambiguous-direction
- question: Must the fix cover the REST path, which today has no duplicate check at all?
- context: the issue names "two browser tabs" as a trigger, but REST uses `check_duplicate=False` (gh-194 E001 C). Covering REST means adding the check there too, which is a public-contract change.
- options:
  - A) (Recommended) Agent path only, consistent with gh-194 E001 C; REST unchanged.
  - B) Agent + REST: REST also checks and returns 409 on a duplicate, plus FE handling on /flights and /hotels (a separate public-contract intake).
- default_if_no_response: BLOCK
- decision: A — agent path only; REST unchanged (user, verbatim: "ok, dong y vs de xuat")
- decided_by: Minh Tran
- decided_at: 2026-09-15
