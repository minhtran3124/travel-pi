# gh-198 — Atomic duplicate-intent check (design)

Status: approved by user 2026-09-15 ("ok, ko khoa tren sqlite")
Decisions: ESCALATIONS E001 B (per-owner lock), E002 A (agent path only); SQLite = no lock.

## Purpose

Two concurrent agent `book_flight` / `book_hotel` calls by the same owner, for the same
flight + passenger count or the same hotel + dates, with different idempotency keys, can both
pass the gh-194 duplicate check and both insert. The goal is to make check + insert atomic per
owner on Postgres, so exactly one booking wins and the other gets `DuplicateBookingError`.

## Constraints

- No schema or migration change. No REST behaviour change (`check_duplicate=False` takes no lock).
- Follow the existing unit-of-work: agent tools run the service inside `session_scope()`
  (`app/tools/_base.py`), one live `Session` that commits or rolls back at tool exit. Live-session
  repos only `flush` (`app/repositories/base.py`), so the check and the insert already share one
  transaction.
- SQLite gets **no lock**. Every running environment (dev and local) is Docker + Postgres (user,
  2026-09-15), so SQLite is only the default DB of the `make test` unit suite. The race stays on
  SQLite and the docstring says so; no running environment is exposed to it.

## Architecture

- New `BookingRepository.lock_owner_bookings(user_id: str) -> None`:
  - Postgres: `SELECT pg_advisory_xact_lock(:key)`, where `key` is a stable signed int64 derived
    from `"booking:" + user_id` via `hashlib.blake2b(digest_size=8)`, not Python `hash()`, which
    is salted per process. The digest is converted with
    `int.from_bytes(digest, "big", signed=True)`, which always fits Postgres `bigint`. The lock is
    released automatically on commit or rollback. It is a transaction-level lock, so savepoint
    release or rollback (the `begin_nested` in `add`) never drops it.
  - Any other dialect (SQLite): no-op. Dialect check follows the precedent in
    `app/repositories/rate_limit.py` (`s.get_bind().dialect.name`).
  - It is only meaningful with a live session: in factory mode the transaction would end at once.
    So it raises `RuntimeError` when the repo is in factory mode (`self._s is None`), matching the
    explicit-contract guard in `app/core/rate_limit.py`. It is checked before the dialect branch, so
    SQLite tests catch misuse too. Every `check_duplicate=True` caller today (the two agent tools)
    runs in `session_scope()`'s live session.
- `BookingService.book_flight` / `book_hotel`: call `self._repo.lock_owner_bookings(user_id)` at
  the top of the `if check_duplicate:` block, after idempotency replay and flight/hotel
  resolution, and before `list_active_by_reference`.

## Data flow under a race (Postgres, READ COMMITTED, the engine default)

A: lock → check (none) → insert → tool exit commit → lock released.
B: lock waits → acquires after A's commit → check sees A's row → `DuplicateBookingError` →
existing `tool_error` path → model asks the traveller. B's transaction rolls back and releases.

One lock per transaction, keyed per owner, so there is no lock-ordering deadlock. Unrelated
owners never contend. Key-hash collisions between owners only cause a brief extra wait, never a
wrong answer.

## Error behaviour

A failure while acquiring the lock propagates. `session_scope` rolls back and the tool returns
`tool_error`. There is no `lock_timeout`: tool transactions are short, and the wait is bounded
by the other call's commit (YAGNI).

## Tests

- Postgres-only (skip on SQLite; run under `make test-docker`), deterministic rather than a
  barrier race, which could pass without the lock if A commits before B checks:
  1. Session A books (same owner, `check_duplicate=True`) and is left uncommitted, holding the lock.
  2. Start B in a thread (same owner + flight + passengers, different idempotency key).
  3. Assert B is blocked: after a short `join(timeout)` it is still alive, and `pg_locks` shows a
     waiting `advisory` lock.
  4. Commit A, then assert B raises `DuplicateBookingError` and exactly one active booking exists.

  Repeat for hotel + dates. Negative control: with `lock_owner_bookings` patched to a no-op, the
  same scenario produces two bookings. This proves the test depends on the lock.
- SQLite suite:
  - `lock_owner_bookings` is invoked only when `check_duplicate=True` (spy);
  - the helper is a no-op on SQLite;
  - existing REST booking and agent tool tests stay green.

## Out of scope

REST duplicate checking (E002 A) · schema unique index (E001 A) · agent tool serialization
(E001 C) · SQLite locking · `lock_timeout` · cross-owner races such as hotel room capacity (two
different owners both passing an availability check). The lock is per owner and does not
serialize different owners.

## Rollback

`git revert <sha>`: code-only, no data or schema to undo.
