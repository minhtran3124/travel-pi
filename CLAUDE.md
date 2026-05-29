# CLAUDE.md

Guidance for Claude Code when working in this repo.

## What this is

A FastAPI **mock backend** for a Travel Planner agent — flight search, hotel
search, booking, places/attractions, local tips, and weather endpoints that
fake real travel APIs (no keys, no payments, no external calls — except
`/weather`, which proxies the free Open-Meteo API, and `/places/route` /
`/cities/route`, which optionally call OpenRouteService). The project began
from a `mock-api-spec.md` behavioural contract, but that file is no longer in
the repo: the code has since moved to a layered `app/` package and grown
endpoints beyond the original spec (places, tips, weather, cities, routing).
**`APIS.md` is the current endpoint reference, and the `tests/` suite is the
behavioural contract.**

## Run it

```bash
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

- Swagger UI: http://localhost:8000/docs · raw spec: `/openapi.json`
- Run the test suite: `.venv/bin/python -m pytest tests/ -v`
- The current endpoint set + behaviour lives in `APIS.md` and is pinned by the
  `tests/` suite — treat those as the contract (the older `mock-api-spec.md` is
  no longer in the repo).

## Layout

```
app/
  main.py          # app factory + CORS + global exception handler
  exceptions.py    # domain exceptions (AppError + subclasses), no FastAPI deps
  enums.py         # shared string enums (BookingType/Status/Sort, TripStatus)
  core/config.py   # settings (env vars, all have defaults)
  core/logging.py  # process-wide logging setup (dictConfig)
  core/lifespan.py # startup/shutdown hooks (creates the bookings + trips tables)
  core/geo.py      # shared haversine distance helper
  core/text.py     # shared fuzzy text matcher
  routers/         # one file per endpoint group, each tagged for Swagger
                   # (dashboard.py = server-rendered HTML pages, not part of the API)
  services/        # business logic
  crud/            # data-access layer (raw SQLite persistence, no logic)
  schemas/         # Pydantic request/response models (all extend AppBaseModel)
  templates/       # Jinja2 templates for the /dashboard/* HTML pages
  data/            # seed data (airlines, airports, cities, hotels, places, tips)
scripts/generate_data.py   # manual tool to generate more mock hotels
tests/             # pytest suite — 417 tests covering all API endpoints
  conftest.py      # shared TestClient fixture (isolated temp SQLite DB)
  test_meta.py
  test_airports.py
  test_cities.py
  test_flights.py
  test_hotels.py
  test_hotel_availability.py  # /hotels/availability + deterministic room model
  test_places.py
  test_routes.py   # /places/route — ORS path (monkeypatched) + offline estimate
  test_tips.py
  test_weather.py
  test_bookings.py
  test_errors.py   # consistent error-envelope across AppError/HTTP/validation
  test_trips.py    # /trips itinerary CRUD + idempotency
  test_destinations.py  # /destinations/{city}/overview composition (weather stubbed)
  test_workflows.py     # end-to-end agent journeys across endpoints
  test_text.py     # fuzzy text matcher (app/core/text.py)
  test_logging.py
```

## Key things to know

- **Flights are never stored.** `services/flight_service.py` seeds an RNG from
  an MD5 of `origin-destination-date`, so the same query always returns the
  same 5 flights. `find_flight_by_id()` reverses a flight ID back into search
  params and re-runs the generator. Changing the algorithm breaks existing IDs.
- **Bookings** are persisted to a SQLite file (`travel.db`) — the only
  mutable state. Everything else (seed data, generated flights) is
  in-memory / read-only. The booking domain is split two tiers:
  `services/booking_service.py` owns the rules (pricing, resolving the
  referenced flight/hotel, search/sort) and `crud/booking.py`
  (`BookingRepository`) owns the SQL. The table is created on startup via
  `core/lifespan.py`, not at import time. A `Booking` exposes two friendly
  computed fields (`schemas/booking.py`): `confirmation_code` (a 6-char
  PNR-style reference derived deterministically from the UUID) and `summary`
  (a one-line human/agent-readable description built from `details`).
  `GET /bookings/{id}` accepts the UUID or the confirmation code; both are
  also matched by the `q` search. `POST /bookings/{id}/cancel` is a soft
  state change — `status` becomes `cancelled`, the row is kept — and is
  idempotent.
- **Trips** are the second piece of mutable state — a planning aggregate
  (`schemas/trip.py`, `crud/trip.py`, `services/trip_service.py`,
  `routers/trips.py`) that groups a destination + dates with the bookings made
  for it (`booking_ids`) and an itinerary of places (`items`). Same two-tier
  split and SQLite patterns as bookings (WAL, partial-unique idempotency
  index, derived `confirmation_code` — here `TRP-XXXXXX`). `TripService`
  validates references on create/patch (unknown city/booking/place → 404, bad
  date range → 422) and takes the `BookingService` as a **parameter** (passed
  by the router) rather than the singleton, so it reads the same booking store
  the `/bookings` routes do — which is what keeps the test suite's isolated DB
  working. `GET /trips/{id}` returns a `TripDetail` that resolves
  `booking_ids` → full `bookings` and `items` → an `itinerary` with each
  `place` embedded, so an agent gets the whole plan in one call. `DELETE` is a
  soft, idempotent cancel (mirrors bookings).
- **`GET /destinations/{city}/overview`** is read-only composition over the
  place/tip/hotel/airport/weather services (`services/destination_service.py`)
  — one agent round-trip for top places + essential tips + live weather +
  hotel count + serving airports. Weather is **best-effort**: an upstream
  failure logs a warning and returns `weather: null` rather than failing the
  request. Tests stub `weather_service.get_weather` to stay network-free.
- **Error handling is layered.** Services raise domain exceptions from
  `app/exceptions.py` (`NotFoundError` → 404, `ConflictError` → 409,
  `UpstreamError` → 502); the
  global handler in `main.py` turns any `AppError` into an HTTP response, so
  the service layer never imports `HTTPException`. Routers may still raise
  `HTTPException` directly for request-validation errors (e.g. a bad date
  → 422). All three error sources — `AppError`, `HTTPException`, and
  `RequestValidationError` — go through handlers in `main.py` that emit one
  consistent JSON envelope (`{error, message, status_code, path, [errors]}`),
  so API consumers parse every failure the same way. That envelope is
  documented for Swagger as the `ErrorResponse` schema (`schemas/error.py`);
  routes declare their error codes via `responses=error_responses(...)` so
  the docs show the real shape instead of "Undocumented" / the stale
  `HTTPValidationError`.
- **Logging** is set up once in `core/logging.py` (`dictConfig`, called from
  `create_app`); level via `LOG_LEVEL` (default `INFO`). Modules use
  `logger = logging.getLogger(__name__)` — never `print()`. A middleware in
  `main.py` logs one line per request (method/path/status/duration) and is
  the single access log, so Uvicorn's own `uvicorn.access` logger is
  silenced. The `AppError` handler logs failures at `WARNING`.
- **Hotels** in `data/hotels.py` are the source of truth; add more with
  `python scripts/generate_data.py hotels --help`. Every city in
  `data/cities.py` has ≥3 hotels and ≥3 places. Hotel records store only
  `city` — `country` is derived from `cities.py` at import time.
- **Hotel search vs availability are two endpoints.** `GET /hotels/search`
  is dateless discovery ("any hotels in this city?"). `GET /hotels/availability`
  takes dates + party size and annotates each hotel with room availability.
  Availability is **generated, never stored** — same pattern as flights:
  `hotel_service.total_rooms` is seeded from the hotel ID, `available_rooms`
  from an MD5 of `hotel.id-check_in-check_out`, so a query is deterministic
  and a hotel can be fully booked (0 rooms) for some date ranges.
  `POST /hotels/book` re-checks availability and raises `ConflictError` (409)
  if the hotel can't take the rooms/party. Tests that aren't *about*
  availability pin `available_rooms` high via an autouse fixture.
- **`data/countries.py`** is the single source of truth for the country
  list. `airports.py`, `cities.py`, `places.py`, `hotels.py` and `tips.py`
  all validate their country values against it (or derive from it) at
  import time, so a typo or missing country fails loudly on startup.
- **Places** in `data/places.py` are read-only seed data, keyed per city.
- **Tips** in `data/tips.py` are two-tier: `COUNTRY_TIPS` (inherited by every
  city in that country) merged with `CITY_TIPS`. `tip_service` resolves a
  `city` → its country via `data/cities.py` and assigns positional IDs, so
  the tip lists must only be **appended to**, never reordered.
- **Weather** (`services/weather_service.py`) and **routing**
  (`services/routing_service.py`) are the two features that can make a real
  outbound call. Both are fully `async` — the route, the service functions,
  and `httpx.AsyncClient` — because they are the only real network I/O;
  everything else stays sync (in-memory, runs in FastAPI's threadpool). Tests
  monkeypatch each module's `_fetch_json` with an `async` fake.
  - Weather → Open-Meteo, no key, always live.
  - Routing (`GET /places/route` and `GET /cities/route`) → OpenRouteService
    for real road distance/duration per travel mode. ORS needs a free API
    key, so it degrades gracefully: with no `ORS_API_KEY` configured it falls
    back to an offline haversine estimate, and the response's `source` field
    says which (`"openrouteservice"` vs `"estimate"`).
    `Settings.routing_provider_enabled` is the check. Places and cities both
    carry `latitude`/`longitude` in the seed data. `routing_service` resolves
    a place ID or a city name to a `RouteEndpoint` (`kind` = `"place"` /
    `"city"`) and `get_route_between` does the rest. Results are cached
    in-process per endpoint pair — the seed data is fixed, so a route never
    changes — which protects the ORS free-tier quota; tests force the offline
    path and clear the cache via an autouse fixture. The shared haversine
    helper lives in `core/geo.py` (so `place_service`'s `/places/nearby` can
    use it without importing `routing_service`).
- **`ENVIRONMENT`** (`core/config.py`, default `development`) gates the
  interactive docs: when set to `production`, `main.py` disables `/docs`,
  `/redoc`, and `/openapi.json`. `Settings.is_production` is the check.
- Routes return typed `response_model`s so the FE can codegen TS types.

## Conventions

- Python 3.10+ type hints (`list[X]`, `X | None`), Pydantic v2.
- `datetime.now(timezone.utc)` for timestamps, never `utcnow()`.
- Lint/format with `ruff check app scripts` and `ruff format app scripts`.
- Keep it minimal. **Out of scope:** auth, an ORM/migration framework, and
  rate limiting. **In scope:** lightweight `limit`/`offset` pagination is
  *already implemented* (`schemas/pagination.py`'s `PagedResponse`, used by the
  list endpoints) — keep it as-is, don't expand it to cursor pagination. Also
  in scope: lightweight console logging (see the Logging note above); anything
  heavier (file rotation, JSON/structured logs, log shipping) is not.
- Booking requests carry only what's needed to issue the booking — never the
  price. `total_price` on a `Booking` is always computed server-side (flight
  fare from `flight.price`; hotel from `price_per_night × nights`).
- **Fuzzy name resolution is consistent across the API.** Every endpoint
  that takes a free-text city or country name resolves it fuzzily
  (typo/spacing/case tolerant) via `core/text.py`'s `best_match` /
  `fuzzy_filter` — `/cities?q=`, `/cities?country=`, `/cities/{city_name}`
  (case-insensitive), `/cities/route`, `/hotels/search?city=`,
  `/places/search?city=`, `/tips?city=`, `/tips?country=`. Services own
  their own resolver (`hotel_service.resolve_city`, `place_service.resolve_city`)
  against the city set that actually has data. Resource IDs (UUIDs, IATA
  codes) stay exact — they are machine identifiers, not names.
- Known intentional quirk: an unrecognised city/country returns `count: 0`,
  not a 404.

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
| ------ | ---------- |
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.
