# migration-helper — Escalations

## Hard gate: data-loss/migration — confirm lane

- **Date:** 2026-06-18
- **Gate:** `risk-corroboration.sh` flags any added `ALTER TABLE` line as `data-loss/migration`
  (a hard gate). A0 relocates existing `ALTER TABLE ADD COLUMN` statements into a shared helper, so
  the diff WILL contain `ALTER TABLE` → the gate trips and blocks a commit below `high-risk` unless
  loosened with `RISK_WARN_CATEGORIES="data-loss/migration"`.
- **Substance:** No new or destructive migration. No `DROP`/`DELETE`/data loss. The same three
  additive, nullable, idempotent column migrations run — just via one helper instead of three
  inline copies. Behavior must be identical (verified on fresh + legacy DBs).
- **Decision needed (human):** choose the lane —
  1. **Normal + migration waiver (recommended):** treat as behavior-preserving refactor; keep
     `Lane: normal`; commit with `RISK_WARN_CATEGORIES="data-loss/migration"`; elevated proof = a
     **legacy-DB migration test** (add a column to a pre-existing table) + final correctness review.
  2. **High-risk (full ceremony):** brainstorming → xia2 → writing-plans → execute. Heavier; the
     conservative reading of the "migration" hard gate.
- **Status:** RESOLVED 2026-06-18 — human chose **Normal + migration waiver**. Commit with
  `RISK_WARN_CATEGORIES="data-loss/migration"`; behavior-preserving refactor (no new/destructive
  migration). Elevated proof required: a legacy-DB migration test (ALTER path on a pre-existing
  table) + the final correctness review. `Lane: normal` stands.
