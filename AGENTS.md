# AGENTS.md — Start Here

> First read for any agent or teammate joining this repo. It gives you the **vision**,
> the **mental model**, and a **map** of where to go next. It does not repeat setup
> (`README.md`) or the full rule set (`CLAUDE.md`) — it points you to them.

---

## The vision (what we're building)

A **Travel Planner** product: an AI travel assistant that helps a user plan a trip
end-to-end — discover places, check weather, search flights/hotels, track a budget,
book, and keep a trip journal — through a natural conversation.

Two halves, one monorepo:

- **`apps/api`** — a **FastAPI backend** with full CRUD APIs (trips, bookings,
  expenses, hotels, places, …) persisted in SQLite/Postgres. Real external calls:
  keyless weather/air-quality/climate (Open-Meteo), routing (OpenRouteService, with a
  haversine fallback), and the agent's **LLM calls** (a real provider when keys are
  set; `FakeLLM` in tests). It also hosts the **agentic brain**: a multi-agent
  LangGraph chatbot (supervisor → specialist sub-agents → tools).
- **`apps/web`** — a **Next.js + TypeScript frontend** (in active build-out) that
  consumes the backend and surfaces the planner UI.

Travel *inventory* stays synthetic on purpose: flights and hotel availability are
generated deterministically from seed data, and FX is a static snapshot — zero real
money and no external booking providers. Everything the user creates (trips, bookings,
expenses, journals) is real, persisted CRUD.

---

## Mental model (how it fits together)

```
  ┌────────────┐        /api/be/*         ┌──────────────────────────────┐
  │  apps/web  │  ───────proxy──────────▶ │           apps/api           │
  │  Next.js   │                          │  FastAPI backend             │
  │  (UI)      │ ◀───────JSON──────────── │                              │
  └────────────┘                          │  routers → services → repos  │
                                          │  ───────────────────────────│
                                          │  Agent: supervisor + 5       │
                                          │  ReAct sub-agents + tools    │
                                          │  (LangGraph, provider-agnostic)
                                          └──────────────────────────────┘
                                                   │
                                          SQLite (local) / Postgres (Docker)
```

- **Backend layering:** `routers → services → repositories`. Services raise domain
  exceptions; ORM is confined to `repositories/`. (Details in `CLAUDE.md`.)
- **The agent** lives under `apps/api/app/agents/` + `tools/`. A supervisor classifies
  intent and hands off to one of five specialists (planner, concierge, journal,
  booking, budget), each a ReAct loop over a focused tool group. The LLM provider is a
  config switch (OpenAI default), and tests run on a deterministic `FakeLLM`.

---

## Repository map

```
apps/
  api/        FastAPI backend + AI agent     → apps/api/README.md, CLAUDE.md
    app/
      routers/        HTTP endpoints (one file per group)
      services/       business logic
      repositories/   SQLAlchemy data access (ORM lives only here)
      agents/         LangGraph supervisor + sub-agents + nodes + state
      tools/          agent tools, grouped by domain (registry.py)
      clients/llm.py  provider-agnostic LLM client
      memory/         conversation memory (summarizer/store)
      schemas/ db/    Pydantic v2 models + ORM models
  web/        Next.js frontend (TypeScript)
docs/         longer-form documentation
specs/        per-feature folders: PLAN.md / SUMMARY.md / REVIEW.md (git-tracked)
.claude/rules/  the working agreement for agents (see below)
```

---

## Where to go next (by what you're doing)

| You want to… | Read |
|---|---|
| Get the project running | `README.md` (root) → `apps/api/README.md` |
| Know the stack & versions | `TECHSTACKS.md` (root) |
| Work on the **backend** | `CLAUDE.md` (architecture, conventions, run/test) |
| Understand the **AI agent** | `WORKFLOW.md` + `WORKFLOW_DIAGRAM.md` (root) |
| See the agent roadmap/plan | `specs/travel-agent/PLAN.md`, `REVIEW.md` |
| Work on the **frontend** | `apps/web/` + `specs/monorepo-fe/`, `specs/web-trip-planner/` |
| Find prior work on a feature | `specs/<feature-slug>/` (one folder per feature) |

---

## How we work (the short version)

These are enforced conventions, not suggestions. Full text in `.claude/rules/`:

- **Plan before multi-step work.** >3 steps or >2 files → write `specs/<slug>/PLAN.md`
  (`rules/plan-format.md`). Every task records a `SUMMARY.md`.
- **Orchestrate, don't sprawl.** Heavy research/implementation is delegated to
  fresh-context agents; main thread stays a thin coordinator (`rules/orchestration.md`).
- **Surgical changes.** Minimum diff that solves the problem; match existing style; no
  speculative abstractions (`rules/behavior.md`, `rules/guidelines.md`).
- **Evidence over assertion.** "Done" needs a re-runnable verify command, not a claim.
- **Lanes scale ceremony.** A change is classified `tiny | normal | high-risk`; risk
  decides how much proof, ambiguity decides whether a human is asked (`rules/auto-correct-scope.md`).

Backend commands run from `apps/api/` (`make dev`, `make test`); the Python venv is the
single root `.venv`.

---

## The 60-second orientation

1. It's a **monorepo**: `apps/web` (UI) + `apps/api` (CRUD backend + AI agent).
2. CRUD (trips, bookings, expenses, …) is **real and persisted**; only travel inventory (flights, hotel availability, FX) is synthetic/seeded. Weather, routing, and the agent's LLM calls hit real services.
3. The interesting part is the **LangGraph agent** in `apps/api/app/agents/`.
4. Features live in **`specs/<slug>/`** with a PLAN + SUMMARY; read the relevant one first.
5. Read **`CLAUDE.md`** before touching backend code, and follow **`.claude/rules/`**.
