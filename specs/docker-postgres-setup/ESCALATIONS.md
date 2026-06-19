# ESCALATIONS — docker-postgres-setup

Default: deny-on-no-response (work does not proceed past the DB-migration step
until the scope question below is answered).

## E1 — Postgres migration scope (open)

**Trigger:** Hard gate (data-store migration SQLite → Postgres) + low confidence.

**Question:** How far should "update db config with postgres" go? The data tier is
raw `sqlite3` (~81 dialect-specific call sites; 594 tests on temp SQLite).

**Options presented:** full replacement · dual-backend (configurable) · runtime
Postgres + tests stay SQLite.

**Status:** RESOLVED (2026-06-19).

**Decision:**
- **Scope:** Runtime Postgres behind Docker; backend selected by config (SQLite
  stays default for local/CI). Normal `pytest` keeps temp SQLite; a separate
  test-compose runs the suite against an isolated Postgres for integration.
- **Driver:** **SQLAlchemy ORM** — *user override of the CLAUDE.md "no ORM"
  constraint.* Crud tier moves from raw `sqlite3` to ORM models; engine is a
  connection URL, giving clean dual-engine (SQLite + Postgres) support.
- **Tooling:** Compose-first Makefile with both Docker and local-dev targets.

**Deviation to carry forward:** CLAUDE.md "Keep it minimal — no ORM" must be
updated; record the architecture change via `/compound`.
