# rename-crud-to-repositories — Summary

Lane: normal
Confidence: high
Reason: Mechanical, fully reversible rename of the data-access package — no hard gates fired; lands as `normal` (not `tiny`) only because it touches 37+ files across all domains rather than ≤1.
Flags: none
Affects: `app/crud/` data-access layer (internal module path; no public API/contract change)
Input-type: change request

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

i want to rename folder "curd" to "repositories", it make clear more

<!-- "curd" is a typo for the existing `app/crud/` package. -->

## What changed

Rename the data-access package `app/crud/` → `app/repositories/` (and mirror `tests/crud/` → `tests/repositories/`), update all `app.crud` import references, and update the active documentation that names the layer (CLAUDE.md, README.md, the architecture rule). No behavior change; all generation seeds, schema, and public API shapes are untouched. Historical `specs/` records are left as-is (audit trail).

### Rationale

`repositories` matches the per-entity repository pattern the layer already implements (the architecture test even calls them "repos"), making the layer's role self-evident. Chosen as a pure rename because the change is mechanical and the 663-test suite (SQLite + Postgres parity) catches any broken import loudly.

### Alternatives considered

- Keep `crud/` — rejected: the user explicitly wants the clearer name, and the code already speaks in "repos".
- Rewrite historical `specs/` mentions too — rejected: those are dated audit records of past work; rewriting them falsifies history. Only active docs are updated.

### Deviations

- none

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| import sanity | `python -c "import app.repositories"` | 0 | OK |
| full suite (SQLite) | `make test` | 0 | 682 passed |
| no stale refs | `grep -rn "app\.crud" app tests scripts alembic` | 1 | no matches |
| lint | `ruff check app scripts tests` | 0 | all checks passed |

### Rollback

- `git revert <sha>` (pure rename; reversible)

### Harness-Delta

- none
