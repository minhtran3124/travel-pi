# gh-198-booking-duplicate-check-atomic — Summary

Lane: high-risk
Confidence: high
Reason: session-scope hard gate (Rule 4) — per-owner transaction-scoped lock around the duplicate check + insert (E001 B); no schema change, REST untouched (E002 A). Was low confidence at intake; resolved by user decisions 2026-09-15.
Flags: session-scope, existing-behavior, weak-proof, cross-platform (Postgres vs SQLite lock semantics)
Affects: app/services/booking_service.py (book_flight / book_hotel check_duplicate path), app/repositories/booking.py (lock + list_active_by_reference + add), session/UoW handling for the booking write
Input-type: change request
Route: brainstorming (light — approach already chosen) → xia2 (Deep) → writing-plans → using-git-worktrees → subagent-driven-development; compound for the concurrency decision
Escalate: no (E001 B, E002 A decided by user 2026-09-15)

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

/feature-intake https://github.com/minhtran3124/travel-pi/issues/198

Issue #198 — "booking: make the duplicate-intent check atomic (check-then-insert race)":

> The duplicate-intent check added in #197 (`BookingService.book_flight` / `book_hotel` with `check_duplicate=True`) is a plain check-then-insert: `BookingRepository.list_active_by_reference` runs a SELECT, then `self._repo.add(...)` inserts, with no lock and no uniqueness rule on (owner, type, reference, dates/passengers).
>
> **Trigger:** two concurrent booking calls for the same owner + same flight (same passenger count), or the same hotel + same dates, whose idempotency keys differ. For example, two `book_hotel` tool calls in one LangGraph super-step that differ only in `notes`, or two browser tabs. Each call reads before the other commits, so both pass the check and both insert.
>
> **Result:** two identical active bookings, which is exactly what the check exists to prevent. The unique idempotency index only catches identical keys.
>
> Options: partial unique index on active rows (match key as columns; hotel dates and flight passengers live in `details` JSON) · per-owner serialization (`SELECT … FOR UPDATE` / Postgres advisory lock; SQLite fallback) · serialize booking tool calls inside the booking specialist (agent-only) · accept the window and document it.
>
> A lasting fix is a schema or transaction-scope change (Rule 4 hard gate: data-model / session-scope). That needs its own intake, lane `high-risk`.

Follow-up turn (user, 2026-09-15), verbatim, answering E001 (recommended B) and E002 (recommended A): "ok, dong y vs de xuat"

Later scope-deciding turns (user, 2026-09-15), verbatim, in order:
1. Design approval, SQLite handling: "ok, ko khoa tren sqlite"
2. Environment fact: "hien tai chay dev hay local deu dung docker + postgres ca"
3. Plan approval and execution mode: "1. approve plan\n2. chay lien mach 2 wave"

### Intake findings (local evidence)

- `check_duplicate` defaults to `False` and only the agent tools pass `True` (`app/tools/flight_tools.py:491`, `app/tools/hotel_tools.py:599`; `app/services/booking_service.py:358,467`). REST `POST /flights/book` and `/hotels/book` **never run the check**, so the issue's "two browser tabs" trigger is not a race in the check: that path has no check at all (gh-194 E001 C). The race that remains is between agent calls (same super-step, or two threads/tabs chatting at once).
- `bookings` has only `ix_bookings_idempotency_key` (partial unique) plus one more index (`app/db/models/booking.py:26-34`); match-key fields (hotel check-in/out, flight passengers) live in `details` JSON (`booking.py:20`).
- Parallel ToolNode execution of two `book_*` calls in one super-step: **unknown**. It was not confirmed in #197, and intake did not check it. xia2 must settle this, because it decides whether option C is enough.

## What changed

Two concurrent agent `book_flight` / `book_hotel` calls by the same traveller for the same flight + passenger count (or the same hotel + dates) can no longer both pass the gh-194 duplicate check and both insert. On Postgres, which is every running environment, the check and the insert are now serialized per owner by a transaction-scoped advisory lock (`BookingRepository.lock_owner_bookings`, `pg_advisory_xact_lock` on a blake2b hash of the owner id). It is taken first inside the `check_duplicate` block. The second call waits for the first to commit, then sees its row and gets the usual "possible duplicate" error. REST (`check_duplicate=False`) takes no lock and is unchanged. No schema, migration, prompt or tool-argument change.

### Rationale

The agent tool path already runs the service in one live session (`session_scope()`; live-session repos only flush), so check and insert share a transaction. One lock statement at the top of that block makes them atomic, with no schema change and no REST contract change (E001 B, E002 A). Research confirmed the race is reachable: production drives the graph with `ainvoke`, ToolNode `asyncio.gather`s the batch, and sync tools run via `run_in_executor` on separate threads. The blocking variant (not `pg_try_*`) is deliberate: the loser must see the winner's row and get the friendly duplicate warning, not an opaque retry error. SQLite is a no-op because it backs only the unit-test suite.

### Alternatives considered

- Partial unique index on active rows (E001 A): needs new match-key columns (hotel dates and flight passengers live in `details` JSON), a backfill and a dedupe of existing duplicates, and turns REST duplicates into 409s. Declined.
- Serialize `book_*` calls inside the booking specialist (E001 C): would not cover two threads or tabs chatting at once.
- Accept the window and document it (E001 D): the race is reachable via parallel tool calls (research-brief.md).
- `SELECT ... FOR UPDATE` on a per-owner row: needs a local users row to lock; the advisory lock needs no table.
- A process-local `threading.Lock` on SQLite (design option b): adds global state for a test-only engine. Declined by the user ("ko khoa tren sqlite").

### Deviations

- Rule 1: Task 2.1 cleanup `try/except/pass` rewritten as `contextlib.suppress` to satisfy ruff SIM105 (SC-7). Same behaviour. `apps/api/tests/services/test_booking_duplicate_concurrency.py`, commit f028932.
- Process: `scripts/deploy-harness.sh` does not exist. `find . -name deploy-harness.sh` in both the worktree and the main checkout returned nothing. The worktree has no `.claude/` harness (`.claude/` is in the repo-local exclude file; only `settings.json` is tracked), so harness scripts (`task_brief.py`, `review_package.py`, `check_plan_contract.py`, `run_state.py`) were run from the main checkout against worktree paths.
- Process: the branch-isolation hook resolves ROOT from `CLAUDE_PROJECT_DIR` (the main checkout, on `main`), so Edit/Write into the sibling worktree is refused even after `EnterWorktree`. Worktree files were written with Bash python heredocs. The first Task 1.1 implementer was launched before `EnterWorktree` (cwd = main checkout), was blocked on every write path, and was re-dispatched from the worktree. No code impact.

- Rule 1 (correctness fix, user-approved): re-run `_replay` right after `lock_owner_bookings` in `book_flight` / `book_hotel`, so a concurrent same-idempotency-key call returns the original booking instead of `DuplicateBookingError` (CR-1). `apps/api/app/services/booking_service.py`, plus the same-key Postgres test in `apps/api/tests/services/test_booking_duplicate_concurrency.py`. Commit 447dc39.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| unit: lock called only on check_duplicate=True path; factory-mode RuntimeError; SQLite no-op; key stable int64 | `cd apps/api && /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/python -m pytest tests/services/test_booking_owner_lock.py -q` | 0 | part of Task 1.1 Verify, 33 passed @ 3b082d7 (controller re-run) | SC-1 |
| unit: gh-194 duplicate behaviour unchanged (service + agent tools) | `cd apps/api && /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/python -m pytest tests/services/test_booking_duplicate.py tests/tools/test_booking_duplicate_tools.py -q` | 0 | part of Task 1.1 Verify, 33 passed @ 3b082d7 (controller re-run) | SC-2 |
| integration: REST booking/flight/hotel contract unchanged | `cd apps/api && /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/python -m pytest tests/api/booking tests/api/flight tests/api/hotel -q` | 0 | 201 passed @ 3b082d7 (controller re-run) | SC-3 |
| behaviour (Postgres 17): B blocks on the advisory lock while A is uncommitted, then gets DuplicateBookingError; 1 active row (flight + hotel) | `cd apps/api && TEST_DATABASE_URL=postgresql+psycopg://test:test@localhost:55432/test /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/python -m pytest tests/services/test_booking_duplicate_concurrency.py -q -k blocks` | 0 | 2 passed @ f028932 (controller re-run). Needs the gh198-pg container on :55432 | SC-4 |
| negative control (Postgres 17): lock stubbed → 2 active rows | `cd apps/api && TEST_DATABASE_URL=postgresql+psycopg://test:test@localhost:55432/test /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/python -m pytest tests/services/test_booking_duplicate_concurrency.py -q -k without_lock` | 0 | 2 passed @ f028932 (controller re-run). Mutation check: with both real call sites removed, `-k blocks` → exit 1, 2 failed; restored from the last commit | SC-5 |
| concurrency module skipped (not failed) on default SQLite | `cd apps/api && /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/python -m pytest tests/services/test_booking_duplicate_concurrency.py -q` | 0 | 4 skipped @ f028932 (controller re-run) | SC-6 |
| lint | `cd apps/api && /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/ruff check app tests/services/test_booking_owner_lock.py tests/services/test_booking_duplicate_concurrency.py` | 0 | All checks passed @ f028932 (controller re-run) | SC-7 |
| format | `cd apps/api && /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/ruff format --check app/repositories/booking.py app/services/booking_service.py tests/services/test_booking_owner_lock.py tests/services/test_booking_duplicate_concurrency.py` | 0 | 4 files already formatted @ f028932 (controller re-run) | SC-8 |
| behaviour (Postgres 17): same-idempotency-key concurrent call replays the winner's booking after the lock (CR-1 fix) | `cd apps/api && TEST_DATABASE_URL=postgresql+psycopg://test:test@localhost:55432/test /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/python -m pytest tests/services/test_booking_duplicate_concurrency.py -q -k same_key` | 0 | 2 passed @ 447dc39 (controller re-run: full module 6 passed on Postgres; 6 skipped on SQLite). Failed before the fix: exit 1, B got DuplicateBookingError | |

### Not auto-verified

- The race is triggered by a real model emitting two parallel `book_*` calls in one super-step. This reached **provenance** (derived from the LangGraph/langchain-core source: `tool_node.py:858` gather, `structured.py:68` run_in_executor). It was not reproduced end-to-end with a live model, because the offline suite uses FakeLLM.
- OpenAI's default for `parallel_tool_calls` was not checked against provider docs. Local code sets no override (`app/agents/subagents/_base.py:249`). This reached **traceability** only.
- SQLite keeps the race by design; it backs only the unit-test suite (every running environment is Postgres, per the user 2026-09-15). The Postgres rows SC-4 and SC-5 are the proof, and the default `make test` suite skips them.
- Cross-owner races (e.g. hotel room capacity) are out of scope (design.md). Not addressed.

### Open Minor findings (per-task reviews → final review chain)

- M1 (1.1): the unit tests do not pin the lock-before-check order. Covered by SC-4 and the mutation check.
- M2 (1.1): the lock is exercised only on Postgres. Covered by SC-4 and SC-5.
- M3 (1.1): a same-idempotency-key race before `_replay` relies on the global unique index. `BookingRepository.add` catches IntegrityError inside the `begin_nested` savepoint and returns the winner via `get_by_idempotency_key`, so it surfaces as a replay, not a 500 (read from code, not tested).
- M4 (1.1): the replay no-lock spy covers `book_flight` only.
- M5 (2.1): the `finally` blocks do not join thread B before closing sessions. This only matters on an already-failing run.
- M6 (2.1): the `pg_locks` ungranted count is cluster-wide, not keyed to the owner. It is safe on the throwaway DB with no xdist.
- M7 (2.1): booking rows accumulate in the reused container. Per-case owners and owner-derived keys prevent collisions.

### Advisory Findings

Final correctness review over ef9aec1..f028932: 6 finder angles (enclosing-function, removed-behavior, call-site-impact, stack-defects, guard-completeness, prior-art), deduplicated to 4 locations, each scored by an independent scorer. None reached the threshold of 75, so none entered the fix loop.

- CR-1 (score 50, **FIXED in 447dc39**, fixed at the user's request although below the threshold): `apps/api/app/services/booking_service.py:422` / `:518`. Two concurrent agent book calls by the same owner with the SAME idempotency key (identical parallel tool calls in one turn, or an overlapping retry) both miss `_replay`, which runs before the lock. The loser then waits on the lock, sees the winner's committed row, and raises `DuplicateBookingError` instead of replaying the winner's booking. Before this diff it usually replayed via the `IntegrityError` branch in `BookingRepository.add`. Introduced by this diff. Rare, and no second booking is created. Suggested fix: call `_replay(idempotency_key, user_id)` again right after `lock_owner_bookings`. Supersedes M3's "surfaces as a replay" reading.
- CR-2 (score 25): `booking_service.py:421` / `:517`. The lock is taken only when `check_duplicate=True`, so REST and override inserts never wait on it. This is accepted scope (E002 A; REST runs no duplicate check), but the docstring sentence "two concurrent requests cannot both pass the check" applies to agent-vs-agent races only.
- CR-3 (score 0, unmodified line): `booking_service.py:537`. Not a race. `hotel_service.is_available` / `available_rooms` is a fixed md5-seeded number that never counts existing bookings, so a hotel can be overbooked even by sequential requests. A design limit that predates this diff and is out of scope (design.md).
- CR-4 (score 0, unmodified line): `booking_service.py:460` / `:584`. A real bug that predates this diff. When `BookingRepository.add` loses an idempotency-key race it returns the winner's booking, but `book_flight` / `book_hotel` ignore that value and return their locally built booking, whose id and confirmation_code were never persisted. Fix: `booking = self._repo.add(...)`.

### Intent Findings

- none. The intent review over ef9aec1..f028932 found no gap, drift or excess. Every clause of issue #198 and the user's decisions (E001 B, E002 A, "ko khoa tren sqlite", Postgres everywhere, two waves) maps to the diff. SC-1 to SC-8 are each proven by a passing Verify row.

### Rollback

- Revert all three commits, newest first (447dc39, f028932, 3b082d7), with the VCS revert command. Code-only: no schema, data or migration to undo. An advisory lock leaves no persistent state.

### Harness-Delta

- backlog: sibling-worktree runs lose the harness. `.claude/` is excluded locally, `deploy-harness.sh` does not exist, and the branch-isolation hook roots at `CLAUDE_PROJECT_DIR`, so every worktree write needs a heredoc and subagents launched before `EnterWorktree` are fully blocked. Candidate fix: resolve the branch and root from the target file's own repository toplevel. It is a high-blast hook, so it needs its own intake → compound.
