# gh-198 — Research Brief

Depth: **Deep** (from intake lane `high-risk`; not re-scored). No upgrade needed; no waiver.
External surface: yes. The fix relies on Postgres advisory-lock semantics, which are version-specific
(Postgres 17).

## Bottom Line

| Field | Value |
|---|---|
| **Recommendation** | use built-in: Postgres `pg_advisory_xact_lock(bigint)` inside the existing tool unit-of-work |
| **Why this is the lightest credible path** | The check and the insert already share one transaction (`session_scope` plus live-session repos that only flush). One lock statement makes them atomic, with no schema, dependency or contract change. |
| **Confidence** | 85% |
| **Next step** | `writing-plans`: 1 wave. Repo helper + service call sites + SQLite tests, then a deterministic Postgres concurrency test under `make test-docker`. |

## Repo Snapshot

| Field | Detected |
|---|---|
| Repo type | monorepo; FastAPI API (`apps/api`) + Next.js web |
| Primary language + runtime | Python 3.14 local venv (Docker py3.12, see memory `docker-py312-vs-local-py314`) |
| Frameworks / platforms | FastAPI, SQLAlchemy 2.0.51 (sync engine), LangGraph 1.2.6, langgraph-prebuilt 1.1.0, langchain-core 1.4.8 |
| Relevant packages | psycopg 3.3.4 (+ binary); Postgres 17 (`pgvector/pgvector:pg17` dev, `postgres:17-alpine` test) |
| Detectable versions | `.venv` metadata + `apps/api/docker-compose.yml`, `docker-compose.test.yml` |
| Important constraints | SQLite locally / Postgres in Docker, chosen by `DATABASE_URL`; tests switch via `TEST_DATABASE_URL` (`tests/conftest.py:43`); stage and commit separately |

## Feature Understanding and Assumptions

- **Requested feature:** make the gh-194 duplicate-intent check atomic (issue #198). Decisions: E001 B, E002 A, SQLite no lock (design.md).
- **What success appears to mean:** two concurrent agent `book_*` calls for the same owner and intent on Postgres produce exactly one booking plus one `DuplicateBookingError`. REST behaviour is unchanged.
- **Assumptions from the request:** every running environment (dev and local) runs Docker +
  Postgres (confirmed by the user, 2026-09-15); SQLite is only the unit-test suite's default DB.
- **Assumptions still needing confirmation:** none that would change the recommendation.

## Evidence Ledger

| Label | Evidence |
|---|---|
| `Local` | Tools call `BookingService(s)` inside `session_scope()`, which commits or rolls back at exit (`app/tools/_base.py:104-116`; `flight_tools.py:472-491`, `hotel_tools.py:580-599`). |
| `Local` | Live-session repos `flush` and never commit (`app/repositories/base.py` `_commit`), so check and insert share the tool's transaction. |
| `Local` | `add` wraps the insert in `begin_nested()` (savepoint) and maps `IntegrityError` on the idempotency key (`app/repositories/booking.py:250-262`). |
| `Local` | The engine sets no `isolation_level` (`app/db/engine.py:33-38`), so Postgres runs at its READ COMMITTED default. |
| `Local` | Production drives the graph with `ainvoke`/`astream` (`app/routers/agent.py:398,406`; `app/streaming/mapper.py`). |
| `Local` | ToolNode async path runs every tool call in the batch through `asyncio.gather` (`langgraph/prebuilt/tool_node.py:858`). Sync tools run on the async path via `run_in_executor` (`langchain_core/tools/structured.py:68`, `base.py:900`), i.e. on separate threads. `book_flight` / `book_hotel` are sync `def` tools (`flight_tools.py:367`, `hotel_tools.py:486`). |
| `Local` | `bind_tools(active_tools)` is called with no `parallel_tool_calls` override (`app/agents/subagents/_base.py:249`). Grep over `app/` found only `app/clients/llm.py:224` and that line. |
| `Local` | Dialect-branch precedent: `app/repositories/rate_limit.py:67`. Explicit-contract `RuntimeError` precedent: `app/core/rate_limit.py` (`session.in_transaction()` guard). |
| `Docs` | PG17 `pg_advisory_xact_lock(key bigint) → void`: "Obtains an exclusive transaction-level advisory lock, waiting if necessary." Released automatically at transaction end, with no explicit unlock. Single 64-bit key space. |
| `Docs` | PG17 caveat: an advisory-lock call combined with `LIMIT` may lock unexpected rows. Not applicable here (a scalar `SELECT pg_advisory_xact_lock(:k)`). |
| `Upstream` | Community pattern: hash the entity id to a signed 8-byte key and take `pg_advisory_xact_lock` before check-then-insert (FireHydrant, blasphemess.com SQLAlchemy post, leontrolski). Matches the design. |
| `Inference` | Two `book_*` calls in one super-step run concurrently on two threads, each with its own session and connection, so the race in #198 is reachable in production (not reproduced live). |

## Local Findings

- **Relevant files:** `app/services/booking_service.py` (`book_flight` ~L353, `book_hotel` ~L462, `if check_duplicate:` blocks); `app/repositories/booking.py`; `app/repositories/base.py`; `app/tools/_base.py`; `tests/services/test_booking_duplicate.py`; `tests/tools/test_booking_duplicate_tools.py`; `tests/conftest.py`.
- **Extension points:** a new `BookingRepository` method; one call per service method.
- **Conventions worth preserving:**
  - repos own SQL and services own rules;
  - dialect branch via `s.get_bind().dialect.name`;
  - Sphinx-style docstrings with `:param:`;
  - raise explicit `RuntimeError` for a misuse contract.
- **Reusable:** `session_scope` UoW, the `DuplicateBookingError` → `tool_error` path, and the gh-194 duplicate tests.
- **Missing locally:**
  - a Postgres-only test marker: none found in `tests/`, `tests/conftest.py`, `pyproject.toml` or `pytest.ini`, so the new test uses `pytest.mark.skipif` on dialect;
  - any existing advisory-lock usage: grep for `advisory` over `app/` hit only unrelated files.

## Upstream Findings

- **Sources inspected:** FireHydrant blog (Rails advisory locks), blasphemess.com "SQLAlchemy, Race Conditions, And PostgreSQL Advisory Locks", leontrolski "Postgres advisory locks for python developers".
- **Pattern:** a hashed entity key plus a transaction-level advisory lock around the critical section.
- **Match:** high. The only local nuance is the dual-mode `Repo`, handled by the factory-mode guard.
- **Gaps:** the upstream posts use `pg_try_*` (fail fast) in some cases. We want the blocking variant so the loser sees the winner's row and gets the friendly duplicate error.

## Docs Findings

- **Official sources checked:** postgresql.org/docs/17 explicit-locking (§13.3.5) and functions-admin (Table 9.106).
- **Version-matched:** yes (PG 17 = dev and test images).
- **Built-in capability:** `pg_advisory_xact_lock(bigint)`; no extension needed.
- **Caveats:** the lock is held to transaction end, so keep the transaction short (tool scope already is). There is no unlock call. Avoid combining it with `LIMIT`. SQLite has no equivalent, and a no-op is accepted per design.

## Recommendation

- **Primary:** use the built-in `pg_advisory_xact_lock` via a new `BookingRepository.lock_owner_bookings(user_id)`, called at the top of each `if check_duplicate:` block.
- **Why lightest:** one statement, reusing the existing UoW; no migration, no new dependency, no contract change.
- **Why the next-best lost:**
  - A partial unique index needs new columns, a backfill and a dedupe, and it changes REST (E001 A rejected).
  - Agent-level serialization leaves cross-thread and two-tab chat races open (E001 C).
  - `pg_try_advisory_xact_lock` would turn the loser into an opaque retry error instead of the duplicate warning.
- **What would flip it:** production on a DB other than Postgres, or tools moving to a factory-mode (per-statement commit) session.

## Risks, Unknowns, and Follow-Up Questions

- **Technical risks:**
  - A future caller passing `check_duplicate=True` outside a live session. Mitigated by the factory-mode `RuntimeError`.
  - The lock holder waiting on something slow inside the same transaction. Low risk: the tool transaction is only reads plus one insert.
  - The concurrency test must hold the transaction open deterministically, or it can pass without the lock. The design's negative control covers this.
- **Evidence gaps:**
  - The race was not reproduced end-to-end through a real model emitting two parallel `book_*` calls.
  - OpenAI's `parallel_tool_calls` default was not verified against the provider docs. The local code sets no override.
- **Version uncertainties:** none. PG17 matches both compose images.
- **Follow-up questions for the user:** none.

## Source Pack

- **Local files read:** apps/api/app/tools/_base.py; app/repositories/base.py; app/repositories/booking.py; app/repositories/rate_limit.py; app/core/rate_limit.py; app/core/lifespan.py; app/db/engine.py; app/services/booking_service.py; app/tools/flight_tools.py; app/tools/hotel_tools.py; app/agents/subagents/_base.py (grep); app/db/models/booking.py (grep); tests/conftest.py (grep); .venv langgraph/prebuilt/tool_node.py; .venv langchain_core/tools/{structured,base}.py; docs/solutions/agent/sync-node-breaks-async-only-tools.md; apps/api/docker-compose.yml; docker-compose.test.yml
- **Upstream repositories or pages checked:** https://firehydrant.com/blog/using-advisory-locks-to-avoid-race-conditions-in-rails/ ; https://blog.blasphemess.com/sqlalchemy-race-conditions-and-postgresql-advisory-locks/ ; https://leontrolski.github.io/postgres-advisory-locks.html (search-result summaries only)
- **Official docs domains or pages checked:** https://www.postgresql.org/docs/17/explicit-locking.html ; https://www.postgresql.org/docs/17/functions-admin.html

## Evidence Boundary

> Confirmed from artifacts:
> - tool UoW shares one transaction for check + insert;
> - READ COMMITTED default;
> - ToolNode gathers calls, and sync tools run in the executor;
> - no `parallel_tool_calls` override;
> - PG17 advisory xact lock semantics;
> - Postgres 17 in both compose files.
>
> Inferred from patterns:
> - the race is reachable in production via parallel `book_*` calls;
> - the savepoint does not release the xact lock (docs say release happens at transaction end; savepoint behaviour follows from that and was not separately tested).
>
> Not checked:
> - live reproduction with a real model;
> - OpenAI provider default for parallel tool calls;
> - upstream posts beyond search summaries.
