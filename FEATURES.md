# FEATURES.md — Travel Planner (Travel-Pi)

Feature inventory of the AI travel-assistant product as it exists in the codebase today.
Derived from a code review of `apps/api` (FastAPI + LangGraph) and `apps/web` (Next.js),
not from roadmap documents. Anything documented but not built is called out under
[Known gaps](#12-known-gaps--caveats).

- **Repo:** pnpm workspaces + Turborepo monorepo — `apps/api` (Python/FastAPI), `apps/web` (Next.js 16 / React 19)
- **Surface counts:** ~65 public JSON endpoints, 19 server-rendered operator pages, 5 LangGraph sub-agents, 37 registry agent tools, 6 chat side-panel types, 283 backend test files
- **Reviewed at:** commit `80575565` (`main`)

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

`START → load_context → summarize → supervisor → route_tasks → {single sub-agent → reflection | plan (booking HITL) → booking → reflection | parallel Send(synthesis_worker) × N → synthesize → reflection} → END`

- **Supervisor** — a structured-output router that picks a `target_agent`, an optional
  `secondary_agent`, and a `plan` of **additional independent** specialists (slices that don't
  depend on the primary's result); it also detects the conversation `language` and extracts raw
  slots (destination, dates, party size, budget…). Slot *extraction* is LLM work; slot
  *normalization* is plain Python — the model never computes a final date or number.
- **Parallel task list** — the supervisor builds a `tasks` list deduplicated by agent (primary
  first, max 4). `route_tasks` is pure code with no LLM call: one task routes to a single specialist,
  `booking` detours through the HITL `plan` node, and two or more tasks fan out to parallel
  `synthesis_worker`s via LangGraph `Send`, converging on a single `synthesize` node so REST and SSE
  emit one aligned final answer. There is no ordered sequential ledger and no `dispatch_next`.
- **Dependent chains → one specialist** — a chain whose steps all live in one specialist's toolset
  (flights → hotel → places → weather → itinerary are all planner-owned) routes to that single
  specialist; its own ReAct loop is the sequential executor and sees its own tool results, staying
  within `agent_recursion_limit` (25).
- **Reflection / revision loop** — a bounded LLM self-critique judge can send the answer back to
  its sub-agent once (`max_revisions` default 1); the SSE `reset` event tells the client to
  discard the superseded draft.
- **Clarification** — a `needs_clarification` tool sets `awaiting_user`, which makes reflection end
  the turn early (a question isn't a reviewable answer).
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

### 2.4 Agent tools (37 in `ALL_TOOLS`, plus `needs_clarification` given to every sub-agent)

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
| Trips | `create_trip`, `list_trips`, `get_trip_summary`, `get_trip_budget`, `set_trip_budget`, `estimate_trip_budget`, `list_trip_places`, `add_place_to_trip`, `add_itinerary_item` |
| Budget | `add_expense`, `list_expenses`, `expense_summary` |
| Knowledge | `get_local_tips`, `get_visa`, `search_travel_knowledge` (RAG) |
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
  instructions, episodes (past trips). A deterministic **poisoning guard** (`memory/guard.py`,
  key allowlist + length cap + EN/VI blocklist, no LLM) stands between the extractor/tools and the
  store, on both the write and read paths, so a "from now on always…" injection can't become a
  permanent directive.
- **Fact age + token pressure** — remembered facts are surfaced with an age marker, and the
  conversation summarizer compresses history under token pressure (not just a message-count
  threshold). Store reads page through everything (no silent limit at the call sites).
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
- **Ownership** — trips, expenses, bookings and saved places are scoped by `user_id` at the
  repository layer (a foreign id reads as a 404, never a 403); the `trips.user_id` migration was a
  destructive one. A conversation-claim endpoint reassigns an anonymous conversation once the user
  signs in.
- **Roles** — `PATCH /admin/users/{id}/tier` requires `app_metadata.role == "admin"` (403 otherwise).
- **Tiers** — free vs premium. Premium unlocks the `booking` sub-agent and the REST
  `POST /flights/book` / `POST /hotels/book` routes (`require_premium` → 403 otherwise).
- **Quotas** — free tier gets a daily UTC-day agent-turn limit counted from `messages` rows;
  exceeding it raises `QuotaExceededError` → HTTP 429.
- **Rate-limit primitive** — a reusable DB-backed per-user limiter (`rate_limit_counters`) with
  prune-on-insert and SQLite `busy_timeout` handling. Built and merged; not yet wired onto every
  endpoint.

---

## 8. MCP server

`build_mcp_server()` (`app/mcp/server.py`) builds a `FastMCP` server named `travel-pi` from the
**same** `ALL_TOOLS` registry the agent uses, so new agent tools are exposed automatically with no
server edit. Each tool carries `readOnlyHint` / `destructiveHint` annotations, and destructive tools
get " Cannot be undone." appended to their description.

Three exclusion rules keep the unauthenticated surface safe:

- Tools needing a runtime-injected `store` or `tool_call_id` are skipped — an external MCP client
  can supply neither.
- The four **destructive** tools (`book_flight`, `book_hotel`, `cancel_flight`, `cancel_hotel`) are
  withheld, because MCP can't provide the authenticated owner, HITL approval or premium gate they
  require; booking and cancellation stay on the in-agent path.
- `list_trips` is excluded **by name** (`_MCP_EXCLUDED_BY_NAME`): its injected `user_id` would become
  a caller-supplied argument that alone could enumerate a user's trips. Other trip-scoped tools
  survive because they need a `trip_id` the caller cannot guess.

What remains is the read-only search/lookup set. `tests/mcp/` pins that destructive and clarification
tools stay off the server.

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
  runtime DB. Active today: `communication_style` v9, `supervisor` v13, `concierge` v13,
  `planner` v16, `booking` v10, `journal` v3, `budget` v3, `reflection` v1,
  `memory_extraction` v6, `date_resolution` v1. Changes are tracked in `prompts/CHANGELOG.md`.
- **Reflection toggle** — driven by `agent_config.enabled`, resolved per request via
  `AgentContext.allow_reflection`; no graph rebuild needed.
- **Database** — SQLite for the config default and the unit-test suite; Postgres (pgvector image)
  in Docker for dev, selected by `DATABASE_URL`. 18 Alembic migrations.
- **Scripts** — `seed_agent_config`, `set_tier`, `seed_supabase_user`, `ingest_rag`,
  `generate_data`.
- **Docker** — `docker-compose.yml` (pgvector Postgres + API with `--reload`) and
  `docker-compose.test.yml` (tmpfs Postgres, `alembic upgrade head && pytest`).
- **Observability** — Langfuse integration exists but is optional and off by default.

---

## 11. Quality: tests and evaluation

**Backend** — 283 test files (~2,858 tests) spanning `api/`, `agents/`, `tools/`, `infra/`, `db/`,
and smaller suites for core, services, memory, streaming, prompts, rag, repositories, clients,
scripts, mcp and an architecture-boundary test. `make test` runs on SQLite; `make test-docker`
reruns the same suite on Postgres for cross-engine parity.

**Frontend** — Vitest + Testing Library + MSW, co-located with components (chat panels, hooks,
queries, bookings). Playwright has four specs (`theme`, `trip-smoke`, `booking-smoke`,
`chat-feedback`) under `apps/web/playwright/`, run in CI by the `web-e2e` job only when the E2E
secrets are configured (otherwise it skips green).

**CI** — GitHub Actions (`.github/workflows/`). On pull request (`ci.yml`): a `secrets` job
(gitleaks scan of the PR commits), an `api` job (pytest on SQLite, Python 3.12), a `web` job
(lint + vitest + `next build`, Node 24), and a `web-e2e` job (Playwright, gated on E2E secrets —
skips green when unset). `eval.yml` runs the keyless agent-eval smoke gate on agent/prompt/tool
paths. `state-on-merge.yml` marks a spec shipped and refreshes `specs/STATE.md` after a merge to
`main`.

**Agent evaluation** — a capability × scenario suite (`python -m eval`, `apps/api/eval/`), built on
the portable `evalkit/` engine (AST boundary gate keeps the binding decoupled). 84 goldens across
10 capabilities (18 tagged `suite=smoke`, 66 `full`), one JSON file per capability under
`eval/datasets/`. Three metric layers: deterministic (flow/tools/language/args-shape) and
trajectory checks are keyless; judged G-Eval rubrics plus a DB-Oracle fact-check need a real judge
key. `make eval-smoke` runs the keyless layers against the real agent; `make eval-full` runs the
judged matrix (k=3), and `make eval-compare`/`eval-check` gate a run against the committed
`eval/baselines/main.json`. The judged suite never runs on CI (decision E002) — see
`apps/api/eval/README.md`.

---

## 12. Known gaps / caveats

These are real, verified in code — worth knowing before treating anything above as production-ready.

1. **`/dashboard/*` uses optional HTTP Basic, not the JWT/admin system.** `require_dashboard_access`
   enforces HTTP Basic when `DASHBOARD_BASIC_USER`/`DASHBOARD_BASIC_PASSWORD` are set; with neither
   set the pages are open in development but return 404 in production, so the dashboard is never
   reachable in production without credentials.
2. **Read-only travel-inventory endpoints are public.** Flight/hotel search, the places catalog and
   the destination-intelligence reads take no auth — they expose only synthetic or reference data.
   Bookings and saved places, by contrast, carry a non-null `user_id` and are owner-scoped (a
   foreign id reads as a 404), and the `POST` book routes are premium-gated.
3. **OAuth is UI-only.** `OAuthButtons` renders Google/GitHub, but the server action returns
   "not enabled yet — configure the provider in Supabase first."
4. **`/expenses` is gated in middleware but has no page yet.**
5. **Flights are synthetic.** No real flight provider; fares and schedules are hash-seeded and
   deterministic. Currency rates are seeded, not live. Weather, air quality, climate and routing
   *are* real.
6. **No PII redaction module.** The guardrail is a code comment on `trip_facts`
   ("never store PII/secrets here"); a middleware guardrail exists only as an unmerged spec.
7. **E2E coverage is thin** — four Playwright specs, and CI's `web-e2e` job only runs when the
   E2E secrets are configured (skips green otherwise).
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
