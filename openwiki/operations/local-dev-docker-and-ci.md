---
type: operations
title: Local development, Docker and CI
description: How to run, test and ship the monorepo — toolchain requirements (Node 24 with pnpm 11, Python via a single root uv venv), the root and backend Make targets, the Docker Compose dev stack with pgvector Postgres and the throwaway Postgres test stack, seeding and data-generation scripts, the pinned dependency policy, and every GitHub Actions workflow (secrets scan, API and web CI, the opt-in e2e job, the keyless agent-eval gate, the state-on-merge spec bookkeeping and the scheduled OpenWiki refresh).
tags: [operations, makefile, docker, ci, github-actions, pnpm, uv, toolchain]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-18T04:47:06.927Z
sources:
  - id: openwiki-source-164e2da859b5277df81c7d94
    resource: repo://.github/workflows/ci.yml
  - id: openwiki-source-9ea7004cd60fc78ed888a032
    resource: repo://.github/workflows/eval.yml
  - id: openwiki-source-6d4b4e707b8d60b6ccfa3425
    resource: repo://.github/workflows/openwiki-update.yml
  - id: openwiki-source-732ec7ab6498165b4e6d98af
    resource: repo://.github/workflows/state-on-merge.yml
  - id: openwiki-source-005fa33a80365b59c59a2523
    resource: repo://apps/api/docker-compose.test.yml
  - id: openwiki-source-555487c3c39cc1f3039be31e
    resource: repo://apps/api/docker-compose.yml
  - id: openwiki-source-c67fada0a467b1fb8d2dec3a
    resource: repo://apps/api/docker/entrypoint.sh
  - id: openwiki-source-74dac8f3a8700bf870db47a8
    resource: repo://apps/api/Makefile
  - id: openwiki-source-433db6b1a4d324432630a14a
    resource: repo://apps/api/requirements-ai.txt
  - id: openwiki-source-ec60cf4e5fef6b1d32582303
    resource: repo://apps/api/requirements.txt
  - id: openwiki-source-b71a2db39f6d466021257a3b
    resource: repo://apps/api/scripts/start.sh
  - id: openwiki-source-02d70415be97f3061192e2bd
    resource: repo://apps/web/.nvmrc
  - id: openwiki-source-a2371d6362e5db4bc834ad03
    resource: repo://CLAUDE.md
  - id: openwiki-source-012f2c78e3b1446dfc35803f
    resource: repo://Makefile
  - id: openwiki-source-5b54a58d1b51cd490b0e7162
    resource: repo://package.json
generated: { by: "claude-code", at: "2026-09-18T04:47:06.927Z" }
---

# Local development, Docker and CI

## Toolchain

- **Node 24 and pnpm 11.** The root `package.json` pins `pnpm@11.9.0` and requires Node ≥ 22.13; `apps/web/.nvmrc` selects `24.17.0` and CI uses Node 24. On a machine whose default `nvm` node is older, put `~/.nvm/versions/node/v24.17.0/bin` on `PATH` before any pnpm command, since pnpm 11 will not start on Node 18.
- **Python via uv, one venv.** `uv venv` at the repository root creates `.venv`, and `uv pip install -r apps/api/requirements.txt` installs the backend; `apps/api/Makefile` resolves `VENV ?= ../../.venv`, so every backend target uses that interpreter. CI runs Python 3.12 and the Docker image is Python 3.12 slim, whereas a local interpreter may be newer, which is one reason the Docker test stack exists.
- **Commands run from the app directory**: backend commands from `apps/api/`, frontend commands from `apps/web/`, or through the root `Makefile`, which is a thin delegation layer (see [Monorepo overview](../architecture/monorepo-overview.md)).

## Quick start

```bash
corepack enable pnpm && pnpm install
uv venv && uv pip install --python .venv/bin/python -r apps/api/requirements.txt
cp apps/api/.env.example apps/api/.env
cp apps/web/.env.example apps/web/.env.local
make api    # FastAPI on :8000, Swagger at /docs
make web    # Next.js on :3000
make dev    # both, through Turbo
```

The API runs on its SQLite default with no `.env` and no LLM key; the web app needs its public Supabase variables to construct its auth clients (see [Configuration and environments](../architecture/configuration-and-environments.md)). Swagger and the OpenAPI schema are served only outside production.

## Make targets

The root `Makefile` delegates: `dev`, `build`, `lint` run through Turbo; `test`, `test-docker`, `seed`, `api`, `up`, `down` and every `eval-*` target call `make -C apps/api`; `fe`/`web` start the Next dev server; `diagram` renders `WORKFLOW_DIAGRAM.md` to HTML.

`apps/api/Makefile` owns the backend lifecycle: `install` (uv venv + requirements), `dev` (uvicorn with reload on port 8000), `up`/`down`/`logs`/`exec-api`/`exec-db` for the Docker stack, `migrate` (`alembic upgrade head`), `seed` (runs `seed_all` against the configured `DATABASE_URL`), `test` (pytest on SQLite), `test-docker`, `fmt`/`lint` (ruff over `app` and `scripts`; tests are formatted the same way but not gated, and `alembic/` is excluded), and the eval targets (`eval-smoke`, `eval-full` with `--repeat 3`, `eval-html`, `eval-baseline`, `eval-compare` which exits 1 on regression, and `eval-check` = full + compare). Run a single test file with `../../.venv/bin/python -m pytest tests/<path> -xvs` from `apps/api/`.

## Docker

`apps/api/docker-compose.yml` runs two services: `db`, a `pgvector/pgvector:pg17` Postgres on host port **5433** with a persistent `pgdata` volume and a `pg_isready` health check, and `api`, built from the local `Dockerfile`, loading `.env` but overriding `DATABASE_URL` to the `db` service and `ENVIRONMENT=development`, bind-mounting the source tree and running uvicorn with `--reload` so host edits reach the container. The image's entrypoint runs `alembic upgrade head` before serving, so the shared dev database is migrated automatically on every start (see [Data layer and migrations](../architecture/data-layer-and-migrations.md)). `scripts/start.sh` is a `docker compose up --build` alias for non-Make users. Prefer `docker compose up -d` over restarting a single container, because a restarted container can lose the compose network's DNS for `db`.

`docker-compose.test.yml` is the parity proof: a `postgres:17-alpine` on **tmpfs** (wiped on teardown) plus a `tests` container that sets both `DATABASE_URL` and `TEST_DATABASE_URL` to it, migrates, and runs the whole pytest suite on Postgres. `make test-docker` brings it up with `--abort-on-container-exit --exit-code-from tests` and then `down -v`. Because it shares the compose project name with the dev stack, the teardown also removes the dev stack's volumes; restart the dev stack afterwards with `docker compose up -d`. See [Backend test strategy](../testing/backend-test-strategy.md).

## Dependencies and pins

`apps/api/requirements.txt` pins upper bounds to the current majors so a fresh install cannot pull a breaking release; FastAPI is capped below 0.137 (and Starlette below 1.3) because that release's route-tree refactor breaks the operation-id and route-enumeration tests, and `requirements-ai.txt` (the LangChain and LangGraph stack) is split out so its large transitive tree resolves independently and must never force those caps upward. The AI floors were last raised to the minimums a future `deepagents` dependency would need, without adding it.

## Seeding and data scripts

Startup, `make seed` and the test fixtures all run the idempotent seeder. `scripts/generate_data.py` prints ready-to-paste hotel dict literals for a city with ids that continue from existing records; `scripts/generate_translations.py` pre-fills catalog translation files; `scripts/ingest_rag.py` upserts the knowledge corpus into a persisted vector store; `scripts/seed_agent_config.py`, `scripts/set_tier.py` and `scripts/seed_supabase_user.py` are the operational scripts described on [LLM providers and per-agent configuration](../agent/llm-providers-and-agent-config.md) and [Authentication and user tiers](../concepts/auth-and-tiers.md).

## GitHub Actions

| Workflow | Trigger | What it does |
|---|---|---|
| `ci.yml` `secrets` | every PR | Downloads a pinned, checksum-verified `gitleaks` binary (not a third-party action, so the scanner is never handed a token; checkout uses `persist-credentials: false`) and scans only the PR's own commit range, with allowlists in `.gitleaks.toml`. |
| `ci.yml` `api` | every PR | Python 3.12 + uv, `pytest tests/ -q` on SQLite. |
| `ci.yml` `web` | every PR | Node 24 + pnpm, `lint`, `test` (Vitest) and `build` for `@travel/web`. |
| `ci.yml` `web-e2e` | after `web`, only when all four e2e secrets are set | Starts the backend on SQLite with every LLM key blanked and the Supabase URL from secrets, waits for `/docs`, installs Chromium, runs the Playwright suite against the shared e2e account, and uploads the report and traces on failure. A half-configured repository skips the job with a note instead of reporting green on skipped tests. |
| `eval.yml` | PRs touching agents, prompts, tools, `eval/` or `evalkit/` | Runs the offline `tests/eval` suite (portability boundary, dataset validation, deterministic and trajectory metrics) and a `--dry-run` of the smoke suite. The judged eval **never runs on CI** by decision; `make eval-check` is the local, human-gated regression gate (see [Agent evaluation harness](../testing/agent-eval-harness.md)). |
| `state-on-merge.yml` | a PR merged into `main` from the same repository | Lists the PR's changed files, runs `.github/scripts/state_on_merge.py` to mark the matching `specs/<slug>` shipped and refresh `specs/STATE.md`, and pushes straight to `main` with up to three rebase retries; a `GITHUB_TOKEN` push cannot retrigger workflows, so it cannot loop. |
| `openwiki-update.yml` | daily schedule or manual | Installs a pinned OpenWiki, runs `openwiki code --update --print` with full history, removes transient run state, and opens a `docs: update OpenWiki` pull request that preserves partial progress when the run fails. |

The frontend e2e suite is opt-in locally too: `pnpm e2e` from `apps/web` with the backend already on `:8000` and the e2e credentials in `.env.local` (see [Frontend unit tests and Playwright e2e](../testing/frontend-tests-and-e2e.md)).

## Git conventions

Feature PRs target the current integration branch rather than `main` directly, staging and committing are separate commands (a local hook blocks compound `git add … && git commit …`), and the repository owner's GitHub account is used for pushes and pull requests.
