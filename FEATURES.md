# FEATURES.md — Travel Planner (Travel-Pi)

Feature inventory of the AI travel-assistant product as it exists in the codebase today.
Derived from a code review of `apps/api` (FastAPI + LangGraph) and `apps/web` (Next.js),
not from roadmap documents. Anything documented but not built is called out under
[Known gaps](#12-known-gaps--caveats).

- **Repo:** pnpm workspaces + Turborepo monorepo — `apps/api` (Python/FastAPI), `apps/web` (Next.js 16 / React 19)
- **Surface counts:** ~65 public JSON endpoints, 19 server-rendered operator pages, 5 LangGraph sub-agents, 30 agent tools, 6 chat side-panel types, 182 backend test files
- **Reviewed at:** commit `6ecb00b`, branch `feat/web-protected-routes`

---

## 1. Product at a glance

A travel planner built **around** an AI agent rather than bolted onto one. Users plan trips,
explore places, manage bookings and track budget through a conventional UI; a streaming,
human-in-the-loop chat agent can do the same work on their behalf. The design principle the
codebase actually follows is *agent-native parity* — every REST capability has a matching agent
tool, and the agent's tool registry is the single source of truth for both the LangGraph agent
and the MCP server.

| Layer | What it is |
|---|---|
| Web app | Next.js App Router — trips, bookings, places + a floating chat co-pilot on every page |
| REST API | FastAPI — trips, itinerary, budget, expenses, bookings, flights, hotels, places, weather, air quality, currency, visa, tips, routing |
| Agent | LangGraph supervisor + 5 specialist sub-agents, SSE streaming, HITL approval, memory, RAG |
| MCP server | The same tool registry re-exposed to external MCP clients |
| Operator dashboard | Jinja2 pages for browsing inventory + editing per-agent LLM config and prompt versions |

---

## 2. AI travel agent

### 2.1 Graph architecture

`START → load_context → summarize → supervisor → route_tasks → {sub-agent | plan | parallel synthesis} → dispatch_next → reflection → END`

- **Supervisor** — a structured-output router that picks a `target_agent`, an optional
  `secondary_agent`, and an ordered multi-intent `plan`; it also detects the conversation
  `language` and extracts raw slots (destination, dates, party size, budget…).
  Slot *extraction* is LLM work; slot *normalization* is plain Python — the model never
  computes a final date or number.
- **Task ledger** — the supervisor builds an ordered task list (max 4 steps). `dispatch_next`
  is pure code with no LLM call: it drains queued flows one at a time, hides the previous
  sub-agent's prose from the next one while keeping tool results visible, and aborts the queue
  if the agent needs to ask the user something.
- **Parallel multi-intent** — more than one task fans out to `synthesis_worker`s via LangGraph
  `Send`, converging on a single `synthesize` node so REST and SSE emit one aligned final answer.
- **Reflection / revision loop** — a bounded LLM self-critique judge can send the answer back to
  its sub-agent once (`max_revisions` default 1); the SSE `reset` event tells the client to
  discard the superseded draft.
- **Clarification** — a `needs_clarification` tool sets `awaiting_user`, which short-circuits both
  the task queue and the reflection judge (a question isn't a reviewable answer).
- **Fault tolerance** — a `RetryPolicy` on every LLM node retries provider-transient failures
  (408/409/429/5xx, timeouts); tool errors are returned to the model as a self-correction hint
  rather than crashing the turn.

### 2.2 Sub-agents

| Sub-agent | Owns | Tier |
|---|---|---|
| `planner` | Trip planning — flight/hotel *search*, itinerary shaping | free |
| `concierge` | Destination knowledge — places, weather, air quality, tips, RAG | free |
| `journal` | Trip records + long-term memory (`get_trip_summary`, `recall_past_trips`) | free |
| `booking` | Booking and cancelling flights/hotels | **premium only** |
| `budget` | Expenses and budget tracking | free |

Free-tier users are routed away from `booking` with an upgrade message, and the
plan-approval path to booking is blocked too.

### 2.3 Human-in-the-loop booking

Anything routed to `booking` goes through a `plan` node that calls LangGraph `interrupt()`.
The stream emits an `interrupt` event, the UI renders an approval prompt, and the run resumes
with `Command(resume={"approved": bool})`. Rejection ends the turn with a cancellation message.
Cancel tools additionally require an explicit `confirm=True`.

### 2.4 Agent tools (30)

| Domain | Tools |
|---|---|
| Flights | `search_flights`, `book_flight` |
| Hotels | `browse_hotels` (undated), `search_hotels` (dated availability), `book_hotel` |
| Booking mgmt | `cancel_flight`, `cancel_hotel` |

`book_flight`, `book_hotel`, `cancel_flight` and `cancel_hotel` take the traveller's `user_id` via
`InjectedState("user_id")` (never model-supplied), so an agent-made booking is stamped with the
authenticated owner and a cancel of a booking owned by someone else reads as *not found* (#118,
review-A E004).
| Places | `search_places`, `nearby_places`, `resolve_place`, `parse_nl_query`, `list_place_categories` |
| Weather / climate | `get_weather`, `get_packing`, `get_air_quality`, `get_climate` |
| Routing | `get_route`, `get_city_route` |
| Trips | `create_trip`, `get_trip_summary`, `get_trip_budget`, `list_trip_places`, `add_place_to_trip`, `add_itinerary_item` |
| Budget | `add_expense`, `list_expenses`, `expense_summary` |
| Knowledge | `get_local_tips`, `search_travel_knowledge` (RAG) |
| Memory | `save_user_preference`, `get_user_preferences`, `recall_past_trips` |
| Utility | `resolve_date`, `needs_clarification` |

`book_*` and `cancel_*` carry a `destructiveHint`; write tools are flagged non-read-only.

### 2.5 Memory

- **Conversation persistence** — `AsyncPostgresSaver` checkpointer (opened once at lifespan);
  falls back to in-process `MemorySaver` outside Postgres, and fails fast in production if
  Postgres is configured but unreachable.
- **Summarization** — sliding-window compression once the message count crosses a threshold;
  tool-call/tool-result pairs are kept intact so long tool-using threads don't break.
- **Long-term store** — LangGraph `BaseStore` over Postgres + pgvector (semantic) or an indexed
  in-memory store, namespaced `("users", <user_id>, <kind>)`. Kinds: preferences, standing
  instructions, episodes (past trips).
- **Background extraction** — after the response is sent, a FastAPI background task extracts
  preferences / instructions / episodes from the last exchange. It is not part of the graph, so
  it never adds latency to the turn.
- **Personalization** — a profile (name, gender, travel group) is folded into the system prompt;
  gender is inferred, never asked directly.
- **Per-thread facts** — `trip_facts` is a merge-reducer slot memory that stays sticky across
  turns of a conversation.

### 2.6 Knowledge / RAG

Visa policies, local tips and country summaries are templated into natural-language prose and
chunked (400/50) into `PGVector` (collection `travel_knowledge`) or an in-memory vectorstore.
Retrieval is **hybrid**: semantic similarity + lexical token overlap fused with Reciprocal Rank
Fusion (k=60), with metadata filters pushed into the vector search. Re-ingest is idempotent via
stable document ids. Only `concierge` gets the retrieval tool.

### 2.7 Streaming (SSE)

`POST /agent/stream` emits typed events: `start`, `token`, `reset`, `subagent`, `tool_call`,
`tool_result`, `panel`, `interrupt`, `done` (carries suggestions, language, trip_id), `error`.

**Side panels** — tool artifacts are projected into typed structured panels through a registry:
`route`, `places`, `weather`, `air_quality`, `flights`, `hotels`. Panel content is localizable.

**Suggestion chips** — the backend emits locale-agnostic *keys* (e.g. `planner.addDay`), capped
at 3, chosen per current flow with a rule layer that can react to `trip_facts` / profile /
preferences. The web client resolves keys to localized labels; the backend never sends label text.

### 2.8 Language handling

The supervisor detects a sticky per-turn `language` (default `en`). Every sub-agent reply is
pinned to it, and panel data is localized (Vietnamese lookup tables plus an LLM translate seam).
This exists because the awaiting-user path skips reflection and used to leak language flips.

### 2.9 Identity

The assistant is branded **"Tin"**, defined in the `communication_style` prompt so all five
sub-agents inherit it, with a matching avatar and welcome state in the web UI.

---

## 3. Trips, itinerary and budget (REST)

**`/trips`** — fully owner-scoped; the service factory itself depends on the authenticated user,
so every query is filtered by `user_id` at the repository layer.

- Create / list (paginated) / detail / update / soft-delete a trip
- `POST /trips` supports an `Idempotency-Key` header, unique per `(user_id, key)`
- `POST /trips/estimate` — pure budget math, nothing persisted
- `GET /trips/{id}` returns computed `total_spent` plus coverage `gaps`
- `GET /trips/{id}/day-plan?date=` — ordered day plan with travel time (409 if the trip has no start date)
- `GET|POST /trips/{id}/budget` — per-category caps vs spent vs remaining (POST replaces caps)
- Itinerary items: create / update / delete, with a 409 when a linked booking would exceed a category cap
- Shortlist: attach / list / detach catalog or saved places on a trip (409 on duplicates)

**`/trips/{id}/expenses`** — expense ledger scoped through trip ownership. Create, list, summary,
detail, patch, soft-delete. `amount_usd` and `fx_rate` are computed at write time with Decimal
`ROUND_HALF_UP`, and roll into the trip's "spent" figure.

---

## 4. Travel inventory

| Area | Behavior |
|---|---|
| **Flights** | Deterministically generated from `(origin, destination, date)` — repeatable, never persisted until booked. Search with filters/sort, detail, book. |
| **Hotels** | DB-seeded catalog plus hash-seeded availability generation. List, search by city (undated), dated availability, detail, book. |
| **Places** | DB-seeded POI catalog: list, search, natural-language search (`POST`), cities, categories, nearby (haversine), place-to-place routing, detail. Plus user saved places with favorite/visited toggles. |
| **Bookings** | The one real mutable ledger: list with search/filter/sort/pagination, detail by UUID or confirmation code, cancel. Confirmation-code uniqueness enforced by migration. |
| **Cities / airports** | Seeded reference data; city list, city-to-city route (distance/time/mode), airport list with unique IATA codes. |

---

## 5. Destination intelligence

| Endpoint | Source |
|---|---|
| `/weather` current + forecast, `/weather/packing` gear suggestions | **Live Open-Meteo** (keyless) |
| `/air-quality` current AQI + forecast | **Live Open-Meteo Air-Quality** |
| `/destinations/{city}/climate` monthly normals | **Live Open-Meteo Archive**, cached by rounded lat/lon |
| `/places/route`, `/cities/route` | **OpenRouteService** when `ORS_API_KEY` is set, else offline haversine; the response's `source` field says which |
| `/currency/convert` | DB-seeded FX table (not live rates) |
| `/visa` entry guidance | DB-seeded, fuzzy-matched, returns `found: false` rather than 404 |
| `/tips` local tips | DB-seeded |

Free-text city/country lookups go through a shared fuzzy matcher that folds Vietnamese
diacritics (Đà Nẵng → Da Nang).

---

## 6. Web app (`apps/web`)

### 6.1 Routes

| Route | Purpose | Access |
|---|---|---|
| `/` | Redirects to `/trips` | public |
| `/trips` | Trip list dashboard — cards, welcome line, new-trip modal | **protected** |
| `/trips/[tripId]` | Trip detail: Itinerary / Budget / Expenses / Shortlist tabs | **protected** |
| `/bookings` | Bookings table + detail modal | **protected** |
| `/places` | Saved places browse drawer | **protected** |
| `/auth/login`, `/auth/sign-up` | Sign in / register | public |
| `/auth/callback`, `/auth/confirm`, `/auth/auth-code-error` | PKCE / magic-link / OTP handlers | public |

Protection lives in `src/middleware.ts` → `updateSession`: it refreshes the Supabase session and
gates the prefix list `['/trips','/bookings','/expenses','/places']`, redirecting to
`/auth/login?next=<path>`. Auth pages render without the app shell or chat widget.

### 6.2 Chat co-pilot

A floating launcher + panel present on every non-auth route, aware of the active trip from the
URL. Features: bespoke SSE parsing (not `EventSource`), streaming markdown via `streamdown` with a
token-reveal animation, typed side-panel drawer that auto-opens on new panels, suggestion chips,
an onboarding empty state, an interrupt/approval prompt for booking, agent avatar and settings
menu. On turn completion it invalidates the React Query caches for trips, items, budget and
expenses — because the agent can mutate the same data.

### 6.3 Auth

Supabase (`@supabase/ssr`). Email + password sign-in/sign-up, magic link via `signInWithOtp`,
sign-out. Post-login redirect targets are sanitized to same-origin paths (open-redirect guard).
OAuth buttons render but the action is deliberately stubbed — see [gaps](#12-known-gaps--caveats).

### 6.4 i18n, theming, stack

- **Locales:** `en` (default) and `vi`, cookie-based via `next-intl` with no URL prefixes; a
  `LocaleSwitcher` in the app shell writes the cookie and refreshes.
- **Theme:** `next-themes`, class-based dark variant, system default. Design tokens (`@theme inline`)
  cover accent (lime/coral), surfaces, ink levels, booking-status colors and topic colors — all
  theme-flippable.
- **Stack:** Next.js 16.2.9, React 19.2.4, Tailwind v4, a hand-rolled `components/ui` design system
  (not shadcn), `maplibre-gl`, TanStack Query v5, `openapi-fetch` against types generated from the
  FastAPI OpenAPI schema.

---

## 7. Auth, tiers and quotas

- **Verification** — Supabase JWT (RS256/ES256) verified against JWKS. `get_current_user` raises
  401; `get_current_user_optional` returns `None` so the agent can serve anonymous callers.
- **Ownership** — trips and expenses are scoped by `user_id` at the repository layer (migration
  `trips.user_id` was a destructive one). A conversation-claim endpoint reassigns an anonymous
  conversation once the user signs in.
- **Roles** — `PATCH /admin/users/{id}/tier` requires `app_metadata.role == "admin"` (403 otherwise).
- **Tiers** — free vs premium. Premium unlocks the `booking` sub-agent.
- **Quotas** — free tier gets a daily UTC-day agent-turn limit counted from `messages` rows;
  exceeding it raises `QuotaExceededError` → HTTP 429.
- **Rate-limit primitive** — a reusable DB-backed per-user limiter (`rate_limit_counters`) with
  prune-on-insert and SQLite `busy_timeout` handling. Built and merged; not yet wired onto every
  endpoint.

---

## 8. MCP server

`python -m app.mcp.server` builds a `FastMCP` server named `travel-pi` from the **same**
`ALL_TOOLS` registry the agent uses, so new agent tools are exposed automatically with no server
edit. Each tool carries `readOnlyHint` / `destructiveHint` annotations, and destructive tools get
" Cannot be undone." appended to their description. Tools requiring runtime injection (`store`,
`tool_call_id`) are skipped because an external MCP client can't supply them.

> **E004 caveat (review-A):** the four booking/cancel tools now take `user_id` via
> `InjectedState("user_id")`. Unlike `store` / `tool_call_id`, an `InjectedState` arg is **not**
> skipped by the server — `get_trip_summary` (also `InjectedState("user_id")`) is exposed too — so
> these tools **remain on the MCP surface**, now with a `user_id` parameter. E004's intent (drop
> them, since MCP has no auth) is therefore **not yet enforced**; achieving it needs an explicit
> filter in `app/mcp/server.py`. See `.harness-state/sdd/report-3.1.md`.

---

## 9. Operator dashboard

Server-rendered Jinja2 pages under `/dashboard`, excluded from OpenAPI (`include_in_schema=False`).

- **Inventory browsing** — flights (arrivals-board style) with route search and detail, hotels,
  places, tips, visa, weather, air quality, bookings ledger
- **Agent model config** — view and edit each LangGraph node's provider, model, temperature,
  max_tokens and enabled flag, persisted to the `agent_config` table
- **Prompt registry browser** — every prompt name with its active version, a per-version viewer,
  and a side-by-side line diff between any two versions
- **Command palette** — `_search.json` index of cities and airports

---

## 10. Configuration and operations

- **Per-agent LLM config** — `AgentConfigCache` holds `agent_name → override` process-wide, polls
  for changes and bumps a generation counter; the compiled graph is rebuilt when the generation
  changes, so a config edit takes effect **without a restart**. A `FAST_AGENTS` set
  (`summarize`, `journal`, `budget`, `reflection`, `extract_memory`, `date_resolution`) defaults
  to a cheaper fast-tier model.
- **Versioned prompts** — file-backed `prompts/<name>/vN.md` with an `active.yaml` pointer, no
  runtime DB. Active today: `communication_style` v8, `supervisor` v8, `concierge` v11,
  `planner` v11, `booking` v7, `journal` v2, `budget` v2, `reflection` v1,
  `memory_extraction` v5, `date_resolution` v1. Changes are tracked in `prompts/CHANGELOG.md`.
- **Reflection toggle** — driven by `agent_config.enabled`, resolved per request via
  `AgentContext.allow_reflection`; no graph rebuild needed.
- **Database** — SQLite locally, Postgres (pgvector image) in Docker, selected by `DATABASE_URL`.
  13 Alembic migrations.
- **Scripts** — `seed_agent_config`, `set_tier`, `seed_supabase_user`, `ingest_rag`,
  `generate_data`.
- **Docker** — `docker-compose.yml` (pgvector Postgres + API with `--reload`) and
  `docker-compose.test.yml` (tmpfs Postgres, `alembic upgrade head && pytest`).
- **Observability** — Langfuse integration exists but is optional and off by default.

---

## 11. Quality: tests and evaluation

**Backend** — 182 test files across 18 directories: `api/` (52), `agents/` (36), `tools/` (20),
`infra/` (8), `db/` (8), and smaller suites for core, services, memory, streaming, prompts, rag,
repositories, clients, scripts, mcp and an architecture-boundary test. `make test` runs on SQLite;
`make test-docker` reruns the same suite on Postgres for cross-engine parity.

**Frontend** — Vitest + Testing Library + MSW, co-located with components (chat panels, hooks,
queries, bookings). Playwright has two specs (`theme.spec.ts`, `trip-smoke.spec.ts`) and is
explicitly opt-in, not part of CI.

**CI** — GitHub Actions on pull request: an `api` job (pytest on SQLite) and a `web` job
(lint + vitest + `next build`).

**Agent evaluation** — two harnesses:
- `eval/run_eval.py` — offline, network-free routing/plan/task accuracy against JSON datasets
  (routing, intent, language, memory, multi_intent, suggestions, tools, format) with thresholds
  (routing ≥ 0.9, plan ≥ 0.8) and an injectable FakeLLM for CI.
- `eval/run_deepeval.py` — LLM-as-judge (DeepEval + G-Eval) over the compiled graph, skipping
  gracefully without a real API key. Metrics include response-language adherence, search-vs-booking
  intent, suggestion relevance, and a deterministic tool-correctness metric.
- `evalkit/` — a separate installable package holding portable metric ports, with an AST boundary
  gate so the eval binding stays decoupled.

---

## 12. Known gaps / caveats

These are real, verified in code — worth knowing before treating anything above as production-ready.

1. **`/dashboard/*` has no authentication.** The prompt browser and the agent-model-config editor
   are reachable without a JWT or admin role, unlike `/admin`. Fine for a local operator tool,
   not for a deployed environment.
2. **Bookings, saved places and the travel-inventory endpoints are unauthenticated and
   un-scoped.** `Booking` and `SavedPlace` have no `user_id` column, so any caller can read or
   cancel any booking by id. Ownership scoping exists only for trips and expenses.
3. **OAuth is UI-only.** `OAuthButtons` renders Google/GitHub, but the server action returns
   "not enabled yet — configure the provider in Supabase first."
4. **`/expenses` is gated in middleware but has no page yet.**
5. **Flights are synthetic.** No real flight provider; fares and schedules are hash-seeded and
   deterministic. Currency rates are seeded, not live. Weather, air quality, climate and routing
   *are* real.
6. **No PII redaction module.** The guardrail is a code comment on `trip_facts`
   ("never store PII/secrets here"); a middleware guardrail exists only as an unmerged spec.
7. **E2E coverage is thin** — two Playwright specs, not run in CI.
8. **The rate-limit primitive isn't fully wired.** It is built and tested; only the agent-turn
   daily quota is enforced today.
9. **The operator dashboard is undocumented** in `PRODUCT.md` / `DESIGN.md` — it exists only in code.

---

## 13. Where to look

| Feature area | Entry point |
|---|---|
| Agent graph | `apps/api/app/agents/graph.py`, `supervisor.py`, `nodes.py` |
| Sub-agents | `apps/api/app/agents/subagents/`, built by `_base.py` |
| Tools | `apps/api/app/tools/registry.py` |
| Prompts | `apps/api/app/prompts/` + `active.yaml` |
| Memory | `apps/api/app/memory/` |
| RAG | `apps/api/app/rag/` |
| SSE + panels | `apps/api/app/streaming/` |
| REST | `apps/api/app/routers/` |
| MCP | `apps/api/app/mcp/server.py` |
| Operator UI | `apps/api/app/routers/dashboard*.py`, `app/templates/` |
| Web routes | `apps/web/src/app/` |
| Chat UI | `apps/web/src/components/chat/` |
| Route protection | `apps/web/src/middleware.ts` |
| Eval | `apps/api/eval/`, `apps/api/evalkit/` |
