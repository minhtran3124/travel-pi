<!-- auto: bootstrap-xia2 (2026-07-09) — travel-pi FastAPI profile, tailored from CLAUDE.md's
     documented layout (the bundled templates/stacks/fastapi/ profile assumes config/·database/·
     redis/·usecases/·pgvector·payments which this repo does NOT use). Review, then move over
     .claude/rules/architecture.md. -->

# Architecture Profile — travel-pi (FastAPI + LangGraph)

Authoritative architecture reference. Consult before implementing, debugging, or reviewing.
Primary orientation lives in `CLAUDE.md`, `AGENTS.md`, `TECHSTACKS.md`, and `WORKFLOW.md` (the
agent architecture) — this file is the layer/pattern SoT for review.

---

## What this is

FastAPI mock backend for a Travel Planner agent. Everything is faked except keyless Open-Meteo
calls (`/weather`, `/air-quality`, `/destinations/{city}/climate`), `/*/route` (OpenRouteService,
haversine fallback), and the AI agent's LLM calls (real provider via `init_chat_model()` when keys
set; `FakeLLM` in tests). Flights, hotel availability, trips, bookings, FX are deterministic /
DB-seeded fakes. Monorepo: BE in `apps/api/`, Next.js FE in `apps/web/`.

## Project Structure (`apps/api/app/`)

```
main.py         # app factory: CORS, exception handlers, middleware
exceptions.py   # domain exceptions (AppError subclasses), no FastAPI deps
core/           # config (Settings), logging, lifespan, auth (Supabase JWKS), geo, text (fuzzy)
routers/        # one file per endpoint group (HTTP interface only)
services/       # business logic; raise domain exceptions, never HTTPException
repositories/   # SQLAlchemy ORM data access ONLY — no logic
agents/         # LangGraph supervisor + 5 ReAct sub-agents, nodes, state, context, checkpointer
tools/          # agent tools grouped by domain (registry.py = single source of truth); via mcp/
mcp/            # MCP server exposing registry tools to external clients
clients/llm.py  # provider-agnostic LLM client (init_chat_model; FakeLLM in tests)
streaming/      # SSE event contract (events.py, mapper.py, panels.py) consumed by apps/web
memory/         # conversation memory (summarizer / store)
db/             # engine, session (get_session DI), models/, seed.py
schemas/        # Pydantic v2 models (extend AppBaseModel)
data/           # seed source of truth (imported only by db/seed.py)
alembic/        # migrations
```

## Request / Data Flow

- **HTTP:** Request → middleware → (auth dep where applied) → Router (Pydantic validation) →
  Service (business logic) → Repository (ORM) → SQLite/Postgres → Pydantic response.
- **Agent (`/agent/*`):** Router → LangGraph graph (built once in `core/lifespan.py`) →
  supervisor → planner/concierge/journal/booking/budget → reflection → SSE stream
  (`streaming/mapper.py`) → `apps/web`. Tools open their own session via `session_scope()`.
- **Errors:** services raise domain exceptions (`NotFoundError`→404, `ConflictError`→409,
  `UpstreamError`→502); `main.py` handlers map them. Never raise `HTTPException` from services.

## Layer Responsibilities

- **Routers** — HTTP interface only: validate, delegate, return. No business logic, no ORM.
- **Services** — business logic + orchestration; raise domain exceptions.
- **Repositories** — ORM/data-access only. Models live in `db/models/`, referenced as
  `models.Hotel` etc. (avoid collision with Pydantic schemas). No logic here.
- **Agents/Tools/MCP** — thin adapters over services; NO business logic. `tools/registry.py`
  (`ALL_TOOLS`) is the single source of truth and auto-feeds the MCP surface.

## Key Patterns

| Pattern | Implementation |
|---|---|
| Layering | routers → services → repositories (no usecases layer) |
| Domain exceptions | `AppError` subclasses in `exceptions.py` → HTTP status in `main.py` |
| Dependency Injection | `Depends(get_session)` request-scoped; `session_scope()` for tools/background |
| Deterministic fakes | flights + hotel availability seeded from MD5 hash — **do not change the algorithm** |
| Async only for real I/O | `weather_service`, `routing_service`; everything else is sync |
| Agent graph | LangGraph supervisor + 5 sub-agents, built once at lifespan startup |
| Provider-agnostic LLM | `init_chat_model()`; `FakeLLM` in tests (no network) |
| Tool registry → MCP | registry membership auto-exposes tools over MCP with readOnly/destructive hints |
| Conversation persistence | LangGraph checkpointer (Postgres dev/prod; MemorySaver fallback) |

## Infrastructure

| Component | Technology |
|---|---|
| Persistence | SQLite locally / Postgres in Docker (by `DATABASE_URL`); Alembic migrations |
| Auth | Supabase JWT verified against JWKS (`core/auth.py`, `PyJWKClient`) |
| AI agent | LangGraph + provider-agnostic LLM (OpenAI default); MCP server for external clients |
| Real upstreams | Open-Meteo (weather), OpenRouteService (routing, haversine fallback) |
| FE | Next.js (`apps/web/`), pnpm + Turborepo, Node v24 |

> No Redis, no pgvector/RAG (RAG removed), no payments, no usecases layer — do not assume the
> generic FastAPI template's shape.
