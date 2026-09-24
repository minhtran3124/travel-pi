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

Intake only — not started.

### Rationale

Pure layering refactor with existing test coverage; one clear interpretation, so normal lane with high confidence.

### Alternatives considered

- tiny lane: rejected — more than one file and new public repository methods.

### Deviations

- none

### Verify

| Check | Command | Exit | Notes |
|---|---|---|---|
| Intake record | `python .claude/scripts/verify_summary.py --lane gh-226-research-orm-repositories` | 0 | intake handoff |
