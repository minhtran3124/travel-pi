---
problem_type: knowledge
module: monorepo
tags: monorepo, turborepo, pnpm, relocation, python, cwd-tooling
severity: critical
applicable_when: Moving an existing self-contained language sub-app into apps/<x> in a monorepo and you want to avoid rewriting its imports.
affects:
  - apps/api/Makefile
  - turbo.json
  - pnpm-workspace.yaml
  - apps/api/package.json
supersedes: null
confidence: high
confirmed_at: 2026-06-26
---
## Applicable When

Relocating a self-contained language sub-app (e.g. a FastAPI backend) into `apps/<x>/` as part of a monorepo conversion, when its tooling addresses files by **relative** paths and you want zero source churn.

## Pattern

**Move the whole sub-app as one block and run every tool with CWD set to that subdir** — do NOT rename the import package. Because all tool config is relative and the top-level package name is unchanged, nothing needs rewriting:

- `alembic.ini` `prepend_sys_path = .` and `env.py` `parents[1]` resolve from `apps/api`
- `docker-compose` `build: .` resolves to `apps/api` (compose files move with the app)
- `ruff` `src = ["app","scripts"]` (pyproject moves with the app)
- the import package stays `app.*` → **zero `from app...` rewrites** (this session avoided rewriting 622 imports that the naive "rename to `apps.api.app`" path would have required)

The load-bearing invariant: **relative-path config + CWD discipline + unchanged package root**. The relocation collapses from "622 import rewrites + path surgery" to "`git mv` block + `cd apps/<x>`".

## How to Use

1. `git mv app tests scripts alembic … apps/api/` as a block (keep configs with the code: alembic.ini, Makefile, Dockerfile, compose, requirements, pyproject, .env.example).
2. Run all sub-app commands from `apps/api` (Makefile targets, CI `working-directory: apps/api`, docker build context = `apps/api`).
3. **Polyglot Turborepo orchestration:** give the non-JS app a thin `package.json` (`@scope/api`) whose scripts shell to `make` (`"test": "make test"`), so `turbo` can drive it from the same task graph as the JS apps.
4. **Single root venv:** `apps/api/Makefile` uses `VENV ?= ../../.venv` so the relocated app resolves its interpreter at the monorepo root instead of carrying its own.

## Code Example

```makefile
# apps/api/Makefile — single root venv, CWD-relative
VENV ?= ../../.venv
test:
	$(VENV)/bin/python -m pytest tests/ -q
```

```json
// apps/api/package.json — thin wrapper so Turborepo orchestrates the Python app
{ "name": "@travel/api", "private": true,
  "scripts": { "dev": "make dev", "test": "make test", "lint": "make lint", "build": "echo no-op" } }
```

## Gotchas

- `pnpm test -- <name>` does **not** forward the positional as a vitest path filter — it runs the whole suite. Use `pnpm exec vitest run <name>` to scope to one file.
- Verify renames are renames-only: `git diff --cached --name-status -M` should show `R100` for moved source (only config you intentionally edit, like the Makefile VENV line, should differ).

## Related
- docs/solutions/monorepo/phase1-architecture-decisions.md
- docs/solutions/harness/wave-shared-file-partition.md
