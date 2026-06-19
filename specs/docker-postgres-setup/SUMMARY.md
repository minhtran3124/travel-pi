# SUMMARY — docker-postgres-setup

Lane: high-risk
Confidence: high (escalation E1 resolved 2026-06-19 — scope pinned)
Reason: Hard gate hit (data migration: SQLite → Postgres). 4 risk flags fired (data model, external systems, existing behavior, weak proof).
Flags: data-model, external-systems, existing-behavior, weak-proof
Affects: DB persistence tier (`app/crud/*` raw sqlite3 — booking/flight/trip/saved_place/_migrations), `app/core/lifespan.py`, `app/core/config.py` (`database_path`), `tests/conftest.py` (per-session temp SQLite). New infra: Dockerfile, docker-compose, Makefile, README.
Input-type: Maintenance (ops/infra) + Change request (DB backend)
Route: high-risk full chain — /brainstorming (covered by escalation Q&A) → /xia2 ✅ (research-brief.md) → /writing-plans ✅ (PLAN.md, 19 tasks / 6 chunks, plan-review pass: 11 findings folded in incl. trip_service IntegrityError catch + 617→624 test baseline) → /using-git-worktrees (next) → /subagent-driven-development
Escalate: yes (hard gate + low confidence — Postgres migration scope is ambiguous)

### Intent

User request, verbatim:

- define docker image and docker-compose to run project.
- define db in docker-compose with postgres
- update db config with postgres
- write scripts and make file to start up project
- update readme, guide
- create docker-compose to run unittest with isolate db

### Rationale

The Docker/compose/Makefile/README parts are low-risk additive infra. The
risk is concentrated in **"update db config with postgres"**: the data tier is
raw `sqlite3` (~81 SQLite-specific call sites across 6 files), `database_path`
is a file path (not a URL), and 594 tests run against a per-session temp SQLite
file (`tests/conftest.py`). Moving persistence to Postgres is a data-store
migration (hard gate) and rewrites the crud SQL dialect, conflicting with the
CLAUDE.md "minimal, no ORM" constraint unless scope is pinned.

### Alternatives (the fork that forces escalation)

1. **Full replacement** — SQLite removed; all crud + tests on Postgres.
2. **Dual-backend** — backend selected by config (SQLite default for local/tests,
   Postgres for Docker). Keeps the fast test path, doubles the SQL-dialect surface.
3. **Runtime Postgres, tests stay SQLite** — Postgres only behind Docker; the
   pytest suite keeps temp SQLite; a separate compose runs tests against an
   isolated Postgres for integration confidence.

Two competent engineers would build materially different things → confidence low.

### Resolution (2026-06-19)

User selected: **runtime Postgres + tests stay SQLite** (backend config-selected),
**SQLAlchemy ORM** (overrides CLAUDE.md "no ORM"), **compose-first Makefile**
(Docker + local targets). Confidence now high; lane stays high-risk (the
data-store migration hard gate is independent of confidence). See ESCALATIONS.md
E1. CLAUDE.md "no ORM" rule must be updated and the decision recorded via
`/compound`.
