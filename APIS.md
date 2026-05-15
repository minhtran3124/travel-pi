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
| GET | `/places/nearby` | Find places near another place |
| GET | `/places/route` | Route between two places — distance, time, best travel mode |
| GET | `/places/{place_id}` | Get one place by ID |
| GET | `/tips` | Local tips for a city or country |
| GET | `/weather` | Current weather + short forecast for a city |
| GET | `/bookings` | List bookings (search / filter / sort) |
| GET | `/bookings/{booking_id}` | Look up a booking by UUID or confirmation code |
| POST | `/bookings/{booking_id}/cancel` | Cancel a booking |

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
    "passenger_phone": "+84 901 234 567",
    "notes": "Outbound leg of Da Nang trip"
  }'
```

| Field | Required | Notes |
|-------|----------|-------|
| `flight_id` | ✓ | UUID from `/flights/search` — **404** if invalid |
| `passenger_name` | ✓ | Full name as printed on the passenger's ID/passport |
| `passenger_email` | ✓ | Contact email for the itinerary / e-ticket |
| `passenger_phone` | ✓ | Contact phone for airline notifications (delays, gate) |
| `notes` | — | Free-text context the agent/user wants to attach |

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
