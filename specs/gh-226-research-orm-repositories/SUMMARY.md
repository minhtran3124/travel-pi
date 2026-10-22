# gh-226-research-orm-repositories — Summary

Lane: normal
Confidence: high
Reason: behaviour-preserving refactor across several files (research service, validator, router, repositories); no manifest hard gate — no migration, no route/response change, no auth.
Flags: existing-behavior, multi-file
Affects: apps/api research module (app/research/service.py, app/research/validate.py, app/routers/research.py) and app/repositories (agent_run, place_ref, hotel_ref, flight)
Input-type: maintenance
Route: using-git-worktrees -> writing-plans (PLAN.md, >2 files) -> subagent-driven-development
Escalate: no

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> /feature-intake for https://github.com/minhtran3124/travel-pi/issues/226

Issue #226 "Move research ORM queries behind repositories/" (owner decision D6 during the PR #221
review, 2026-09-23): route every direct `select()`/`update()` in `app/research/service.py`,
`app/research/validate.py` and `app/routers/research.py` through repository methods; pure refactor, no
behaviour change; acceptance = no `select(`/`update(` left in those files and the research suites pass
unchanged.

### Intake notes

- Constraint (Rule 4 guard, not a gate): `ResearchService.start` runs `_running_for` inside the session
  that holds `advisory_xact_lock`. The repository method must take that open session, not open its own —
  moving the query to a new session would change transaction scope and break the per-trip lock.
- Repository names differ from the issue text: the place/hotel/flight repositories live in
  `place_ref.py`, `hotel_ref.py`, `flight.py`; the plan uses the existing classes.
- `validate.py` uses `app.tools._base.session_scope`; keep that session source.
- Proof: existing research suites (`tests/research`, `tests/api/research`) must pass unchanged — no test
  edits except new repository-method tests.

## What changed

Research no longer queries the ORM directly. `AgentRunRepository` gained `get`, `latest_for_trip`,
`running_for`, `count_for_trip` and `sweep_running_before`; `PlaceRepository`, `HotelRepository` and
`FlightIndexRepository` gained `known_ids`. `ResearchService` (`latest`, `sweep_stale`, `_running_for`,
`_get_run`), the router's `_thread_turn` and `validate_proposal`'s `_unknown_ids` now call them. No
behaviour change; `_running_for` still reads on the session that holds the per-trip advisory lock.

### Rationale

Pure layering refactor with existing test coverage; one clear interpretation, so normal lane with high confidence.

### Alternatives considered

- tiny lane: rejected — more than one file and new public repository methods.

### Deviations

- none

Full backend suite in the worktree (no `.env`), cited in prose per `rules/plan-format.md`: `cd apps/api && ../../.venv/bin/python -m pytest -q` → 3055 passed, 9 skipped, 0 failed.

### Lock-scope evidence (mutation check)

Mutating `_running_for` to open a fresh session (`AgentRunRepository(self._sf)`) still passes SC-6: the
advisory lock serializes both starts, and a fresh session opened after the first commit sees the
committed row. The mutant is caught instead by the SQLite suite — `tests/research/test_resume.py::
test_start_after_a_crash_resumes_the_checkpointed_turn` and `tests/research/test_service.py::
test_start_after_a_cancelled_run_resumes_without_spending_the_cap` fail, because `start()` then sets
`interrupted` on a detached row that is never written. So the locked-session constraint is guarded by
SC-4, and SC-6 guards serialization. Code restored after the check (`git checkout`).

### Review findings (Minor, recorded)

- Task 1.2: `known_ids` tests combine the empty, mixed and all-unknown cases in one function per repository; the empty-input test does not prove that no query runs; `init_db()` in the flight test is redundant.
- Task 1.1: no test for `sweep_running_before` in live-session mode or for a sweep with no match; the status strings `"running"` / `"interrupted"` are duplicated in the repository and in `service.py` constants.
- Correctness review (6 angles): 0 candidates.

### Intent Findings

Intent review verdict: no material mismatch; the acceptance clauses of #226 are met (the issue's grep exits 1; research suites pass with no existing test edited).

- drift (equivalent): the issue proposed `latest` and `sweep_stale`; they shipped as `latest_for_trip` and `sweep_running_before`, with the same signatures and semantics. `ResearchService.sweep_stale` still exists and delegates.
- drift (equivalent): `count_for_trip` takes a keyword-only `upto`. It is needed to keep `_thread_turn`'s `created_at <= upto` bound, so behaviour is unchanged.
- drift (equivalent): `get(run_id)` is added for the `_get_run` call site the issue lists; the issue's proposed-method list did not name it.
- gap (out of scope, deferred): `ResearchService.start` still sets `running.status = interrupted` on the ORM row and commits inside the advisory-lock transaction (`service.py` ~164/175). The issue's acceptance keys on `select(` / `update(` only. Moving this write touches the lock transaction (Rule 4), so it is left for the owner. A possible follow-up is `AgentRunRepository(session).mark_interrupted(run)` on the caller's session.

### Verify

| Check | Command | Exit | Notes | Criterion |
|---|---|---|---|---|
| Intake record | `python .claude/scripts/verify_summary.py --lane gh-226-research-orm-repositories` | 0 | intake handoff | |
| No raw query left | `grep -rnF -e "select(" -e "update(" apps/api/app/research apps/api/app/routers/research.py` | 1 | no match | SC-1 |
| AgentRun repo methods | `cd apps/api && ../../.venv/bin/python -m pytest tests/repositories/test_agent_run_repo.py -q` | 0 | 14 passed | SC-2 |
| known_ids | `cd apps/api && ../../.venv/bin/python -m pytest tests/repositories/test_reference_repos.py -q` | 0 | 35 passed | SC-3 |
| Research suite, no test edited | `cd apps/api && ../../.venv/bin/python -m pytest tests/research -q` | 0 | 114 passed, 2 skipped (Postgres-only) | SC-4 |
| Research routes, no test edited | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/research -q` | 0 | 26 passed | SC-5 |
| Advisory lock on Postgres | `cd apps/api && TEST_DATABASE_URL=postgresql+psycopg://test:test@localhost:55432/test ../../.venv/bin/python -m pytest tests/research/test_service_concurrency.py -q` | 0 | 2 passed, 0 skipped on throwaway postgres:17-alpine :55432 | SC-6 |
| Lint | `cd apps/api && ../../.venv/bin/ruff check app tests/repositories` | 0 | All checks passed | SC-7 |
