# Travel Planner Mock API

A fake travel-booking backend — flight search, hotel search, and booking
endpoints — so the frontend can build against a real API during development.
**No API keys, no payments, no real data.**

You don't need to know Python. Just follow the steps below.

## Start the server

There are three ways to run the project. **(a)** is the simplest (no Docker);
**(b)** runs the same app against a real Postgres database in Docker; **(c)**
runs the test suite against isolated Postgres for cross-engine parity.

### (a) Local, on SQLite (zero-config)

You need **Python 3.10 or newer** and **[uv](https://docs.astral.sh/uv/)**
(a fast Python package manager). To install uv:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # Windows: see the uv docs
```

Then, from the project folder:

```bash
make install        # uv venv && uv pip install -r requirements.txt
make dev            # uvicorn app.main:app --reload --port 8000
```

(If you prefer not to use `make`, run the underlying commands shown in the
comments above, activating the venv with `source .venv/bin/activate` first.)

When you see `Application startup complete`, it's running at
**http://localhost:8000** (Swagger at **/docs**). Keep this terminal open.
Press `Ctrl+C` to stop. Data is stored in a local `travel.db` SQLite file,
created automatically.

Run the test suite (**617 tests**, on SQLite):

```bash
make test           # .venv/bin/python -m pytest tests/ -q
```

### (b) Docker + Postgres

Runs the app and a Postgres database in containers:

```bash
make up             # docker compose up --build -d
make logs           # tail the container logs
make down           # stop the stack
```

The app is at **http://localhost:8000** (Swagger at **/docs**); Postgres runs
in its own container. **Migrations run automatically** on container start —
the entrypoint runs `alembic upgrade head` before the app boots, so the schema
is always up to date.

### (c) Tests on isolated Postgres

Run the full suite against a throwaway Postgres database (cross-engine parity —
the same **617 tests** pass on both SQLite and Postgres):

```bash
make test-docker
```

### Database configuration

The persistence backend is selected by the **`DATABASE_URL`** environment
variable:

- **Default** (local and tests): `sqlite:///travel.db`
- **Docker**: the compose files inject
  `postgresql+psycopg://travel:travel@db:5432/travel`

Schema is owned by **Alembic** on Postgres. Apply migrations against whatever
`DATABASE_URL` points at with:

```bash
make migrate        # .venv/bin/alembic upgrade head
```

In Docker this runs automatically via the entrypoint (see above).

## Use it

- **Flight board:** open **http://localhost:8000/dashboard/flights** — an
  airport-style arrivals/departures board (pick airport, date, and
  arrivals/departures). There's also a "search by route" page and a
  per-flight detail page. HTML for humans, not the API client.
- **Try endpoints in the browser:** open **http://localhost:8000/docs** — an
  interactive page to call every endpoint and see the responses.
- **Full endpoint reference:** see **[APIS.md](./APIS.md)**. Highlights: `/flights/search`, `/hotels/availability`, `/places/search`, `/tips`, `/weather`, `GET /air-quality` (live US-AQI + pollutants + short forecast via Open-Meteo, also at `/dashboard/air-quality`), `GET /destinations/climate` (monthly climate normals + best-time guidance), `GET /destinations/{city}/overview` (one-call city briefing: weather + places + tips + hotel summary), `GET /currency/convert` (mock-FX currency conversion), `GET /visa` (general visa / entry requirements for a city or country), `/trips` (save & edit a freeform day-by-day itinerary — full CRUD with per-item endpoints), and `POST /trips/estimate` (server-side trip budget breakdown + per-person total; calculation only, nothing stored).
- **Generate TypeScript types** (re-run whenever the API changes):

  ```bash
  npx openapi-typescript http://localhost:8000/openapi.json -o ./types/api.ts
  ```

## Good to know

- **Flights are generated on the fly.** The same `origin + destination + date`
  always returns the **same 5 flights**, so you can show a flight, leave, and
  fetch it again by ID. A different date gives different flights.
- **Hotels are a fixed list** of 51 hotels across 18 cities in Southeast Asia.
- **Bookings and trips are saved** to a database, so they survive server
  restarts. Locally that's a SQLite file (`travel.db`, created automatically);
  in Docker it's Postgres — the backend is chosen by `DATABASE_URL` (see above).
  These are the mutable state — a **trip** (`/trips`) is a freeform, day-by-day
  itinerary with full CRUD plus per-item endpoints.
- **CORS is fully open**, so you can call the API from `localhost:3000` (or
  anywhere) without errors.
- **The `/docs` page is for local use.** It stays on in development; setting
  `ENVIRONMENT=production` in `.env` turns it (and `/openapi.json`) off.

## Project layout

```
travel-pi/
├── app/
│   ├── main.py            # App setup + CORS + error handling
│   ├── core/              # Settings + startup/shutdown hooks
│   ├── routers/           # One file per endpoint group (+ dashboard.py = HTML pages)
│   ├── services/          # Business logic (flight gen, bookings, ...)
│   ├── crud/              # Data-access layer (SQLAlchemy ORM; SQLite or Postgres)
│   ├── schemas/           # Request/response shapes
│   ├── templates/         # Jinja2 HTML templates for the web pages
│   └── data/              # Seed data (airlines, airports, hotels)
├── tests/                 # pytest suite covering all API endpoints
├── scripts/generate_data.py   # Generate more mock hotels
├── requirements.txt
└── .env.example           # Optional config — copy to .env to override
```

### Adding more mock hotels

```bash
python scripts/generate_data.py hotels --city "Da Nang" --count 3
```

It prints ready-to-paste records — copy them into `app/data/hotels.py`.
Run `python scripts/generate_data.py hotels --help` for all options.
