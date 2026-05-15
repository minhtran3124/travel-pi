# CLAUDE.md

Guidance for Claude Code when working in this repo.

## What this is

A FastAPI **mock backend** for a Travel Planner agent — flight search, hotel
search, booking, places/attractions, local tips, and weather endpoints that
fake real travel APIs (no keys, no payments, no external calls — except
`/weather`, which proxies the free Open-Meteo API). `mock-api-spec.md`
describes the original behavioral contract; the structure has since moved to
a layered `app/` package and grown endpoints beyond the original spec
(places, tips, weather, cities), so the spec is out of date on layout/config
and no longer lists every endpoint — see `APIS.md` for the current set.

## Run it

```bash
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

- Swagger UI: http://localhost:8000/docs · raw spec: `/openapi.json`
- Run the test suite: `.venv/bin/python -m pytest tests/ -v`
- Verify behaviour changes against the acceptance criteria in `mock-api-spec.md` §9.

## Layout

```
app/
  main.py          # app factory + CORS + global exception handler
  exceptions.py    # domain exceptions (AppError + subclasses), no FastAPI deps
  enums.py         # shared string enums (BookingType, BookingStatus, BookingSort)
  core/config.py   # settings (env vars, all have defaults)
  core/logging.py  # process-wide logging setup (dictConfig)
  core/lifespan.py # startup/shutdown hooks (creates the bookings table)
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
tests/             # pytest suite — 336 tests covering all API endpoints
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
- Keep it minimal — no auth, DB/ORM, pagination, or rate limiting (see the
  out-of-scope list in `mock-api-spec.md` §1). Lightweight console logging
  *is* in scope (see the Logging note above); anything heavier (file
  rotation, JSON/structured logs, log shipping) is not.
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
