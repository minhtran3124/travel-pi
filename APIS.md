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
| GET | `/flights/search` | Search flights (one-way or round-trip) |
| GET | `/flights/{flight_id}` | Get one flight by UUID |
| POST | `/flights/book` | Book a flight |
| GET | `/hotels` | List all hotels |
| GET | `/hotels/search` | Search hotels with optional filters |
| GET | `/hotels/{hotel_id}` | Get one hotel by UUID |
| POST | `/hotels/book` | Book a hotel |
| GET | `/places` | List all places / attractions |
| GET | `/places/search` | Search places by city + filters |
| GET | `/places/{place_id}` | Get one place by ID |
| GET | `/tips` | Local tips for a city or country |
| GET | `/weather` | Current weather + short forecast for a city |
| GET | `/bookings` | List bookings (search / filter / sort) |
| GET | `/bookings/{booking_id}` | Look up a booking by UUID |

---

## `GET /cities`

Returns every city that has at least one seeded hotel, with hotel count and
country. **Use this before calling `/hotels/search`** to validate a city name
— unknown cities return `count: 0`, not an error.

```bash
curl http://localhost:8000/cities
```

```json
[
  { "name": "Bali",           "country": "Indonesia", "hotel_count": 5 },
  { "name": "Bangkok",        "country": "Thailand",  "hotel_count": 5 },
  { "name": "Cebu",           "country": "Philippines","hotel_count": 1 },
  { "name": "Chiang Mai",     "country": "Thailand",  "hotel_count": 3 },
  { "name": "Da Nang",        "country": "Vietnam",   "hotel_count": 4 },
  ...
]
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
    "flight_id": "<uuid from /flights/search>",
    "passenger_name": "Minh Tran",
    "passenger_email": "minh@example.com",
    "total_price": 474.29,
    "notes": "Outbound leg of Da Nang trip"
  }'
```

| Field | Required | Notes |
|-------|----------|-------|
| `flight_id` | ✓ | UUID from `/flights/search` — **404** if invalid |
| `passenger_name` | ✓ | |
| `passenger_email` | ✓ | |
| `total_price` | ✓ | Client-supplied (mock only; real APIs never do this) |
| `notes` | — | Free-text context the agent/user wants to attach |

Returns a `Booking` object. The booking `id` is a UUID you can later fetch via
`GET /bookings/{id}`.

---

## `GET /hotels`

```bash
curl http://localhost:8000/hotels
```

Returns all 51 seeded hotels, unfiltered.

---

## `GET /hotels/search` — with optional filters

### Required params

| Param | Example |
|-------|---------|
| `city` | `Da Nang` — case-insensitive; unknown city returns `count: 0` |
| `check_in` | `2026-06-01` (YYYY-MM-DD) |
| `check_out` | `2026-06-03` (YYYY-MM-DD) |

### Optional params

| Param | Example | Notes |
|-------|---------|-------|
| `guests` | `2` | Echoed back; does not filter |
| `min_stars` | `4` | Only hotels with star_rating ≥ this value (1–5) |
| `max_price` | `300` | Only hotels with price_per_night ≤ this (USD) |
| `amenities` | `Pool` | Required amenity. **Repeat the param for multiple.** All must match. |

### Basic example

```bash
curl "http://localhost:8000/hotels/search?city=Da%20Nang&check_in=2026-06-01&check_out=2026-06-03"
```

### Filtered example — 5-star with pool and spa, under $500/night

```bash
curl "http://localhost:8000/hotels/search\
?city=Bangkok\
&check_in=2026-06-01\
&check_out=2026-06-05\
&min_stars=5\
&max_price=500\
&amenities=Pool\
&amenities=Spa"
```

```json
{
  "count": 2,
  "search": {
    "city": "Bangkok", "check_in": "2026-06-01", "check_out": "2026-06-05",
    "guests": 1, "min_stars": 5, "max_price": 500.0,
    "amenities": ["Pool", "Spa"]
  },
  "results": [ ... ]
}
```

All applied filters are echoed back in the `search` object so the UI can show
what was active.

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
    "hotel_id": "<uuid from /hotels/search>",
    "check_in": "2026-06-01",
    "check_out": "2026-06-03",
    "guests": 2,
    "guest_name": "Minh Tran",
    "guest_email": "minh@example.com",
    "notes": "Anniversary trip — request sea-view room"
  }'
```

| Field | Required | Notes |
|-------|----------|-------|
| `hotel_id` | ✓ | UUID from `/hotels` or `/hotels/search` — **404** if invalid |
| `check_in` | ✓ | YYYY-MM-DD |
| `check_out` | ✓ | YYYY-MM-DD |
| `guests` | — | Default 1 |
| `guest_name` | ✓ | |
| `guest_email` | ✓ | |
| `notes` | — | Free-text context the agent/user wants to attach |

`total_price` is calculated server-side: `price_per_night × nights` (minimum 1
night). The response `details` object includes `nights` and `price_per_night`.

---

## `GET /bookings`

All params optional:

| Param | Values | Notes |
|-------|--------|-------|
| `q` | any string | Case-insensitive match on ID, name, or email |
| `type` | `flight` \| `hotel` | Other values ignored |
| `sort` | `created_desc` (default), `created_asc`, `price_desc`, `price_asc` | Unknown values fall back to `created_desc` |

```bash
# All hotel bookings, most expensive first
curl "http://localhost:8000/bookings?type=hotel&sort=price_desc"

# Search by customer name
curl "http://localhost:8000/bookings?q=minh"
```

---

## `GET /tips` — local tips for a destination

Curated, practical advice for a destination — currency, transport, safety,
etiquette, food, best time to visit, etc. Data is two-tier: **country tips**
(inherited by every city in that country) merged with any **city-specific
tips**.

### Params

| Param | Required | Notes |
|-------|----------|-------|
| `city` | one of `city`/`country` | City name. Resolves its own country, then merges country + city tips. |
| `country` | one of `city`/`country` | Country name, case-insensitive. |
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

## `GET /bookings/{booking_id}`

```bash
curl http://localhost:8000/bookings/<uuid>
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
  "details": { ... }
}
```

`details` contains flight- or hotel-specific data (route, hotel name, nights,
etc.). `notes` is `null` if none was provided at booking time.

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
