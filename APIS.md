# API Reference

Base URL: `http://localhost:8000`

> **Interactive docs**: open **http://localhost:8000/docs** to call every
> endpoint directly from the browser. This file is the quick text reference
> with curl examples.

## All endpoints

| Method | Path | What it does |
|--------|------|--------------|
| GET | `/` | Service info + endpoint list |
| GET | `/airports` | All supported airports |
| GET | `/cities` | All cities that have hotel data |
| GET | `/cities/route` | Route between two cities — distance, time, best travel mode |
| GET | `/cities/{city_name}` | Get one city by name (case-insensitive) |
| GET | `/flights/search` | Search flights (one-way or round-trip) |
| GET | `/flights/{flight_id}` | Get one flight by UUID |
| POST | `/flights/book` | Book a flight |
| GET | `/hotels` | List all hotels |
| GET | `/hotels/search` | Browse hotels in a city (no dates) |
| GET | `/hotels/availability` | Check room availability for dates + party size |
| GET | `/hotels/{hotel_id}` | Get one hotel by UUID |
| POST | `/hotels/book` | Book a hotel (availability-checked) |
| GET | `/places` | List all places / attractions |
| GET | `/places/search` | Search places by city + filters |
| GET | `/places/cities` | List all cities that have places |
| GET | `/places/categories` | List all place categories |
| GET | `/places/nearby` | Find places near another place |
| GET | `/places/route` | Route between two places — distance, time, best travel mode |
| GET | `/places/{place_id}` | Get one place by ID |
| GET | `/tips` | Local tips for a city or country |
| GET | `/visa` | Visa / entry requirements for a city or country |
| GET | `/weather` | Current weather + short forecast for a city |
| GET | `/air-quality` | Current US-AQI + pollutants + short max-AQI forecast for a city |
| GET | `/destinations/climate` | Monthly climate normals (temp, rain, comfort) + best-time guidance for a city |
| GET | `/destinations/{city}/overview` | Aggregated city overview — weather, top places, essential tips, hotel summary |
| GET | `/currency/convert` | Convert an amount between currencies (mock FX rates) |
| GET | `/bookings` | List bookings (search / filter / sort) |
| GET | `/bookings/{booking_id}` | Look up a booking by UUID or confirmation code |
| POST | `/bookings/{booking_id}/cancel` | Cancel a booking |
| POST | `/trips` | Create a trip itinerary (with optional items) |
| POST | `/trips/estimate` | Estimate a trip budget (calculation only; no state) |
| GET | `/trips` | List trips (paginated) |
| GET | `/trips/{trip_id}` | Get one trip + its day-by-day items |
| PUT | `/trips/{trip_id}` | Replace a trip's top-level fields |
| DELETE | `/trips/{trip_id}` | Delete a trip and its items |
| POST | `/trips/{trip_id}/items` | Add an item to a trip |
| PUT | `/trips/{trip_id}/items/{item_id}` | Replace an item |
| DELETE | `/trips/{trip_id}/items/{item_id}` | Delete an item |

---

## Pagination

Every **list** endpoint shares one `limit`/`offset` paging contract and wraps
its rows in the same envelope:

| Param | Default | Notes |
|-------|---------|-------|
| `limit` | `20` | Page size, 1–500 |
| `offset` | `0` | Number of items to skip |

```json
{
  "total": 51,          // full match count, before paging
  "limit": 20,
  "offset": 0,
  "results": [ ... ]    // the current page
}
```

`total` is always the count of *all* matches; `results` is just the current
page. Applies to: `/airports`, `/cities`, `/hotels`, `/hotels/search`,
`/hotels/availability`, `/places`, `/places/search`, and `/bookings`. The
search endpoints add their `search`/echo fields alongside these. Non-list
responses (`/flights/search`, `/places/nearby`, `/tips`, the `/*/route`
endpoints) use their own `count`-based shapes and are **not** paginated.

---

## `GET /cities`

Returns every city that has at least one seeded hotel, with hotel count and
country. **Use this before calling `/hotels/search`** to validate a city name
— unknown cities return `count: 0`, not an error.

```bash
curl http://localhost:8000/cities
```

### Fuzzy search — `?q=`

Both `/cities` and `/airports` accept an optional `q` free-text param that
fuzzy-matches and **ranks results best-match-first** — tolerant of typos,
casing, and partial input. Ideal for an agent resolving a loosely-spelled
name before a precise search call.

```bash
curl "http://localhost:8000/cities?q=danang"     # → Da Nang
curl "http://localhost:8000/cities?q=Bangok"     # typo → Bangkok ranked first
curl "http://localhost:8000/airports?q=da nang"  # matches on code/name/city
```

`q` combines with the other filters (`country`, `has_hotels`). No match
yields `total: 0` rather than an error.

### Fuzzy city / country params everywhere

Beyond `?q=`, every endpoint that takes a free-text **city** or **country**
name resolves it fuzzily — typo/spacing/case tolerant, so `danang`,
`da nang`, and `DaNang` all resolve to `Da Nang`. This applies to:
`/cities?country=`, `/cities/{city_name}` (case-insensitive),
`/cities/route`, `/hotels/search?city=`, `/places/search?city=`,
`/tips?city=`, and `/tips?country=`. An unrecognised name still yields an
empty result (`count/total: 0`) rather than an error. Resource IDs (flight /
hotel / place UUIDs, IATA codes) stay **exact** — they are machine
identifiers, not names.

```json
{
  "total": 12,
  "limit": 20,
  "offset": 0,
  "results": [
    { "name": "Bali",       "country": "Indonesia",   "hotel_count": 5, "airport_codes": ["DPS"], "latitude": -8.41, "longitude": 115.19 },
    { "name": "Bangkok",    "country": "Thailand",    "hotel_count": 5, "airport_codes": ["BKK", "DMK"], "latitude": 13.76, "longitude": 100.50 },
    { "name": "Cebu",       "country": "Philippines", "hotel_count": 1, "airport_codes": ["CEB"], "latitude": 10.32, "longitude": 123.89 },
    { "name": "Chiang Mai", "country": "Thailand",    "hotel_count": 3, "airport_codes": ["CNX"], "latitude": 18.79, "longitude": 98.99 },
    { "name": "Da Nang",    "country": "Vietnam",     "hotel_count": 4, "airport_codes": ["DAD"], "latitude": 16.05, "longitude": 108.20 }
  ]
}
```

---

## `GET /flights/search` — one-way or round-trip

### Required params

| Param | Example | Notes |
|-------|---------|-------|
| `origin` | `DAD` | IATA 3-letter, case-insensitive |
| `destination` | `SGN` | IATA 3-letter, case-insensitive |
| `departure_date` | `2026-06-01` | YYYY-MM-DD — **422** if invalid |

### Optional params

| Param | Default | Notes |
|-------|---------|-------|
| `return_date` | — | YYYY-MM-DD. When set, response includes return-leg flights |
| `adults` | `1` | Echoed back; does not filter results |
| `airline` | — | IATA code, e.g. `VN`. No match → empty results |
| `max_price` | — | Only flights ≤ this price (USD) |
| `max_stops` | — | `0` = direct only |
| `sort` | `departure_asc` | `departure_asc/desc`, `price_asc/desc`, `duration_asc/desc` |

### One-way example

```bash
curl "http://localhost:8000/flights/search?origin=DAD&destination=SGN&departure_date=2026-06-01"
```

```json
{
  "count": 5,
  "search": {
    "origin": "DAD", "destination": "SGN",
    "departure_date": "2026-06-01", "adults": 1,
    "return_date": null, "airline": null,
    "max_price": null, "max_stops": null, "sort": "departure_asc"
  },
  "results": [ ... ],
  "return_count": null,
  "return_results": null
}
```

### Round-trip example

Add `return_date` to get both legs in one call.

```bash
curl "http://localhost:8000/flights/search?origin=DAD&destination=SGN&departure_date=2026-06-01&return_date=2026-06-08"
```

```json
{
  "count": 5,
  "search": { ..., "return_date": "2026-06-08" },
  "results": [
    { "id": "uuid", "origin": "DAD", "destination": "SGN", ... }
  ],
  "return_count": 5,
  "return_results": [
    { "id": "uuid", "origin": "SGN", "destination": "DAD", ... }
  ]
}
```

The same optional filters (`airline`, `max_price`, `max_stops`, `sort`) apply
to both legs independently. Same route+date always produces the same 5 flights
(deterministic). Filters narrow that set — `count` may be fewer than 5.

---

## `GET /flights/{flight_id}`

```bash
curl http://localhost:8000/flights/<uuid>
```

Returns the flight object, or **404** if the UUID is unknown.

> **Note:** flight UUIDs are stable within a server session. Call
> `/flights/search` first to obtain a valid UUID, then fetch by ID.

---

## `POST /flights/book`

```bash
curl -X POST http://localhost:8000/flights/book \
  -H "Content-Type: application/json" \
  -d '{
    "flight_number": "VN123",
    "origin": "DAD",
    "destination": "SGN",
    "departure_date": "2026-06-01",
    "passenger_name": "Minh Tran",
    "passenger_email": "minh@example.com",
    "passenger_phone": "+84 901 234 567",
    "notes": "Outbound leg of Da Nang trip"
  }'
```

| Field | Required | Notes |
|-------|----------|-------|
| `flight_number` | ✓ | Carrier code + number, case-insensitive (`VN123` or `VN 123`) — from `/flights/search` |
| `origin` | ✓ | 3-letter IATA origin code, case-insensitive |
| `destination` | ✓ | 3-letter IATA destination code, case-insensitive |
| `departure_date` | ✓ | YYYY-MM-DD |
| `passenger_name` | ✓ | Full name as printed on the passenger's ID/passport |
| `passenger_email` | ✓ | Contact email for the itinerary / e-ticket |
| `passenger_phone` | ✓ | Contact phone for airline notifications (delays, gate) |
| `notes` | — | Free-text context the agent/user wants to attach |

A flight number alone isn't unique (the same code is reused across dates and
routes), so the booking is identified by `flight_number` **plus** the route
and date — together they pin a single flight from the search results. An
unmatched combination returns **404**.

The fare is **not** sent by the client — `total_price` on the resulting
booking is taken server-side from the selected flight (`flight.price`), so it
can't be tampered with.

Returns a `Booking` object — see [Booking object shape](#booking-object-shape).
The `id` is a UUID, but the response also carries a friendly
`confirmation_code` (6-char PNR-style) and a one-line `summary`; either the
UUID or the code can be passed to `GET /bookings/{id}`.

### Idempotency

Pass an optional `Idempotency-Key` header to make the booking POST
**replay-safe** — repeating the request with the same key returns the
original booking instead of creating a duplicate. Use a fresh key per
intended booking; reuse it on retries.

```bash
curl -X POST http://localhost:8000/flights/book \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: trip-danang-outbound-001" \
  -d '{ ... }'
```

---

## `GET /hotels`

```bash
curl http://localhost:8000/hotels
```

Returns all 51 seeded hotels, unfiltered.

---

## `GET /hotels/search` — browse hotels in a city (no dates)

Pure **discovery** — answers "are there any hotels in this city?" and lets
you filter on static attributes. No dates: to check whether rooms are
actually free for a stay, use [`/hotels/availability`](#get-hotelsavailability--check-room-availability).

### Required params

| Param | Example |
|-------|---------|
| `city` | `Da Nang` — fuzzy (typo/case tolerant); unknown city returns `total: 0` |

### Optional params

| Param | Example | Notes |
|-------|---------|-------|
| `min_stars` | `4` | Only hotels with star_rating ≥ this value (1–5) |
| `max_price` | `300` | Only hotels with price_per_night ≤ this (USD) |
| `amenities` | `Pool` | Required amenity. **Repeat the param for multiple.** All must match. |

```bash
curl "http://localhost:8000/hotels/search?city=Bangkok&min_stars=5&amenities=Pool&amenities=Spa"
```

```json
{
  "total": 2,
  "limit": 20,
  "offset": 0,
  "search": { "city": "Bangkok", "min_stars": 5, "max_price": null, "amenities": ["Pool", "Spa"] },
  "results": [ ... ]
}
```

---

## `GET /hotels/availability` — check room availability

Given dates and party size, returns every matching hotel **annotated with
availability**: whether it can take the booking, how many rooms are free,
per-room capacity, and the all-in price for the stay.

Availability is *generated deterministically* (hotel + date range → seeded
RNG), like flights — same query always returns the same answer, and a hotel
can be fully booked (`available_rooms: 0`) for some date ranges.

### Required params

| Param | Example | Notes |
|-------|---------|-------|
| `city` | `Da Nang` | fuzzy; unknown city → `total: 0` |
| `check_in` | `2026-06-01` | YYYY-MM-DD — **422** if invalid |
| `check_out` | `2026-06-03` | YYYY-MM-DD |

### Optional params

| Param | Default | Notes |
|-------|---------|-------|
| `rooms` | `1` | Rooms needed |
| `adults` | `2` | Adults in the party |
| `children` | `0` | Children in the party |
| `available_only` | `false` | `true` drops hotels that can't take the booking |
| `min_stars`, `max_price`, `amenities` | — | same static filters as `/hotels/search` |

```bash
curl "http://localhost:8000/hotels/availability\
?city=Da%20Nang&check_in=2026-06-01&check_out=2026-06-03&rooms=1&adults=2"
```

```json
{
  "total": 4,
  "limit": 20,
  "offset": 0,
  "search": {
    "city": "Da Nang", "check_in": "2026-06-01", "check_out": "2026-06-03",
    "nights": 2, "rooms": 1, "adults": 2, "children": 0,
    "min_stars": null, "max_price": null, "amenities": null
  },
  "results": [
    {
      "...hotel fields...": "...",
      "available": true,
      "available_rooms": 56,
      "max_occupancy_per_room": 3,
      "nights": 2,
      "total_price": 900.0
    }
  ]
}
```

`available = available_rooms ≥ rooms` **and** the rooms can physically hold
the party (`max_occupancy_per_room × rooms ≥ adults + children`).
`total_price = price_per_night × nights × rooms`.

---

## `GET /hotels/{hotel_id}`

```bash
curl http://localhost:8000/hotels/<uuid>
```

Returns the hotel object, or **404**.

---

## `POST /hotels/book`

```bash
curl -X POST http://localhost:8000/hotels/book \
  -H "Content-Type: application/json" \
  -d '{
    "hotel_id": "<uuid from /hotels/search or /hotels/availability>",
    "check_in": "2026-06-01",
    "check_out": "2026-06-03",
    "rooms": 1,
    "adults": 2,
    "children": 0,
    "guest_name": "Minh Tran",
    "guest_email": "minh@example.com",
    "guest_phone": "+84 901 234 567",
    "notes": "Anniversary trip — request sea-view room"
  }'
```

| Field | Required | Notes |
|-------|----------|-------|
| `hotel_id` | ✓ | UUID from `/hotels`, `/hotels/search`, or `/hotels/availability` — **404** if invalid |
| `check_in` | ✓ | YYYY-MM-DD |
| `check_out` | ✓ | YYYY-MM-DD |
| `rooms` | — | Default 1 |
| `adults` | — | Default 2 |
| `children` | — | Default 0 |
| `guest_name` | ✓ | Full name of the lead guest, as on their ID |
| `guest_email` | ✓ | Contact email for the reservation |
| `guest_phone` | ✓ | Contact phone for the hotel (late arrival, changes) |
| `notes` | — | Free-text context the agent/user wants to attach |

The booking is **availability-checked**: if the hotel can't take the
requested rooms/party for those dates, you get **409 Conflict** (check
`/hotels/availability` first). `total_price` is computed server-side:
`price_per_night × nights × rooms`. The response `details` includes `nights`,
`rooms`, `adults`, `children`, and `price_per_night`.

Supports the same optional `Idempotency-Key` header as `POST /flights/book`
(see above) — a repeated key returns the original booking unchanged.

---

## `GET /destinations/climate` — monthly climate normals

Returns monthly climate normals for a city derived from ~3 years of
[Open-Meteo](https://open-meteo.com/) historical archive data (free, keyless).
Each month carries average high/low temperature, total precipitation,
rainy-day count, and a short comfort label. The response also includes
`best_months` (the most comfortable and driest months to visit, up to 3) and
a prose `summary` of the destination's climate.

`city` is fuzzy-matched (typo/case tolerant) — the same resolver used by
`/weather` and `/destinations/{city}/overview`. An unrecognised city returns
**404**. Unlike `/destinations/{city}/overview`, **502 is a real failure
here** — the endpoint does not degrade; if the Open-Meteo Archive API is
unavailable or returns malformed data the call fails with 502.

### Query params

| Param | Required | Default | Notes |
|-------|----------|---------|-------|
| `city` | ✓ | — | City name — fuzzy-matched. Unknown city → **404**. |
| `month` | — | (all twelve) | Integer 1–12. When set, returns only that month and `best_months` is `[]`. Out of range → **422**. |

```bash
curl "http://localhost:8000/destinations/climate?city=Da%20Nang"

# Single month only
curl "http://localhost:8000/destinations/climate?city=Bangkok&month=2"
```

```json
{
  "location": {
    "name": "Da Nang",
    "country": "Vietnam",
    "latitude": 16.05,
    "longitude": 108.20,
    "timezone": "Asia/Ho_Chi_Minh"
  },
  "based_on_years": [2022, 2023, 2024],
  "months": [
    {
      "month": 1,
      "name": "January",
      "avg_temp_max_c": 25.1,
      "avg_temp_min_c": 19.3,
      "avg_precip_mm": 83.4,
      "rainy_days": 12,
      "comfort": "mild, wet"
    },
    { "...": "11 more months" }
  ],
  "best_months": [2, 3, 4],
  "summary": "Da Nang is driest and most comfortable around February, March and April; October is wettest.",
  "attribution": "Weather data by Open-Meteo.com (CC BY 4.0)"
}
```

- `location` — resolved city coordinates and timezone (same `WeatherLocation` shape as `/weather`).
- `based_on_years` — the calendar years averaged to produce the normals (typically ~3 years).
- `months` — always in calendar order (January first). Contains one entry when `month` is specified.
- `best_months` — month numbers (1–12) scoring highest on comfort + dryness; up to 3 entries. Empty (`[]`) when `month` is specified.
- `comfort` — temperature band (`hot` / `warm` / `mild` / `cool`) + wetness (`wet` / `dry`), e.g. `"warm, dry"`.
- `summary` — server-generated one-liner naming the best months to visit and the wettest month.
- `attribution` — required Open-Meteo attribution; always present.

### Response codes

| Code | Condition |
|------|-----------|
| 200 | Success |
| 404 | City not found |
| 422 | `month` out of range (1–12) or `city` missing |
| 502 | Open-Meteo Archive API unavailable or returned malformed/empty data |

---

## `GET /destinations/{city}/overview` — aggregated city overview

Combines weather, top places, essential tips, and a hotel summary for a city
into **one response**, so an agent or dashboard can present a destination
briefing with a single call instead of four.

`{city}` is fuzzy-matched (typo/case tolerant) against the seed city list —
the same resolver used by `/weather`, `/places/search`, and `/tips`.
An unrecognised city returns **404**.

### Path param

| Param | Notes |
|-------|-------|
| `city` | City name — fuzzy-matched. Unknown city → **404**. |

### Query params

| Param | Default | Notes |
|-------|---------|-------|
| `include` | all four | Comma-separated subset of `weather,places,tips,hotels`. Omit to include everything. Unknown member → **422**. |
| `place_limit` | `5` | Max top places to return, 1–20. |
| `tip_limit` | `5` | Max essential tips to return, 1–20. |

### Degradation

If Open-Meteo is unavailable, `weather` is `null` and the rest of the
response is still returned with **200**. The endpoint never returns **502**
— weather failure is handled gracefully.

```bash
curl "http://localhost:8000/destinations/Da%20Nang/overview"

# Only weather + places, limit places to 3
curl "http://localhost:8000/destinations/Bangkok/overview?include=weather,places&place_limit=3"
```

```json
{
  "city": "Da Nang",
  "country": "Vietnam",
  "latitude": 16.05,
  "longitude": 108.20,
  "weather": {
    "city": "Da Nang",
    "current": { "temperature_c": 31.2, "condition": "Partly cloudy", "...": "..." },
    "forecast": [ "..." ]
  },
  "top_places": [
    { "id": "56f5b6d7-...", "name": "Dragon Bridge", "category": "landmark", "rating": 4.7, "...": "..." }
  ],
  "essential_tips": [
    { "id": "tip_city_danang_00", "category": "transport", "title": "Grab is the standard taxi app", "is_essential": true, "...": "..." }
  ],
  "hotel_summary": {
    "count": 4,
    "price_range_usd": { "min": 45.0, "max": 450.0 },
    "star_range": { "min": 3, "max": 5 },
    "sample": [
      { "id": "uuid", "name": "Novotel Da Nang Premier Han River", "star_rating": 5, "price_per_night": 130.0, "...": "..." }
    ]
  },
  "attribution": "Weather data by Open-Meteo.com (CC BY 4.0)"
}
```

- `top_places` — recommended places first, then sorted by rating, up to `place_limit`.
- `essential_tips` — only tips with `is_essential: true`, up to `tip_limit`.
- `hotel_summary` — `null` if `hotels` is not in `include`; otherwise `count` is the total hotel count for the city, `price_range_usd` and `star_range` are `null` if the city has no hotels, and `sample` contains up to 3 representative hotels.
- `weather` — `null` if `weather` is not in `include` or if Open-Meteo is unreachable.

### Response codes

| Code | Condition |
|------|-----------|
| 200 | Success (weather may be `null` on upstream outage) |
| 404 | City not found |
| 422 | Invalid query params (unknown `include` member, `place_limit`/`tip_limit` out of range) |

---

## `GET /currency/convert` — convert an amount between currencies

Every price in this API is quoted in USD; this endpoint converts an amount into
another currency so an agent can answer "how much is that in local money?".

**Rates are mock data, not live FX** — a static table with a `last_updated`
snapshot date. Currency codes are exact ISO 4217 identifiers (case-insensitive);
an unknown `from`/`to` returns **404**. An optional `country` is fuzzy-matched
and, when resolved, attaches its `local_currency` so the agent need not know it;
an unrecognised `country` is simply ignored (no error).

Supported codes: `USD`, `EUR`, `GBP`, `AUD`, plus every seed-country currency
(`VND`, `THB`, `SGD`, `MYR`, `IDR`, `PHP`, `KHR`, `LAK`, `MMK`, `BND`, `HKD`,
`KRW`, `JPY`).

### Query params

| Param | Required | Default | Notes |
|-------|----------|---------|-------|
| `from` | — | `USD` | Source ISO 4217 code, case-insensitive. Unknown → **404**. |
| `to` | ✓ | — | Target ISO 4217 code, case-insensitive. Unknown → **404**. |
| `amount` | — | `1.0` | Amount in the source currency. Must be `> 0` → else **422**. |
| `country` | — | — | Destination country (fuzzy). Resolved → adds `local_currency`; unknown → ignored. |

```bash
curl "http://localhost:8000/currency/convert?from=USD&to=VND&amount=100&country=Vietnam"
```

```json
{
  "from": "USD",
  "to": "VND",
  "rate": 25400.0,
  "amount": 100.0,
  "converted": 2540000.0,
  "last_updated": "2026-06-01",
  "local_currency": { "code": "VND", "name": "Vietnamese Dong" }
}
```

- `rate` — units of `to` per 1 unit of `from` (cross-rate via USD base).
- `converted` — `amount × rate`, rounded to 2 decimals.
- `last_updated` — snapshot date of the mock rates (this is **not** live data).
- `local_currency` — the `country`'s own currency, or `null` if no/unknown `country`.

### Response codes

| Code | Condition |
|------|-----------|
| 200 | Success |
| 404 | Unknown `from` or `to` currency code |
| 422 | `amount` ≤ 0, or `to` missing |

---

## `GET /bookings`

All params optional:

| Param | Values | Notes |
|-------|--------|-------|
| `q` | any string | Case-insensitive match on booking ID, confirmation code, customer name, or email |
| `type` | `flight` \| `hotel` | Other values ignored |
| `sort` | `created_desc` (default), `created_asc`, `price_desc`, `price_asc` | Unknown values fall back to `created_desc` |

```bash
# All hotel bookings, most expensive first
curl "http://localhost:8000/bookings?type=hotel&sort=price_desc"

# Search by customer name
curl "http://localhost:8000/bookings?q=minh"
```

---

## `GET /places/route` — route between two places

Given two place IDs, returns the straight-line distance, a per-mode breakdown
(walk / bike / car) of distance + duration, and the **recommended travel
mode** for that distance. Handy for an agent planning how to get between two
spots on an itinerary.

### Params

| Param | Required | Notes |
|-------|----------|-------|
| `origin` | ✓ | Place ID to start from (from `/places` or `/places/search`) |
| `destination` | ✓ | Place ID to travel to |

Returns **404** if either ID is unknown or the place has no coordinates,
and **502** if a configured routing provider is unreachable.

```bash
curl "http://localhost:8000/places/route\
?origin=56f5b6d7-f0e2-5867-a9dd-087a98cff34c\
&destination=26afc73a-6773-55c9-8e61-1f0fe75576e7"
```

```json
{
  "origin":      { "kind": "place", "id": "56f5b6d7-...", "name": "Dragon Bridge",    "latitude": 16.0607, "longitude": 108.2275 },
  "destination": { "kind": "place", "id": "26afc73a-...", "name": "Marble Mountains", "latitude": 15.9736, "longitude": 108.2625 },
  "straight_line_km": 10.38,
  "recommended_mode": "car",
  "legs": [
    { "mode": "walk", "profile": "foot-walking",    "distance_km": 13.49, "duration_minutes": 179.9 },
    { "mode": "bike", "profile": "cycling-regular", "distance_km": 13.49, "duration_minutes": 54.0 },
    { "mode": "car",  "profile": "driving-car",     "distance_km": 13.49, "duration_minutes": 23.1 }
  ],
  "source": "estimate",
  "attribution": "Offline straight-line estimate (set ORS_API_KEY for real road routing)"
}
```

### How distances are computed

- **Default (no config):** `source` is `"estimate"` — an offline straight-line
  (haversine) distance with a small detour factor, and a duration per mode
  from average travel speeds. Works with zero setup.
- **With `ORS_API_KEY` set:** `source` is `"openrouteservice"` — real road
  distance and duration per mode from [OpenRouteService](https://openrouteservice.org/)
  (free, no credit card). Set `ORS_API_KEY` in `.env` to enable it.

`recommended_mode` is picked from the straight-line distance: ≤1.5 km → `walk`,
≤8 km → `bike`, otherwise `car`. Results are cached per endpoint pair (the
seed data is fixed), which keeps repeat calls fast and protects the ORS quota.

---

## `GET /cities/route` — route between two cities

Same shape and behaviour as `/places/route`, but `origin`/`destination` are
**city names** instead of place IDs. The endpoint objects come back with
`"kind": "city"`. City coordinates are in the seed data, so this needs no
extra setup.

City names are matched **fuzzily** — the same typo/spacing-tolerant matcher
as `GET /cities?q=` — so `danang`, `da nang`, and `DaNang` all resolve to
`Da Nang`. No need to know the exact spelling.

```bash
curl "http://localhost:8000/cities/route?origin=danang&destination=hoi an"
```

Returns **404** if either city name is unknown, **502** if a configured
routing provider is unreachable.

---

## `GET /places/nearby` — places near a place

Given a place ID, returns other places within a radius, **nearest-first**,
each annotated with `distance_km`. Pure straight-line (haversine) over the
seed data — no external call. Useful for "what's near my hotel / this
attraction".

### Params

| Param | Required | Notes |
|-------|----------|-------|
| `place_id` | ✓ | The place to search around |
| `radius_km` | — | Search radius, 0–50 km (default 5) |
| `limit` | — | Max results, 1–50 (default 10) |
| `category` | — | Optional category filter, e.g. `restaurant` |

Returns **404** if `place_id` is unknown or has no coordinates. Nothing in
range → empty `results` (not a 404).

```bash
curl "http://localhost:8000/places/nearby\
?place_id=56f5b6d7-f0e2-5867-a9dd-087a98cff34c&radius_km=3&category=cafe"
```

```json
{
  "origin_place_id": "56f5b6d7-...",
  "radius_km": 3.0,
  "count": 2,
  "results": [
    { "id": "d3c94323-...", "name": "Faifoo Coffee", "category": "cafe", "distance_km": 1.26, "...": "..." }
  ]
}
```

Each entry is a full place object plus `distance_km`.

---

## `GET /tips` — local tips for a destination

Curated, practical advice for a destination — currency, transport, safety,
etiquette, food, best time to visit, etc. Data is two-tier: **country tips**
(inherited by every city in that country) merged with any **city-specific
tips**.

### Params

| Param | Required | Notes |
|-------|----------|-------|
| `city` | one of `city`/`country` | City name — fuzzy (typo/case tolerant). Resolves its own country, then merges country + city tips. |
| `country` | one of `city`/`country` | Country name — fuzzy (typo/case tolerant). |
| `category` | — | Filter: `transport`, `money`, `safety`, `culture`, `food`, `connectivity`, `health`, `etiquette`, `best_time`, `language`. Invalid → **422**. |
| `essential_only` | — | `true` returns only the must-know tips. |

Provide **either** `city` **or** `country` — neither → **422**. Unknown city
or country returns `count: 0` (not a 404).

```bash
curl "http://localhost:8000/tips?city=Hanoi"
curl "http://localhost:8000/tips?country=Thailand&category=safety"
curl "http://localhost:8000/tips?city=Bali&essential_only=true"
```

```json
{
  "city": "Hanoi",
  "country": "Vietnam",
  "count": 11,
  "summary": "Vietnam is rewarding and affordable, with superb food ...",
  "tips": [
    {
      "id": "tip_city_hanoi_00",
      "category": "transport",
      "scope": "city",
      "title": "Crossing the road: walk slow and steady",
      "content": "Traffic won't stop for you, but it will flow around you ...",
      "is_essential": true
    }
  ]
}
```

Each tip's `scope` is `"country"` or `"city"`. Use `is_essential` to surface
the must-know tips first in a compact itinerary.

---

## `GET /visa` — visa / entry guidance

General visa and entry requirements for a city or country — visa-free days,
visa-on-arrival and e-visa availability, and minimum passport validity.
Guidance is general and nationality-dependent; the response always carries a
`disclaimer` reminding the caller to verify with official sources before
travel.

### Params

| Param | Required | Default | Notes |
|-------|----------|---------|-------|
| `city` | one of `city`/`country` | — | City name — fuzzy (typo/case tolerant). Resolves the city's country automatically. |
| `country` | one of `city`/`country` | — | Country name — fuzzy (typo/case tolerant). |

Provide **either** `city` **or** `country` — neither → **422**. An unknown
city or country returns `found: false` with `entry: null` (not a 404).

```bash
curl "http://localhost:8000/visa?city=Da%20Nang"
curl "http://localhost:8000/visa?country=Vietnam"
```

```json
{
  "city": "Da Nang",
  "country": "Vietnam",
  "found": true,
  "entry": {
    "visa_free_days": 45,
    "visa_on_arrival": true,
    "e_visa": true,
    "passport_validity_months": 6,
    "summary": "Many nationalities get 45 days visa-free; others can apply for a 90-day e-visa online before arrival."
  },
  "disclaimer": "General guidance only and dependent on your nationality — always confirm current requirements with the destination's official immigration authority or embassy before you travel."
}
```

- `entry.visa_free_days` — `0` when a visa is generally required (not just for some nationalities).
- `entry.passport_validity_months` — `0` means "valid for the duration of stay" (no fixed minimum beyond the trip length).
- `entry` — `null` when `found` is `false` (unrecognised city or country).
- `disclaimer` — always present; surface it to the end user.

### Response codes

| Code | Condition |
|------|-----------|
| 200 | Success — including unknown location (`found: false`, `entry: null`) |
| 422 | Neither `city` nor `country` provided |

---

## `GET /weather` — current conditions + short forecast

Resolves a city name to coordinates and returns live current weather plus a
short forecast from [Open-Meteo](https://open-meteo.com/) (free, no API key).
This is one of the few endpoints that makes a real outbound call.

### Params

| Param | Required | Default | Notes |
|-------|----------|---------|-------|
| `city` | ✓ | — | City name to look up, e.g. `Da Nang`. |
| `days` | — | `3` | Number of forecast days, 1–16. Out of range → **422**. |

Returns **404** if the city name cannot be geocoded, and **502** if the
upstream Open-Meteo service is unreachable.

```bash
curl "http://localhost:8000/weather?city=Da%20Nang&days=5"
```

---

## `GET /air-quality` — current air quality + short forecast

Resolves a city name to coordinates and returns live air quality from the
keyless [Open-Meteo Air-Quality API](https://open-meteo.com/en/docs/air-quality-api):
the current **US AQI** with its category label, the six standard pollutants,
and a short per-day **max-AQI** forecast. Like `/weather`, this makes a real
outbound call; there is no cache (point-in-time data).

### Params

| Param | Required | Default | Notes |
|-------|----------|---------|-------|
| `city` | ✓ | — | City name to look up, e.g. `Da Nang`. |

The forecast horizon is server-configured (`air_quality_forecast_days`,
default `3`).

Returns **404** if the city name cannot be geocoded, **422** if `city` is
missing, and **502** if Open-Meteo is unreachable or returns a malformed body.

```bash
curl "http://localhost:8000/air-quality?city=Da%20Nang"
```

### Response (`AirQualityResponse`)

```json
{
  "location": { "name": "Da Nang", "country": "Vietnam", "latitude": 16.07, "longitude": 108.22, "timezone": "Asia/Ho_Chi_Minh" },
  "time": "2026-06-16T14:00",
  "us_aqi": 35,
  "category": "Good",
  "pm2_5": 8.3,
  "pm10": 15.1,
  "ozone": 62.4,
  "nitrogen_dioxide": 10.7,
  "sulphur_dioxide": 2.1,
  "carbon_monoxide": 189.5,
  "forecast": [
    { "date": "2026-06-16", "max_us_aqi": 42, "category": "Good" }
  ],
  "attribution": "Air quality data by Open-Meteo.com (CC BY 4.0)"
}
```

- `location` — resolved city coordinates and timezone (same `WeatherLocation`
  shape as `/weather`).
- `us_aqi` / pollutant cells / `forecast[].max_us_aqi` are **nullable**; when
  AQI is `null` the `category` is `"Unknown"`.
- `category` follows the **US-AQI bands**: `Good` ≤50, `Moderate` ≤100,
  `Unhealthy for Sensitive Groups` ≤150, `Unhealthy` ≤200, `Very Unhealthy`
  ≤300, `Hazardous` >300.
- `forecast` — one entry per day (in date order) with that day's peak AQI,
  derived from the hourly series.
- `attribution` — required Open-Meteo attribution; always present.

### Response codes

| Code | Condition |
|------|-----------|
| 200 | Success |
| 404 | City not found |
| 422 | `city` missing or empty |
| 502 | Open-Meteo Air-Quality API unavailable or returned malformed/empty data |

---

## `GET /bookings/{booking_id}`

Accepts **either** the booking UUID **or** its friendly `confirmation_code`
(case-insensitive) — they are interchangeable.

```bash
curl http://localhost:8000/bookings/<uuid>
curl http://localhost:8000/bookings/HDEAX4    # confirmation code
```

Returns the `Booking` object, or **404**.

### Booking object shape

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "type": "flight",
  "reference_id": "<flight or hotel uuid>",
  "customer_name": "Minh Tran",
  "customer_email": "minh@example.com",
  "total_price": 474.29,
  "currency": "USD",
  "status": "confirmed",
  "created_at": "2026-06-01T08:30:00+00:00",
  "notes": "Outbound leg of Da Nang trip",
  "details": { ... },
  "confirmation_code": "HDEAX4",
  "summary": "Bamboo Airways QH331 · DAD→SGN · departs 2026-06-01 07:15 · Minh Tran"
}
```

- `id` — canonical UUID; stable, used in URLs.
- `confirmation_code` — friendly **6-character PNR-style reference** (the kind
  airlines/hotels actually quote), derived deterministically from `id`. Use
  it interchangeably with the UUID for lookups, and it is matched by the
  `/bookings?q=` search.
- `summary` — one-line human/agent-readable description of the booking, so
  callers don't have to dig through `details`.
- `details` — flight- or hotel-specific data (route, hotel name, nights, etc.).
- `notes` — `null` if none was provided at booking time.

---

## `POST /bookings/{booking_id}/cancel`

Cancels a booking and returns it with `status: "cancelled"`. Accepts the
UUID **or** the confirmation code. A *soft* change — the booking row is kept
and still retrievable via `GET /bookings/{id}`. **Idempotent**: cancelling an
already-cancelled booking is a no-op. **404** if no booking matches.

```bash
curl -X POST http://localhost:8000/bookings/HDEAX4/cancel
```

---

## `/trips` — itinerary planner (CRUD)

A **trip** is a freeform, day-by-day itinerary you can save and edit. It is the
second piece of mutable state in the API (alongside bookings), persisted to the
same SQLite file. A trip holds a list of **items** — one per planned thing —
each tagged with a `kind` (`place` \| `activity` \| `meal` \| `transport` \|
`note`) and a `day` number. Items are standalone planning notes: `place_id` is
an optional free-text hint and is **not** validated against the place catalog,
and trips carry **no** prices or booking links.

Trips and items are addressed by their exact **UUID** (no fuzzy matching).
Items are returned sorted by `(day, sort_order)`.

| Endpoint | Notes |
|----------|-------|
| `POST /trips` | Create a trip. Body: `title` (required), optional `city`, `start_date`, `end_date` (YYYY-MM-DD; `end_date` ≥ `start_date`), `travelers` (1–50, default 1), `notes`, and an optional `items` array. → **201** |
| `GET /trips` | List trips, newest first, in the shared `limit`/`offset` envelope |
| `GET /trips/{trip_id}` | One trip with its items. **404** if unknown |
| `PUT /trips/{trip_id}` | Replace the trip's top-level fields (items unchanged). Omitted optional fields reset to defaults. **404** if unknown |
| `DELETE /trips/{trip_id}` | Delete the trip and all its items. → **204**, **404** if unknown |
| `GET /trips/{trip_id}/budget` | Per-category caps (planned) vs booked spend. **404** if unknown |
| `POST /trips/{trip_id}/budget` | Replace the trip's per-category caps; returns the budget. **404** if unknown |
| `POST /trips/{trip_id}/items` | Add one item. Body: `day` (≥1), `kind`, `title`, optional `sort_order`, `place_id`, `start_time`, `notes`. → **201**, **404** if the trip is unknown, **409** if a linked booking pushes a category over its cap |
| `PUT /trips/{trip_id}/items/{item_id}` | Replace an item. **404** if the trip or item does not match |
| `DELETE /trips/{trip_id}/items/{item_id}` | Delete one item. → **204**, **404** if the trip or item does not match |

```bash
# Create a trip with two day-1 items
curl -X POST http://localhost:8000/trips \
  -H 'Content-Type: application/json' \
  -d '{
        "title": "Da Nang long weekend",
        "city": "Da Nang",
        "travelers": 2,
        "items": [
          {"day": 1, "kind": "place", "title": "Dragon Bridge", "start_time": "19:00"},
          {"day": 1, "kind": "meal", "title": "Bánh xèo dinner", "sort_order": 1}
        ]
      }'

# Add an item to an existing trip
curl -X POST http://localhost:8000/trips/<trip_id>/items \
  -H 'Content-Type: application/json' \
  -d '{"day": 2, "kind": "activity", "title": "Marble Mountains hike"}'
```

### `POST /trips/estimate` — budget estimator

A **stateless calculator**: given a trip's shape (and any costs you already
know) it returns a line-item budget breakdown, a buffered total, and a
per-person figure. It **persists nothing** — no SQLite, no booking — so it does
not touch the "bookings are the only mutable state" rule.

**Request body**

| Field | Required | Notes |
|-------|----------|-------|
| `nights` | yes | Integer ≥ 1 |
| `travelers` | yes | Integer 1–50 |
| `city` | no | Free text; informational only (does not affect the math) |
| `flight_total_usd` | no | Known total flight cost (≥ 0). Omit to exclude flights |
| `hotel_price_per_night_usd` | no | Known room price/night (≥ 0). Omit to exclude lodging |
| `meal_style` | no | `budget` \| `mid` \| `fine` (default `mid`) |
| `activity_level` | no | `none` \| `some` \| `lots` (default `some`) |

Bad enum values or `nights`/`travelers` below their minimums → **422**. Omitting
`flight_total_usd` / `hotel_price_per_night_usd` zeroes that line and records an
entry in `assumptions` (still **200**).

**Rates** (USD per person per day, where "day" = one night): meals
`budget`=$15 / `mid`=$30 / `fine`=$70; activities `none`=$0 / `some`=$20 /
`lots`=$50; local transport $15/day (per trip); plus a 10% incidentals buffer.
`total_estimate` is rounded to whole dollars; `assumptions` spells out every
rate used so an agent can explain the number.

```bash
curl -X POST http://localhost:8000/trips/estimate \
  -H 'Content-Type: application/json' \
  -d '{
        "city": "Da Nang", "nights": 3, "travelers": 2,
        "flight_total_usd": 240, "hotel_price_per_night_usd": 90,
        "meal_style": "mid", "activity_level": "some"
      }'
# → breakdown {flights 240, accommodation 270, meals 180, activities 120,
#   local_transport 45}, subtotal 855, total_estimate 941, per_person 470.5
```

### `/trips/{trip_id}/budget` — caps vs spend

Unlike the stateless estimator, a trip's **budget** is saved state: per-category
USD **caps** (the planned target) tracked against **spent** (the booked rollup).
The four categories are `flights`, `hotels`, `activities`, and `buffer`; each is
a `cap` / `spent` / `remaining` triple (`remaining` is `cap - spent`, negative
when over, `null` when no cap is set). `spent` is summed from the trip's
**linked, non-cancelled bookings** by type (flight bookings → `flights`, hotel
bookings → `hotels`); `activities` and `buffer` have no booking source yet, so
they stay at `0`.

`GET /trips/{trip_id}/budget` returns the current caps vs spend plus rolled-up
`total_cap` / `total_spent` / `total_remaining` and an `over_budget` flag (true
when any capped category's spend is strictly above its cap). **404** if the trip
is unknown.

`POST /trips/{trip_id}/budget` **replaces** the caps — every POST is the full
set, so any category you omit (or send as `null`) becomes uncapped. Caps are
`≥ 0`. It returns the same budget shape. **404** if the trip is unknown.

Once caps are set, `POST /trips/{trip_id}/items` returns **409** when the new
item carries a linked booking whose spend would push that category over its cap.

```bash
# Set caps (replace) — flights $700, hotels $500
curl -X POST http://localhost:8000/trips/<trip_id>/budget \
  -H 'Content-Type: application/json' \
  -d '{"flights": 700, "hotels": 500}'

# Read caps vs booked spend
curl http://localhost:8000/trips/<trip_id>/budget
```

---

## Error format

Every error response — domain (404/409/502), HTTP, and request-validation
(422) — uses one consistent JSON envelope, so a client can parse failures
the same way regardless of origin:

```json
{
  "error": "NotFoundError",
  "message": "Booking not found",
  "status_code": 404,
  "path": "/bookings/<uuid>"
}
```

Validation errors (422) additionally carry an `errors` array with the
per-field Pydantic detail:

```json
{
  "error": "ValidationError",
  "message": "Request validation failed",
  "status_code": 422,
  "path": "/airports",
  "errors": [ { "loc": ["query", "limit"], "msg": "...", "type": "..." } ]
}
```

---

## ID formats

All resource IDs are **UUIDs**.

| Resource | Example |
|----------|---------|
| Flight | `3f2a1b4c-5d6e-7f8a-9b0c-1d2e3f4a5b6c` |
| Hotel | `0acc4018-3bb2-5760-8101-630dda1d011a` |
| Booking | `550e8400-e29b-41d4-a716-446655440000` |

Hotel UUIDs are stable forever (derived deterministically from seed data).
Flight UUIDs are stable within a server session — obtain them via
`/flights/search`, then reference by ID.

Bookings additionally expose a friendly `confirmation_code` — a 6-character
PNR-style reference (uppercase letters + digits, ambiguous characters like
`0/O/1/I/L` omitted), e.g. `HDEAX4`. It is derived deterministically from the
booking UUID, so it is stable, and is accepted anywhere the booking UUID is.
