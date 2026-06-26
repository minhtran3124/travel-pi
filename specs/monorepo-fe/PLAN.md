---
slug: monorepo-fe
status: proposed
owner: Minh Tran
created: 2026-06-26
---

# Monorepo — Phase 0: Restructure BE into apps/api + Next.js scaffold

> Phase 0 of the `monorepo-fe` initiative. Converts the BE-only repo into a
> Next.js + FastAPI Turborepo monorepo **without changing API behavior**.
> The full FE app is a later phase (needs `/brainstorming` first — see SUMMARY.md).

## 1. Motivation

Repo is BE-only. Owner wants FE + BE in one repo: BE → `apps/api`, FE = Next.js in
`apps/web`, best-practice tooling (pnpm workspaces + Turborepo). Validated layout:
`apps/web` + `apps/api` + thin `package.json` in the Python app so Turborepo can
orchestrate it (ref: cording12/next-fast-turbo).

## 2. Non-goals

- No FE features beyond a wiring-proof skeleton (one real BE call). Full FE = Phase 1+.
- No change to any API route, schema, or behavior. Tests must pass **unchanged**.
- No Python import rewrites — `app.*` stays the top-level package by operating from `apps/api`.
- No `packages/` shared libs yet (e.g. generated SDK) — deferred to Phase 1.

## 3. Success Criteria

- `cd apps/api && <venv>/bin/python -m pytest tests/ -q` → all 685 tests green from new location.
- `pnpm turbo run test --filter=@travel/api` runs the BE suite via Turborepo.
- `apps/web` builds and renders one page that fetches a real BE endpoint.
- CI green at new paths. `make dev`/`make seed`/Docker parity intact.
- Zero diff to any `app/**` or `tests/**` Python file content (move only).

## 4. Key design decision (why this is low-risk)

**Operate from `apps/api` as the Python project root.** The BE moves as a self-contained
block (`app/ tests/ scripts/ alembic/ eval/` + `alembic.ini Makefile Dockerfile
docker-compose*.yml requirements*.txt pyproject.toml .env.example .dockerignore docker/`).
Because everything runs with CWD=`apps/api`, all *relative* references stay correct:

| Reference | Stays valid because |
|---|---|
| `uvicorn app.main:app`, `pytest tests/` | CWD=apps/api → `app` is top-level package |
| alembic `prepend_sys_path = .`, env.py `parents[1]` | resolve to apps/api |
| ruff `src = ["app","scripts"]` (pyproject) | pyproject moves with them |
| docker-compose `build: .`, Dockerfile `COPY . .` | compose files move into apps/api |
| `from app.X import Y` (×622) | **unchanged — no rewrite** |

Only **additive root tooling** and a few **path-prefix fixes** (CI, hooks, docs, venv var)
need editing.

## 5. Tasks

### Task 1.1 — Relocate the BE as a self-contained block

```xml
<task id="1.1" wave="1">
  <files>app/, tests/, scripts/, alembic/, eval/, alembic.ini, Makefile, Dockerfile, .dockerignore, docker/, docker-compose.yml, docker-compose.test.yml, requirements.txt, requirements-ai.txt, pyproject.toml, .env.example, APIS.md, AGENT_IMPROVEMENTS.md, PRODUCT.md, DESIGN.md</files>
  <action>git mv each listed path into apps/api/ (preserving names), e.g. `git mv app apps/api/app`. Do NOT edit any moved file's content in this task except apps/api/Makefile: add `VENV ?= ../.venv` and replace the literal `.venv/` prefix in its recipes with `$(VENV)/` so it reuses the repo-root venv. Keep the repo-root .venv as the single Python venv. README.md, CLAUDE.md, .gitignore, .editorconfig, .github/, .claude/, specs/, docs/ stay at repo root.</action>
  <verify>cd apps/api && ../.venv/bin/python -m pytest tests/ -q</verify>
  <done>All 685 tests pass from apps/api; `git status` shows renames only (no content diff) for app/** and tests/**.</done>
</task>
```

### Task 2.1 — Monorepo tooling (root + apps/api wrapper)

```xml
<task id="2.1" wave="2">
  <files>package.json, pnpm-workspace.yaml, turbo.json, apps/api/package.json, Makefile, .gitignore</files>
  <action>Add root package.json (private, packageManager pnpm@9.x, workspaces apps/*+packages/*), pnpm-workspace.yaml (apps/*, packages/*), turbo.json (turbo 2.x `tasks` key: dev[cache:false,persistent], build, lint, test). Add apps/api/package.json: name `@travel/api`, scripts dev/test/lint/build that shell to its Makefile (`make dev|test|lint`, build no-op). Add a root Makefile delegating `dev/test/lint/seed` into apps/api via `$(MAKE) -C apps/api` and FE targets later. Append node_modules/, .next/, .turbo/, pnpm-debug.log to root .gitignore.</action>
  <verify>npx --yes turbo@^2 run build --dry-run=json | grep -q '@travel/api'</verify>
  <done>turbo.json parses; workspace graph includes @travel/api; `make test` from root runs the BE suite.</done>
</task>
```

### Task 3.1 — Scaffold apps/web (Next.js) + prove BE wiring

```xml
<task id="3.1" wave="3">
  <files>apps/web/</files>
  <action>Scaffold a Next.js App Router app (TypeScript, Tailwind, ESLint) in apps/web with name `@travel/web`. Add next.config rewrite proxying `/api/be/:path*` → `${NEXT_PUBLIC_API_URL:-http://localhost:8000}/:path*`. Build one page (app/page.tsx) that server-fetches a real BE endpoint (GET /weather?city=Hanoi or /destinations) through the proxy and renders the JSON, to prove FE↔BE wiring. No design system yet — minimal.</action>
  <verify>cd apps/web && pnpm install --silent && pnpm run lint</verify>
  <done>apps/web lints clean; `pnpm run build` succeeds; page fetches BE when both run.</done>
</task>
```

### Task 4.1 — CI path update

```xml
<task id="4.1" wave="4">
  <files>.github/workflows/ci.yml</files>
  <action>Point the existing BE job at apps/api (job-level `defaults.run.working-directory: apps/api`, or `cd apps/api` per step) so `uv pip install -r requirements.txt` and `pytest tests/ -q` resolve. Keep Postgres parity job. Optionally add a lightweight apps/web lint+build job (pnpm).</action>
  <verify>cd apps/api && ../.venv/bin/python -m pytest tests/ -q -k "not slow" >/dev/null 2>&1; python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml'))"</verify>
  <done>ci.yml is valid YAML; BE steps reference apps/api paths.</done>
</task>
```

### Task 4.2 — Harness hook path fixes (HARD GATE — see §5a)

```xml
<task id="4.2" wave="4">
  <files>.claude/hooks/commit-quality-gate.sh, .claude/settings.local.json</files>
  <action>Update path globs/prefixes from `app/`,`tests/`,`scripts/` to `apps/api/app/`,`apps/api/tests/`,`apps/api/scripts/` in commit-quality-gate.sh (the 8 references: cached diff filters, app-file detection, test-pair lookup, verify_summary.py path, large-session detection). Update the one `app/templates/visa.html` path in settings.local.json to `apps/api/app/templates/visa.html`. Surgical — match existing style, no logic changes.</action>
  <verify>bash -n .claude/hooks/commit-quality-gate.sh && python3 -c "import json;json.load(open('.claude/settings.local.json'))"</verify>
  <done>Hook parses; test-pairing gate again fires for apps/api/app/** changes.</done>
</task>
```

### Task 4.3 — Docs: CLAUDE.md + README

```xml
<task id="4.3" wave="4">
  <files>CLAUDE.md, README.md</files>
  <action>CLAUDE.md: replace the stale "Ignore apps/ and packages/ — stale, not buildable" line; document the monorepo layout (apps/api = FastAPI, apps/web = Next.js), updated Run & Test commands (root `make` delegates; `pnpm turbo`), and that BE work happens under apps/api. README.md: short monorepo overview + how to run FE and BE.</action>
  <verify>grep -q "apps/api" CLAUDE.md && ! grep -q "stale, not buildable" CLAUDE.md</verify>
  <done>CLAUDE.md reflects monorepo; no stale apps/ guidance remains.</done>
</task>
```

## 5a. Hard gate — Task 4.2 touches `.claude/hooks/*`

Per `rules/auto-correct-scope.md` Rule 4, editing a `.claude/hooks/*` script is a high-blast
action requiring explicit user authorization (it auto-runs every session). 4.2 is **necessary**
— without it the commit-quality-gate test-pairing check silently no-ops after the move (fail-open,
not a block, so it does not stop the work, but the gate stays disabled). Execute 4.2 only after
the user OKs the hook edit. **Rollback:** `git checkout .claude/hooks/commit-quality-gate.sh .claude/settings.local.json`.

## 6. Waves

| Wave | Tasks | Parallelism | Barrier |
|---|---|---|---|
| 1 | 1.1 relocate BE | single | tests green before tooling |
| 2 | 2.1 root tooling | single | turbo graph resolves @travel/api |
| 3 | 3.1 apps/web scaffold | single | FE lints/builds |
| 4 | 4.1 CI, 4.2 hooks*, 4.3 docs | 3 parallel (disjoint files) | * 4.2 gated on user OK |

## 7. Risks

- **venv location:** kept single root `.venv`; apps/api/Makefile uses `VENV ?= ../.venv`. If CI
  creates its own venv, the working-directory change in 4.1 handles it.
- **Hook fail-open window:** between 1.1 and 4.2 the quality gate's test-pairing no-ops. Acceptable
  (other gates still run); 4.2 restores it same session.
- **travel.db:** gitignored, regenerated; tests use isolated temp SQLite, unaffected by the move.
- **Docker build context:** unchanged (`build: .`) because compose files move into apps/api; verify
  with `make test-docker` post-merge (not in fast verify — >60s).

## 8. Status Log

- 2026-06-26 — Plan drafted. Awaiting user OK on Task 4.2 (hook hard gate) before execution.
