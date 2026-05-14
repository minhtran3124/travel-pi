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
  routers/         # one file per endpoint group, each tagged for Swagger
                   # (dashboard.py = server-rendered HTML pages, not part of the API)
  services/        # business logic
  crud/            # data-access layer (raw SQLite persistence, no logic)
  schemas/         # Pydantic request/response models (all extend AppBaseModel)
  templates/       # Jinja2 templates for the /dashboard/* HTML pages
  data/            # seed data (airlines, airports, cities, hotels, places, tips)
scripts/generate_data.py   # manual tool to generate more mock hotels
tests/             # pytest suite — 213 tests covering all API endpoints
  conftest.py      # shared TestClient fixture (isolated temp SQLite DB)
  test_meta.py
  test_airports.py
  test_cities.py
  test_flights.py
  test_hotels.py
  test_places.py
  test_tips.py
  test_weather.py
  test_bookings.py
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
  `core/lifespan.py`, not at import time.
- **Error handling is layered.** Services raise domain exceptions from
  `app/exceptions.py` (`NotFoundError` → 404, `UpstreamError` → 502); the
  global handler in `main.py` turns any `AppError` into an HTTP response, so
  the service layer never imports `HTTPException`. Routers may still raise
  `HTTPException` directly for request-validation errors (e.g. a bad date
  → 422).
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
- **`data/countries.py`** is the single source of truth for the country
  list. `airports.py`, `cities.py`, `places.py`, `hotels.py` and `tips.py`
  all validate their country values against it (or derive from it) at
  import time, so a typo or missing country fails loudly on startup.
- **Places** in `data/places.py` are read-only seed data, keyed per city.
- **Tips** in `data/tips.py` are two-tier: `COUNTRY_TIPS` (inherited by every
  city in that country) merged with `CITY_TIPS`. `tip_service` resolves a
  `city` → its country via `data/cities.py` and assigns positional IDs, so
  the tip lists must only be **appended to**, never reordered.
- **Weather** (`services/weather_service.py`) is the one router making a real
  outbound call (Open-Meteo, no key). It is fully `async` — the route, the
  service functions, and `httpx.AsyncClient` — because it is the only real
  network I/O; everything else stays sync (in-memory, runs in FastAPI's
  threadpool). Tests monkeypatch `_fetch_json` with an `async` fake.
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
- Known intentional quirks: `FlightBookingRequest.total_price` is
  client-supplied; hotel city match is case-insensitive but exact-string;
  unknown cities return `count: 0`, not 404.
