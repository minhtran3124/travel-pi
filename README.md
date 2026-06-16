# Travel Planner Mock API

A fake travel-booking backend — flight search, hotel search, and booking
endpoints — so the frontend can build against a real API during development.
**No API keys, no payments, no real data.**

You don't need to know Python. Just follow the steps below.

## Start the server

You need **Python 3.10 or newer** and **[uv](https://docs.astral.sh/uv/)**
(a fast Python package manager). To install uv:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # Windows: see the uv docs
```

Then, from the project folder, run these commands one by one:

```bash
uv venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
uv pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

When you see `Application startup complete`, it's running at
**http://localhost:8000**. Keep this terminal open. Press `Ctrl+C` to stop.

## Use it

- **Flight board:** open **http://localhost:8000/dashboard/flights** — an
  airport-style arrivals/departures board (pick airport, date, and
  arrivals/departures). There's also a "search by route" page and a
  per-flight detail page. HTML for humans, not the API client.
- **Try endpoints in the browser:** open **http://localhost:8000/docs** — an
  interactive page to call every endpoint and see the responses.
- **Full endpoint reference:** see **[APIS.md](./APIS.md)**. Highlights: `/flights/search`, `/hotels/availability`, `/places/search`, `/tips`, `/weather`, `GET /air-quality` (live US-AQI + pollutants + short forecast via Open-Meteo, also at `/dashboard/air-quality`), `GET /destinations/climate` (monthly climate normals + best-time guidance), `GET /destinations/{city}/overview` (one-call city briefing: weather + places + tips + hotel summary), and `GET /currency/convert` (mock-FX currency conversion).
- **Generate TypeScript types** (re-run whenever the API changes):

  ```bash
  npx openapi-typescript http://localhost:8000/openapi.json -o ./types/api.ts
  ```

## Good to know

- **Flights are generated on the fly.** The same `origin + destination + date`
  always returns the **same 5 flights**, so you can show a flight, leave, and
  fetch it again by ID. A different date gives different flights.
- **Hotels are a fixed list** of 51 hotels across 18 cities in Southeast Asia.
- **Bookings are saved** to a local SQLite file (`travel.db`, created
  automatically), so they survive server restarts.
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
│   ├── crud/              # Data-access layer (SQLite persistence)
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
