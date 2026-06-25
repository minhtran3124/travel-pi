# Solutions Index

O(1) lookup of all entries in `docs/solutions/`. Read this first when searching for prior art.

## Entries

| Slug | Category | Module | Tags | Type | Confidence | Confirmed |
|---|---|---|---|---|---|---|
| [public-contract-gate-warn-only](harness/public-contract-gate-warn-only.md) | harness | harness/intake | risk-corroboration, public-contract, feature-intake, openapi, lane | knowledge | high | 2026-06-23 |
| [untracked-py-gate-root-claude](harness/untracked-py-gate-root-claude.md) | harness | harness/hooks | check-untracked-py, hook, claude-dir, path-pattern, grep | bug | high | 2026-06-23 |
| [formatter-strips-unused-import](harness/formatter-strips-unused-import.md) | harness | harness/editing | postusetool-formatter, ruff, autoflake, fastapi, imports | failure | high | 2026-06-18 |
| [commit-gate-bare-python](harness/commit-gate-bare-python.md) | harness | harness/hooks | commit-quality-gate, hook, python, path, venv | bug | high | 2026-06-18 |

## Critical Patterns

`critical-patterns.md` is always read regardless of query domain — do not skip it.

## Maintenance

- `/compound` appends a row here on every new solution file
- Downgrade confidence on rows whose `confirmed_at` has aged past the decay thresholds (see README.md)
- Remove rows only when the underlying file is deleted (add a tombstone line if needed)
