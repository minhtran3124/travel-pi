---
slug: gh-226-research-orm-repositories
status: shipped
owner: minhtran3124
created: 2026-09-24
---

# gh-226-research-orm-repositories — move research ORM queries behind repositories/

## 1. Motivation

Issue #226 (owner decision D6 in the PR #221 review). `techstacks/architecture.md` and `AGENTS.md`
keep SQLAlchemy ORM access in `app/repositories/`. The research module added in #221 runs seven raw
`select()` / `update()` statements outside it:

| File | Call site | Query |
|---|---|---|
| `app/research/service.py` | `latest()` | newest research run for a trip |
| `app/research/service.py` | `sweep_stale()` | flip stale `running` research rows to `interrupted` |
| `app/research/service.py` | `_running_for()` | the trip's `running` research run, on the **locked** session |
| `app/research/validate.py` | `_unknown_ids()` | which place / flight-offer / hotel ids exist (3 queries) |
| `app/routers/research.py` | `_thread_turn()` | count of research runs for a trip, optionally up to a timestamp |

`ResearchService._get_run()` uses `s.get(AgentRun, run_id)`; it moves too.

## 2. Non-goals

- No behaviour change: same rows returned, same ordering, same commit points.
- No change to routes, response shapes, schemas, migrations, or the research agent.
- No rename or restructure of existing repository methods.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|---|---|---|---|
| SC-1 | No raw `select(` / `update(` statement remains in the research module or its router | `grep -rnF -e "select(" -e "update(" apps/api/app/research apps/api/app/routers/research.py` | exit 1 — no match |
| SC-2 | The new `AgentRunRepository` methods return the same rows the inline queries did | `cd apps/api && ../../.venv/bin/python -m pytest tests/repositories/test_agent_run_repo.py -q` | exit 0 |
| SC-3 | `known_ids` on the place, hotel and flight-index repositories returns exactly the ids that exist | `cd apps/api && ../../.venv/bin/python -m pytest tests/repositories/test_reference_repos.py -q` | exit 0 |
| SC-4 | The research service, runner, tools and validator tests pass with no test edited | `cd apps/api && ../../.venv/bin/python -m pytest tests/research -q` | exit 0 |
| SC-5 | The research routes, including `thread_turn`, pass with no test edited | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/research -q` | exit 0 |
| SC-6 | The per-trip advisory lock still serializes concurrent starts on Postgres | `cd apps/api && TEST_DATABASE_URL=postgresql+psycopg://test:test@localhost:55432/test ../../.venv/bin/python -m pytest tests/research/test_service_concurrency.py -q` | exit 0 — 0 skipped (needs the throwaway `postgres:17-alpine` on :55432 from the test module docstring) |
| SC-7 | Lint is clean on the touched backend code | `cd apps/api && ../../.venv/bin/ruff check app tests/repositories` | exit 0 |

## Global Constraints

- **Transaction scope is load-bearing.** `ResearchService.start` reads the running row inside the
  session that holds `advisory_xact_lock`. The replacement must be `AgentRunRepository(s).running_for(...)`
  with that same `s` (the `Repo` base yields a caller-owned session unchanged). Opening a new session
  there breaks the per-trip lock — a Rule 4 change; stop and report instead.
- **Session sources stay as they are.** `service.py` keeps `self._sf`; `validate.py` keeps
  `app.tools._base.session_scope()` and passes the open session to the repositories; the router keeps
  its isolated factory.
- **Semantics preserved exactly:** `latest` orders by `created_at desc` and returns the first row;
  `sweep_stale` filters `kind`, `status == "running"`, `started_at < cutoff`, sets `interrupted`,
  commits, and returns `rowcount or 0`; the turn count is `created_at <= upto` when `upto` is given.
- Existing tests under `tests/research` and `tests/api/research` are not edited. New tests go only in
  `tests/repositories/`.
- Repository methods take `kind` as a parameter; `RESEARCH_KIND` stays defined in the research module.
- Style: match `app/repositories/*` (docstring one-liners, `with self._session() as s`,
  `self._commit(s)` for writes). Multi-parameter signatures: one parameter per line with a trailing
  comma. Minimal comments.

## 4. Tasks

### Task 1.1 — AgentRunRepository query methods (wave 1)

- **Files:** apps/api/app/repositories/agent_run.py, apps/api/tests/repositories/test_agent_run_repo.py
- **Action:** Test-first. Add to `AgentRunRepository`: `get(run_id)` returning the row or `None`;
  `latest_for_trip(trip_id, kind)`, the newest row by `created_at`; `running_for(trip_id, kind)`, the
  first `running` row; `count_for_trip(trip_id, kind, *, upto=None)`, an int, counting `created_at <= upto`
  when given; `sweep_running_before(kind, cutoff)`, which sets `running` rows with
  `started_at < cutoff` to `interrupted`, commits through `_commit` and returns the row count. Each
  read uses `with self._session() as s`. Add tests for each method, including: another kind or trip is
  excluded, `upto` bounds the count, the sweep leaves rows at or after the cutoff alone, and
  `running_for` sees an uncommitted row when constructed with a live `Session`.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/repositories/test_agent_run_repo.py -q`
- **Done:** the command exits 0 and the file has at least one test per new method.
- **Criteria:** SC-2, SC-7
- **Interfaces:** Consumes the AgentRun model and the Repo base (existing). Produces `app/repositories/agent_run.py` (get, latest_for_trip, running_for, count_for_trip, sweep_running_before).

### Task 1.2 — known_ids on reference repositories (wave 1)

- **Files:** apps/api/app/repositories/place_ref.py, apps/api/app/repositories/hotel_ref.py, apps/api/app/repositories/flight.py, apps/api/tests/repositories/test_reference_repos.py
- **Action:** Test-first. Add `known_ids(ids: list[str]) -> set[str]` to `PlaceRepository`
  (`Place.id`), `HotelRepository` (`Hotel.id`) and `FlightIndexRepository` (`FlightIndex.flight_id`).
  Each returns the subset of `ids` present in the table, and returns `set()` without querying when
  `ids` is empty. Add tests: mixed known and unknown ids, empty input, and all ids unknown.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/repositories/test_reference_repos.py -q`
- **Done:** the command exits 0 and each of the three repositories has an empty-input test and a mixed-input test.
- **Criteria:** SC-3, SC-7
- **Interfaces:** Consumes the Place, Hotel and FlightIndex models (existing). Produces `app/repositories/place_ref.py`, `app/repositories/hotel_ref.py`, `app/repositories/flight.py` (known_ids).

### Task 2.1 — ResearchService and router use AgentRunRepository (wave 2)

- **Files:** apps/api/app/research/service.py, apps/api/app/routers/research.py
- **Action:** Replace the raw queries with repository calls:
  - `latest` → `AgentRunRepository(self._sf).latest_for_trip(trip_id, RESEARCH_KIND)`.
  - `sweep_stale` → `AgentRunRepository(self._sf).sweep_running_before(RESEARCH_KIND, cutoff)`.
  - `_running_for(session, trip_id)` → `AgentRunRepository(session).running_for(trip_id, RESEARCH_KIND)`, on the locked session.
  - `_get_run` → `AgentRunRepository(self._sf).get(run_id)`.
  - Router `_thread_turn` → `AgentRunRepository(factory).count_for_trip(trip_id, RESEARCH_KIND, upto=upto)`.

  Remove the `select`, `update` and `func` imports that become unused. Keep the `AgentRun` import
  where it is used as a type annotation.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/research tests/api/research -q`
- **Done:** the command exits 0 with no test file edited, and `grep -nF -e "select(" -e "update(" -e "s.get(AgentRun" apps/api/app/research/service.py apps/api/app/routers/research.py` exits 1.
- **Criteria:** SC-1, SC-4, SC-5, SC-6, SC-7
- **Interfaces:** Consumes `app/repositories/agent_run.py`. Produces `app/research/service.py`, `app/routers/research.py` (public signatures unchanged).

### Task 2.2 — validate_proposal uses known_ids (wave 2)

- **Files:** apps/api/app/research/validate.py
- **Action:** In `_unknown_ids`, keep `with session_scope() as s:` and replace the three queries with
  `PlaceRepository(s).known_ids(place_ids)`, `FlightIndexRepository(s).known_ids(offer_ids)` and
  `HotelRepository(s).known_ids(hotel_ids)`. Keep the order of the returned unknown ids
  (places, offers, hotels). Remove the `select` and model imports that become unused.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/research -q`
- **Done:** the command exits 0 with no test file edited, and `grep -nF "select(" apps/api/app/research/validate.py` exits 1.
- **Criteria:** SC-1, SC-4, SC-7
- **Interfaces:** Consumes `app/repositories/place_ref.py`, `app/repositories/hotel_ref.py`, `app/repositories/flight.py`. Produces `app/research/validate.py` (make_validate_proposal signature unchanged).

## 5. Risks

- **Moving `_running_for` off the locked session silently breaks the per-trip lock.** SQLite cannot
  detect this because the lock is a no-op there. SC-6 on Postgres is the only proof. If Docker is
  unavailable, record SC-6 as not run in SUMMARY and do not claim the lock is verified.
- **Detached ORM objects.** Factory-mode repository reads return rows after their session closes. This
  is the same as the current inline `with self._sf() as s: return ...`, so it is not a new risk.

## 6. Status Log

- 2026-09-24 — plan written; worktree `../travel-pi-gh-226-research-orm-repositories` on
  `refactor/gh-226-research-orm-repositories` from `2919b566`; baseline 194 passed, 2 skipped
  (`tests/research tests/api/research tests/repositories`).
- 2026-09-24 — plan review: Approved (1 advisory applied: Task 2.1 Done also greps `s.get(AgentRun`).
- 2026-09-24 — tasks 1.1, 1.2, 2.1, 2.2 complete; commits 4ca86233, 259f6e52, 1c3fb323, 14b2ae09, 209b0084; correctness 0 findings, intent no material mismatch.
