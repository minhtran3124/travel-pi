# Travel Planner

An AI-assisted travel-planning product. Plan a trip through conversation, discover
places, check weather, search flights and hotels, manage bookings and expenses, and
keep a trip journal.

This is a monorepo with a Next.js web application and a FastAPI backend. The backend
also hosts the LangGraph-based travel agent.

## Product boundaries

The product deliberately mixes real user data with safe, deterministic travel inventory.

| Real and persisted | Synthetic or read-only |
| --- | --- |
| Trips, bookings, expenses, saved places, journals, conversations, and agent configuration | Flight search results, hotel availability, and FX data |
| Weather, air quality, climate, and routing use external services | No payment processing or external booking provider |
| A configured LLM provider can power the travel agent | Tests use a deterministic `FakeLLM` and make no LLM-network calls |

## Architecture at a glance

```text
apps/web (Next.js + TypeScript)
        │  /api/be/* proxy
        ▼
apps/api (FastAPI)
  routers → services → repositories → SQLite / Postgres
        │
        └─ LangGraph travel agent
           supervisor → specialist agents → domain tools
```

The agent has focused planner, concierge, journal, booking, and budget specialists.
Read [WORKFLOW.md](WORKFLOW.md) for the request flow, memory model, streaming, and
provider configuration.

## Prerequisites

- Node.js **22.13 or newer** and pnpm 11 (`corepack enable pnpm`)
- Python **3.10 or newer** and [uv](https://docs.astral.sh/uv/)
- Docker Desktop only if you want the Postgres-backed stack

## Quick start

From the repository root:

```bash
corepack enable pnpm
pnpm install

uv venv
uv pip install --python .venv/bin/python -r apps/api/requirements.txt

cp apps/api/.env.example apps/api/.env
cp apps/web/.env.example apps/web/.env.local
```

The API runs with its SQLite default and does not require an LLM key for tests. Set a
provider key in `apps/api/.env` when you want live model-backed agent replies. The web
app’s Supabase variables are required for its auth clients; use the values for your
Supabase project when exercising signed-in flows.

Start the applications in separate terminals:

```bash
make api       # FastAPI at http://localhost:8000; docs at /docs in development
make web       # Next.js at http://localhost:3000
```

Or start both through Turborepo:

```bash
make dev
```

The web app proxies `/api/be/*` to `http://localhost:8000` by default. Override that
origin with `NEXT_PUBLIC_API_URL` in `apps/web/.env.local` when needed.

## Everyday commands

| Goal | Command |
| --- | --- |
| Run the backend test suite on SQLite | `make test` |
| Run backend tests against throwaway Postgres | `make test-docker` |
| Lint all workspaces | `make lint` |
| Build all workspaces | `make build` |
| Run frontend tests | `pnpm --filter @travel/web test` |
| Build the frontend only | `pnpm --filter @travel/web build` |
| Seed the local backend database | `make seed` |
| Start / stop API + Postgres with Docker | `make up` / `make down` |
| Run the agent eval locally (smoke / full judged / regression gate) | `make eval-smoke` / `make eval-full` / `make eval-check` |

For backend-specific commands, migrations, database behavior, and API endpoints, see
[apps/api/README.md](apps/api/README.md). Swagger is available at
`http://localhost:8000/docs` during local development.

## Repository map

```text
apps/
  api/       FastAPI API, domain services, repositories, agent, tools, and tests
  web/       Next.js user interface and typed API client
docs/        Longer-form documentation and accepted solutions
specs/       Feature plans and implementation summaries
```

The backend follows `routers → services → repositories`; SQLAlchemy ORM work belongs
in repositories. The frontend consumes the API through `/api/be/*` and generates its
API types from the backend OpenAPI document.

## Working with the codebase

Start with the document that matches the task instead of trying to absorb the entire
repository:

| If you need to… | Start here |
| --- | --- |
| Orient yourself to the product and repository | [AGENTS.md](AGENTS.md) |
| Change the backend | [CLAUDE.md](CLAUDE.md), then [apps/api/README.md](apps/api/README.md) |
| Understand or change the AI agent | [WORKFLOW.md](WORKFLOW.md) and [WORKFLOW_DIAGRAM.md](WORKFLOW_DIAGRAM.md) |
| Confirm framework versions and supported tooling | [TECHSTACKS.md](TECHSTACKS.md) |
| Find history for a feature | [specs/](specs/README.md) and the relevant `specs/<slug>/` directory |
| Work on the web planner | `apps/web/` plus [specs/monorepo-fe](specs/monorepo-fe/) and [specs/web-trip-planner](specs/web-trip-planner/) |

### For coding agents and contributors

1. Read `AGENTS.md` first. For backend work, read `CLAUDE.md` before editing.
2. Locate the relevant feature spec. Use the existing plan and summary as context; create
   a new `specs/<slug>/` record for multi-step work.
3. Keep changes surgical. Preserve the layering boundary, avoid speculative refactors,
   and do not treat synthetic travel inventory as real booking or payment data.
4. Run the narrowest relevant verification command and record what actually ran. Do not
   claim completion based only on a code or documentation diff.

Project conventions and working agreements live in [`.claude/rules/`](.claude/rules/).
They cover planning thresholds, scope control, verification, and documentation records.

## More documentation

- [API reference](apps/api/APIS.md)
- [Agent eval: how to run it locally](apps/api/eval/README.md)
- [Agent workflow diagram](WORKFLOW_DIAGRAM.md)
- [Technology stack](TECHSTACKS.md)
- [Feature specs](specs/README.md)
