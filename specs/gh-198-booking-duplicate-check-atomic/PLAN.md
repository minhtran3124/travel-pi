---
slug: gh-198-booking-duplicate-check-atomic
status: shipped
owner: Minh Tran
created: 2026-09-15
---

# gh-198 — Make the duplicate-intent check atomic (per-owner advisory lock)

## 1. Motivation

The gh-194 duplicate-intent check (`check_duplicate=True`, agent `book_*` tools only) is a
check-then-insert with no lock. Production drives the graph with `ainvoke`. ToolNode gathers the
batch, and sync tools run via `run_in_executor` (research-brief.md), so two `book_*` calls in one
super-step run on two threads, each in its own `session_scope()`. Both can pass the check and
both insert, which yields two identical active bookings.

Decisions (ESCALATIONS.md E001 B, E002 A; design.md approved 2026-09-15):

- Take a per-owner transaction-scoped Postgres advisory lock at the top of the
  `if check_duplicate:` block.
- SQLite does nothing.
- Factory-mode misuse raises `RuntimeError`.
- REST is unchanged.

## 2. Non-goals

- REST duplicate checking; any REST route or schema edit (E002 A).
- Schema, migration or unique index (E001 A); agent tool serialization (E001 C).
- Locking on SQLite; `lock_timeout`; cross-owner races (hotel room capacity).
- Any prompt, tool-argument, `SYSTEM_COPY` or FE change.

## Global Constraints

- **Paths.** Relative to the worktree root
  `/Users/minhtran/Documents/minhtran3124/developer/travel-pi-gh-198`. Run BE commands from
  `apps/api/`. The venv lives in the MAIN checkout:
  `/Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/python`.
- **No `.env`.** Do not create `apps/api/.env` in the worktree: tests use FakeLLM + SQLite by
  default.
- **Postgres checks use a throwaway container, never the dev stack or `make test-docker`.**
  - Start: `docker run -d --rm --name gh198-pg -p 55432:5432 -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=test postgres:17-alpine`
    (image is cached locally). Wait for `docker exec gh198-pg pg_isready -U test` to exit 0.
  - Stop: `docker stop gh198-pg`.
  - `make test-docker` shares a compose project name with the dev stack and `down -v` destroys
    it.
  - A connection-refused error on SC-4, SC-5 or the Task 2.1 Verify means the container is not
    up. That is an environment problem, not a lock verdict: start the container and re-run.
  - Never run `test_booking_duplicate_concurrency.py` with `-n` / xdist. The `pg_locks`
    ungranted count of 1 assumes cases run one at a time.
- **Lock key.** `int.from_bytes(hashlib.blake2b(f"booking:{user_id}".encode(), digest_size=8).digest(), "big", signed=True)`.
  Never use Python `hash()`, which is salted per process.
- **Lock SQL** (Postgres only, dialect via `s.get_bind().dialect.name == "postgresql"`): the
  single statement `SELECT pg_advisory_xact_lock(:key)`. Never use the `pg_try_*` variant: the
  loser must wait, then see the winner's row.
- **Guard order.**
  1. A repo in factory mode (`self._s is None`) raises `RuntimeError` BEFORE the dialect branch,
     so SQLite tests catch misuse.
  2. Any other dialect (SQLite) is then a no-op.
- **Call-site order in `book_flight` / `book_hotel` is load-bearing.**
  1. `_replay` (idempotency) runs first.
  2. The flight/hotel is resolved.
  3. At the top of the `if check_duplicate:` block, call `self._repo.lock_owner_bookings(user_id)`.
  4. Only then `list_active_by_reference`, then the insert.

  `check_duplicate=False` never calls the lock.
- **Style.** Never log PII. Match surrounding docstring style (`:param:` / `:return:`). The
  helper docstring states that the caller must own the transaction, and that SQLite is
  intentionally unlocked (it backs only the unit-test suite; every running environment is
  Postgres).
- **Git.** Implement only: do not `git commit` and stage nothing. The controller serializes
  commits.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
| --- | --- | --- | --- |
| SC-1 | `lock_owner_bookings` is called exactly once per `book_flight` / `book_hotel` with `check_duplicate=True` and 0 times with `False`. A factory-mode repo raises `RuntimeError`. On SQLite the helper returns `None` without SQL error. The lock key is identical for the same user id across calls and within signed int64. | `cd apps/api && /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/python -m pytest tests/services/test_booking_owner_lock.py -q` | exit 0 |
| SC-2 | gh-194 duplicate behaviour unchanged: service raises / not-flagged cases and agent tool warn / override cases still pass | `cd apps/api && /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/python -m pytest tests/services/test_booking_duplicate.py tests/tools/test_booking_duplicate_tools.py -q` | exit 0 |
| SC-3 | REST booking contract unchanged: booking, flight and hotel route tests pass | `cd apps/api && /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/python -m pytest tests/api/booking tests/api/flight tests/api/hotel -q` | exit 0 |
| SC-4 | On Postgres, while session A holds an uncommitted duplicate-checked booking, B's identical booking is blocked: `pg_locks` reaches 1 ungranted advisory lock within 5s and B's thread is still alive. After A commits, B raises `DuplicateBookingError` and exactly 1 active row exists for that owner. Covers flight and hotel. | `cd apps/api && TEST_DATABASE_URL=postgresql+psycopg://test:test@localhost:55432/test /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/python -m pytest tests/services/test_booking_duplicate_concurrency.py -q -k blocks` | exit 0 |
| SC-5 | Negative control on Postgres: with `lock_owner_bookings` patched to a no-op, the same scenario leaves 2 active rows for that owner, which shows SC-4 depends on the lock | `cd apps/api && TEST_DATABASE_URL=postgresql+psycopg://test:test@localhost:55432/test /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/python -m pytest tests/services/test_booking_duplicate_concurrency.py -q -k without_lock` | exit 0 |
| SC-6 | On the default SQLite DB the concurrency module is skipped, not failed | `cd apps/api && /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/python -m pytest tests/services/test_booking_duplicate_concurrency.py -q` | exit 0 |
| SC-7 | Lint clean on changed code | `cd apps/api && /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/ruff check app tests/services/test_booking_owner_lock.py tests/services/test_booking_duplicate_concurrency.py` | exit 0 |
| SC-8 | Format clean on changed files | `cd apps/api && /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/ruff format --check app/repositories/booking.py app/services/booking_service.py tests/services/test_booking_owner_lock.py tests/services/test_booking_duplicate_concurrency.py` | exit 0 |

## 4. Tasks

### Task 1.1 — Per-owner lock helper + service call sites (wave 1)

- **Files:** apps/api/app/repositories/booking.py, apps/api/app/services/booking_service.py, apps/api/tests/services/test_booking_owner_lock.py
- **Action:** Write the tests first in `tests/services/test_booking_owner_lock.py`, reusing the
  `seeded_session` fixture and the flight/hotel request helpers pattern from
  `tests/services/test_booking_duplicate.py`, with a unique owner id per test (`uuid4().hex`).
  Cover:
  1. Spy via `unittest.mock.patch.object(BookingRepository, "lock_owner_bookings", autospec=True)`:
     1 call with the owner id for `book_flight(check_duplicate=True)` and for
     `book_hotel(check_duplicate=True)`; 0 calls with `check_duplicate=False`; 0 calls on an
     idempotency replay (same key twice, spy counted on the second call). Build every
     idempotency key from the per-test owner (e.g. `f"k-{owner}"`): the idempotency index is
     unique across all users, and the SQLite DB is shared for the whole session.
  2. `BookingRepository(get_session_factory(tmp_db)).lock_owner_bookings("u")` raises `RuntimeError`.
  3. On the SQLite `seeded_session`, `BookingRepository(seeded_session).lock_owner_bookings("u")`
     returns `None`.
  4. Module helper `_owner_lock_key`:
     - `_owner_lock_key("a") == _owner_lock_key("a")`;
     - `_owner_lock_key("a") != _owner_lock_key("b")`;
     - `-2**63 <= key < 2**63`.

  Then implement:
  - `_owner_lock_key(user_id: str) -> int` in `app/repositories/booking.py`, as specified in
    Global Constraints.
  - `BookingRepository.lock_owner_bookings(user_id: str) -> None`, with the guard order and SQL
    from Global Constraints and a docstring citing gh-198.
  - The single call at the top of each `if check_duplicate:` block in
    `BookingService.book_flight` and `book_hotel`.
  - An update to both service docstrings: one sentence saying the check + insert is serialized
    per owner on Postgres (gh-198).
- **Verify:** `cd apps/api && /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/python -m pytest tests/services/test_booking_owner_lock.py tests/services/test_booking_duplicate.py tests/tools/test_booking_duplicate_tools.py -q`
- **Done:** SC-1 and SC-2 checks exit 0 (the Verify command). The SC-3 check run separately exits 0. `grep -c "self._repo.lock_owner_bookings(user_id)" app/services/booking_service.py` prints `2`.
- **Criteria:** SC-1, SC-2, SC-3
- **Interfaces:** Consumes the existing Repo live/factory modes in app/repositories/base.py and the gh-194 check_duplicate blocks (pre-existing, no producer task). Produces `_owner_lock_key` and `BookingRepository.lock_owner_bookings` in `apps/api/app/repositories/booking.py`, the call sites in `apps/api/app/services/booking_service.py`, and `apps/api/tests/services/test_booking_owner_lock.py`.

### Task 2.1 — Deterministic Postgres concurrency test + negative control (wave 2)

- **Files:** apps/api/tests/services/test_booking_duplicate_concurrency.py
- **Action:** Create the module.
  - **Skip on non-Postgres:** use a module-level `pytestmark = pytest.mark.skipif(...)` that is
    true unless `os.environ.get("TEST_DATABASE_URL", "").startswith("postgresql")`.
  - **Scenario helper**, parametrized over flight and hotel (seeded inventory as in
    `tests/services/test_booking_duplicate.py`, fresh `uuid4().hex` owner per case, sessions from
    `get_session_factory(tmp_db)`, and depending on `seeded_session` so reference data exists):
    1. Open session A. Call `BookingService(a).book_*(req, user_id=owner, idempotency_key=f"k-a-{owner}", check_duplicate=True)`.
       Do NOT commit. The keys MUST embed the owner: `ix_bookings_idempotency_key` is unique
       across ALL users (`app/db/models/booking.py:26-32`), and SC-4, SC-5 and the Verify reuse
       one container, so fixed keys would collide on that index instead of exercising the lock.
    2. Start a `threading.Thread` for B. B opens its own session, calls the same booking with
       `idempotency_key=f"k-b-{owner}"`, commits on success, and stores the outcome (booking or
       exception).
    3. Poll on a third session, every 0.05s with a 5s deadline, until
       `SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND NOT granted` returns 1.
       Record the last value read.
    4. Record `thread.is_alive()`.
    5. `a.commit()`, then `thread.join(timeout=10)`.
    6. Count active bookings for the owner via
       `BookingRepository(factory).list_active_by_reference`.
  - **`test_concurrent_duplicate_blocks_and_rejects[flight|hotel]`** asserts:
    - the polled ungranted advisory count reached 1 before the deadline;
    - B was alive at that point;
    - B's outcome after A commits is a `DuplicateBookingError`;
    - the active row count is 1.
  - **`test_concurrent_duplicate_without_lock_double_books[flight|hotel]`** patches
    `BookingRepository.lock_owner_bookings` to a no-op (`patch.object(..., return_value=None)`)
    and skips steps 3–4. It asserts:
    - B finished within `thread.join(timeout=5)` while A was still uncommitted;
    - B's outcome is a booking;
    - the active row count is 2 after A commits.
  - **Cleanup:** close every session in `finally`.
  - **Run:** start the throwaway container per Global Constraints for the Verify, and stop it
    afterwards.
- **Verify:** `cd apps/api && TEST_DATABASE_URL=postgresql+psycopg://test:test@localhost:55432/test /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/python -m pytest tests/services/test_booking_duplicate_concurrency.py -q`
- **Done:** SC-4, SC-5, SC-6, SC-7 and SC-8 checks exit 0. The Postgres run reports `4 passed`. The SQLite run reports `4 skipped`.
- **Criteria:** SC-4, SC-5, SC-6, SC-7, SC-8
- **Interfaces:** Consumes `BookingRepository.lock_owner_bookings` and the lock call sites from Task 1.1, plus the tmp_db / seeded_session fixtures in tests/conftest.py (pre-existing, no producer task). Produces `apps/api/tests/services/test_booking_duplicate_concurrency.py`.

## 5. Risks

- **SC-4 could pass without the lock** if A were committed before B's check. Mitigated: A stays
  open until after the blocked-state assertions, and SC-5 must show 2 rows with the lock stubbed.
- **Shared test DB.** SC-4, SC-5 and the Task 2.1 Verify reuse one container, and committed rows
  accumulate across runs. Mitigated by a unique owner per case and owner-derived idempotency keys
  (the idempotency index is unique across all users). Hotel inventory cannot run out:
  `is_available` / `available_rooms` are deterministic hashes with no DB read
  (`app/services/hotel_service.py:73-106`).
- **`pg_locks` count 1 assumes nothing else is waiting on an advisory lock.** True on the
  isolated throwaway DB. The count must not be read on the dev DB.
- **SQLite still has the race by design.** It backs only the unit-test suite; dev and local
  both run Docker + Postgres (user, 2026-09-15). Recorded under SUMMARY *Not auto-verified*.
- **Live model reproduction** (two parallel `book_*` calls from a real model) is not covered
  offline. Recorded under Not auto-verified.

## 6. Status Log

- 2026-09-15 — Plan written after intake (high-risk), E001 B / E002 A, design.md approved
  (SQLite no lock), and research-brief.md (Deep).
- 2026-09-15 — Plan review:
  - iteration 1: Issues Found. A global unique idempotency index collided with fixed keys; the
    pg_locks timing was flaky; the Risks section had two errors; lint and format were merged.
  - iteration 2: Approved. Advisory notes (container-down, no xdist) folded into Global
    Constraints.
  - `check_plan_contract.py` exit 0.
- 2026-09-15 — task 1.1 complete; commit 3b082d7; review spec=pass quality=approved (first pass spec
  `cannot_verify` → controller re-ran Verify 33 passed, SC-3 201 passed, format clean, grep=2 → re-review pass).
  First implementer dispatch BLOCKED (launched with cwd = main checkout; hooks refused all writes) → re-dispatched
  from the worktree with python-heredoc edits. Minor (open, to final chain): M1 unit tests do not pin lock-before-
  check order (Task 2.1 covers it); M2 lock is exercised only on Postgres (Task 2.1); M3 same-idempotency-key race
  before `_replay` relies on the global unique index — confirm it surfaces as replay/clean error, not 500; M4 replay
  no-lock spy covers book_flight only.
- 2026-09-15 — task 2.1 complete; commit f028932; review spec=pass quality=approved (first pass spec
  `cannot_verify` on SC-7/SC-8 → controller re-ran SC-4..SC-8 + mutation check (both call sites removed →
  `-k blocks` 2 failed, restored) → re-review pass). Minor (open, to final chain): M5 `finally` does not join
  thread B before closing sessions; M6 `pg_locks` ungranted count is cluster-wide, not owner-keyed; M7 rows
  accumulate in the reused container (owner-derived keys prevent collisions).
- 2026-09-15 — final chain on ef9aec1..f028932: intent review pass (no gap/drift/excess); correctness review 6
  angles → 4 locations scored 50/25/0/0 (none >= 75; all recorded as advisory in SUMMARY). User decided to fix
  CR-1 anyway (same-idempotency-key concurrent calls get DuplicateBookingError instead of replay, introduced by
  this branch): re-run `_replay` right after `lock_owner_bookings`, plus a same-key Postgres test. Fix-up dispatched.
- 2026-09-15 — CR-1 fix-up complete; commit 447dc39. The same-key Postgres test failed before the fix
  (exit 1, B got DuplicateBookingError) and passes after it. Controller re-ran: Postgres concurrency module 6 passed;
  SQLite 33 passed + 6 skipped. Correctness re-review of the fix is next.
- 2026-09-15 — CR-1 re-review closed (no new defects); intent re-review of the fix passed; verify_summary
  --check 9/9 PASS at 447dc39; review receipt pinned at 447dc39 (correctness + intent pass, 0 blocking,
  3 advisory: CR-2/CR-3/CR-4). All tasks complete (1.1 3b082d7, 2.1 f028932; fix-up 447dc39); status shipped, PR next.
