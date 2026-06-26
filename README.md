# Travel Planner — monorepo

A Next.js frontend and a FastAPI mock backend in one repo, managed with
pnpm workspaces + Turborepo.

```
apps/
  api/   FastAPI mock backend (Python, uv)  — see apps/api/README.md
  web/   Next.js frontend (TypeScript)
packages/  shared libraries (none yet)
```

## Prerequisites

- **Node ≥ 20** and **pnpm** (`corepack enable pnpm`)
- **Python 3.10+** and **[uv](https://docs.astral.sh/uv/)** (for the backend)

## Setup

```bash
pnpm install                                   # JS deps (FE + tooling)
uv venv && uv pip install -r apps/api/requirements.txt   # BE deps (root .venv)
```

## Run

```bash
make api          # backend only  → http://localhost:8000  (Swagger at /docs)
make web          # frontend only → http://localhost:3000
make dev          # both, via turbo
```

The frontend proxies `/api/be/*` to the backend (`NEXT_PUBLIC_API_URL`, default
`http://localhost:8000`). The home page fetches a real backend endpoint to prove
the wiring.

## Test & lint

```bash
make test         # backend suite (delegates to apps/api)
make lint         # lint all apps (turbo)
pnpm --filter @travel/web build   # production build of the frontend
```

Backend details (Docker, Postgres, Alembic, seeding) live in
[`apps/api/README.md`](apps/api/README.md).
