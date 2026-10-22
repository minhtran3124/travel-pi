# API Reference

Base URL: `http://localhost:8000`  
Interactive docs: `http://localhost:8000/docs`

---

## Authentication

Most endpoints are open, but the owner-scoped and agent surfaces require a
**Supabase JWT** sent as `Authorization: Bearer <token>`. A missing or invalid
token yields `401`. Ownership is enforced per caller: another user's resource
reads as `404` (never `403`), so a guessed id is not confirmed.

Routes that require a token:

| Route(s) | Notes |
|----------|-------|
| `GET/POST /bookings`, `GET /bookings/{id}`, `POST /bookings/{id}/cancel` | Scoped to the caller; you only see and cancel your own bookings. |
| `POST /flights/book`, `POST /hotels/book` | The booking is stamped with the caller as owner. |
| `GET/POST /places/saved`, `GET/DELETE /places/saved/{id}`, `POST /places/saved/{id}/favorite`, `POST /places/saved/{id}/visited` | Saved places are per-user. |
| `/agent/*` | The chat agent and its endpoints. |

JWT verification is disabled by default for local dev and tests (set
`SUPABASE_URL` or `SUPABASE_PROJECT_REF` to enable it — see `.env.example`).

The server-rendered `/dashboard/*` operator pages require a login (username +
password from `DASHBOARD_BASIC_USER`/`DASHBOARD_BASIC_PASSWORD`), backed by a
signed session cookie (`DASHBOARD_SECRET_KEY`). Login is always required, in
both dev and prod — it no longer runs open in dev or 404s in prod. If any of
the three env vars is missing, every dashboard page redirects to the login
screen, which shows a "not configured" notice instead of a working form.

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Service info + endpoint list |
| GET | `/airports` | All airports (fuzzy `?q=` search) |
| GET | `/cities` | Cities with hotel data (fuzzy `?q=` search) |
| GET | `/cities/{city_name}` | One city by name |
| GET | `/cities/route` | Route between two cities |
| GET | `/flights/search` | Search flights (one-way or round-trip) |
| GET | `/flights/{flight_id}` | One flight by UUID |
| POST | `/flights/book` | Book a flight |
| GET | `/hotels` | All hotels |
| GET | `/hotels/search` | Browse hotels in a city (no dates) |
| GET | `/hotels/availability` | Check availability for dates + party size |
| GET | `/hotels/{hotel_id}` | One hotel by UUID |
| POST | `/hotels/book` | Book a hotel |
| GET | `/places` | All places |
| GET | `/places/search` | Search places by city + filters |
| GET | `/places/cities` | Cities that have places |
| GET | `/places/categories` | All place categories |
| GET | `/places/nearby` | Places near a given place |
| GET | `/places/route` | Route between two places |
| GET | `/places/{place_id}` | One place by ID |
| GET | `/tips` | Local tips for a city or country |
| GET | `/visa` | Visa/entry requirements |
| GET | `/weather` | Current weather + forecast |
| GET | `/air-quality` | US-AQI + pollutants + forecast |
| GET | `/destinations/climate` | Monthly climate normals + best-time guidance |
| GET | `/destinations/{city}/overview` | City briefing: weather, places, tips, hotels |
| GET | `/currency/convert` | Currency conversion (static FX snapshot) |
| GET | `/bookings` | List/search bookings |
| GET | `/bookings/{booking_id}` | One booking (UUID or confirmation code) |
| POST | `/bookings/{booking_id}/cancel` | Cancel a booking |
| POST | `/trips` | Create a trip itinerary |
| POST | `/trips/estimate` | Estimate trip budget (stateless) |
| GET | `/trips` | List trips |
| GET | `/trips/{trip_id}` | One trip with items |
| PUT | `/trips/{trip_id}` | Replace trip fields |
| DELETE | `/trips/{trip_id}` | Delete a trip |
| GET | `/trips/{trip_id}/budget` | Budget caps vs booked spend |
| POST | `/trips/{trip_id}/budget` | Set budget caps |
| POST | `/trips/{trip_id}/items` | Add an item to a trip |
| PUT | `/trips/{trip_id}/items/{item_id}` | Replace an item |
| DELETE | `/trips/{trip_id}/items/{item_id}` | Delete an item |

---

## Pagination

List endpoints share a common `limit`/`offset` contract:

| Param | Default | Range |
|-------|---------|-------|
| `limit` | `20` | 1–500 |
| `offset` | `0` | — |

```json
{ "total": 51, "limit": 20, "offset": 0, "results": [ ... ] }
```

`total` is the full match count; `results` is the current page. Applies to: `/airports`, `/cities`, `/hotels`, `/hotels/search`, `/hotels/availability`, `/places`, `/places/search`, `/bookings`.

---

## Fuzzy name resolution

Every endpoint that accepts a free-text `city` or `country` resolves it fuzzily — typo, spacing, and case tolerant. `danang`, `da nang`, and `DaNang` all resolve to `Da Nang`. An unrecognised name returns an empty result (`count/total: 0`), never a 404. Resource IDs (UUIDs, IATA codes) are always exact.

---

## `GET /cities`

```bash
curl "http://localhost:8000/cities"
curl "http://localhost:8000/cities?q=bangok"          # typo → Bangkok
curl "http://localhost:8000/cities?country=Vietnam"
```

| Param | Notes |
|-------|-------|
| `q` | Fuzzy free-text search, ranked best-match-first |
| `country` | Filter by country (fuzzy) |
| `has_hotels` | `true` to exclude cities with no hotels |

```json
{
  "total": 12, "limit": 20, "offset": 0,
  "results": [
    { "name": "Da Nang", "country": "Vietnam", "hotel_count": 4, "airport_codes": ["DAD"], "latitude": 16.05, "longitude": 108.20 }
  ]
}
```

---

## `GET /airports`

```bash
curl "http://localhost:8000/airports?q=da nang"
```

Accepts the same `?q=` fuzzy search as `/cities`. Matches on IATA code, name, and city.

---

## `GET /cities/route`

Route between two cities by name (fuzzy-matched).

| Param | Required |
|-------|----------|
| `origin` | ✓ |
| `destination` | ✓ |

```bash
curl "http://localhost:8000/cities/route?origin=danang&destination=hoi an"
```

Returns `404` if either city is unknown, `502` if a routing provider is unreachable. See [`GET /places/route`](#get-placesroute) for the response shape and routing behaviour.

---

## `GET /flights/search`

| Param | Required | Notes |
|-------|----------|-------|
| `origin` | ✓ | IATA code, case-insensitive |
| `destination` | ✓ | IATA code, case-insensitive |
| `departure_date` | ✓ | YYYY-MM-DD |
| `return_date` | — | YYYY-MM-DD — triggers round-trip response |
| `adults` | — | Echoed back; does not filter |
| `airline` | — | IATA code filter |
| `max_price` | — | USD ceiling |
| `max_stops` | — | `0` = direct only |
| `sort` | — | `departure_asc/desc`, `price_asc/desc`, `duration_asc/desc` (default `departure_asc`) |

Same route + date always returns the same 5 flights (deterministic). Filters narrow that set.

```bash
# One-way
curl "http://localhost:8000/flights/search?origin=DAD&destination=SGN&departure_date=2026-06-01"

# Round-trip
curl "http://localhost:8000/flights/search?origin=DAD&destination=SGN&departure_date=2026-06-01&return_date=2026-06-08"
```

```json
{
  "count": 5,
  "search": { "origin": "DAD", "destination": "SGN", "departure_date": "2026-06-01", "return_date": null, "..." : "..." },
  "results": [ ... ],
  "return_count": null,
  "return_results": null
}
```

Round-trip: `return_count` and `return_results` carry the return leg. Filters apply to both legs independently.

---

## `GET /flights/{flight_id}`

```bash
curl http://localhost:8000/flights/<uuid>
```

Returns the flight object, or `404`. Get UUIDs from `/flights/search`.

---

## `POST /flights/book`

| Field | Required | Notes |
|-------|----------|-------|
| `flight_number` | ✓ | e.g. `VN123` — from `/flights/search` |
| `origin` | ✓ | IATA code |
| `destination` | ✓ | IATA code |
| `departure_date` | ✓ | YYYY-MM-DD |
| `passenger_name` | ✓ | |
| `passenger_email` | ✓ | |
| `passenger_phone` | ✓ | |
| `notes` | — | Free text |

`flight_number` + route + date together identify a unique flight. Unmatched combination → `404`. `total_price` is set server-side from the flight — not sent by the client.

```bash
curl -X POST http://localhost:8000/flights/book \
  -H "Content-Type: application/json" \
  -d '{
    "flight_number": "VN123", "origin": "DAD", "destination": "SGN",
    "departure_date": "2026-06-01", "passenger_name": "Minh Tran",
    "passenger_email": "minh@example.com", "passenger_phone": "+84 901 234 567"
  }'
```

Returns a [`Booking`](#booking-object) with a UUID and a friendly `confirmation_code`.

**Idempotency:** pass `Idempotency-Key: <key>` to make retries safe — same key returns the original booking.

---

## `GET /hotels`

```bash
curl http://localhost:8000/hotels
```

Returns all 51 seeded hotels.

---

## `GET /hotels/search`

Browse hotels by static attributes — no dates. To check room availability use [`/hotels/availability`](#get-hotelsavailability).

| Param | Required | Notes |
|-------|----------|-------|
| `city` | ✓ | Fuzzy; unknown city → `total: 0` |
| `min_stars` | — | 1–5 |
| `max_price` | — | USD ceiling on `price_per_night` |
| `amenities` | — | Required amenity; repeat for multiple (all must match) |

```bash
curl "http://localhost:8000/hotels/search?city=Bangkok&min_stars=5&amenities=Pool&amenities=Spa"
```

---

## `GET /hotels/availability`

Returns hotels annotated with availability for the requested dates and party size. Availability is generated deterministically (same query → same answer).

| Param | Required | Default | Notes |
|-------|----------|---------|-------|
| `city` | ✓ | — | Fuzzy |
| `check_in` | ✓ | — | YYYY-MM-DD |
| `check_out` | ✓ | — | YYYY-MM-DD |
| `rooms` | — | `1` | |
| `adults` | — | `2` | |
| `children` | — | `0` | |
| `available_only` | — | `false` | Drop unavailable hotels |
| `min_stars`, `max_price`, `amenities` | — | — | Same as `/hotels/search` |

```bash
curl "http://localhost:8000/hotels/availability?city=Da%20Nang&check_in=2026-06-01&check_out=2026-06-03&rooms=1&adults=2"
```

```json
{
  "results": [
    {
      "...": "hotel fields",
      "available": true,
      "available_rooms": 56,
      "max_occupancy_per_room": 3,
      "nights": 2,
      "total_price": 900.0
    }
  ]
}
```

`available = available_rooms ≥ rooms` and `max_occupancy_per_room × rooms ≥ adults + children`. `total_price = price_per_night × nights × rooms`.

---

## `GET /hotels/{hotel_id}`

```bash
curl http://localhost:8000/hotels/<uuid>
```

Returns the hotel object, or `404`.

---

## `POST /hotels/book`

| Field | Required | Notes |
|-------|----------|-------|
| `hotel_id` | ✓ | UUID from `/hotels` or `/hotels/availability` |
| `check_in` | ✓ | YYYY-MM-DD |
| `check_out` | ✓ | YYYY-MM-DD |
| `rooms` | — | Default `1` |
| `adults` | — | Default `2` |
| `children` | — | Default `0` |
| `guest_name` | ✓ | |
| `guest_email` | ✓ | |
| `guest_phone` | ✓ | |
| `notes` | — | Free text |

Availability-checked: `409` if the hotel can't take the party for those dates. `total_price` is computed server-side. Supports `Idempotency-Key` (see [`POST /flights/book`](#post-flightsbook)).

```bash
curl -X POST http://localhost:8000/hotels/book \
  -H "Content-Type: application/json" \
  -d '{
    "hotel_id": "<uuid>", "check_in": "2026-06-01", "check_out": "2026-06-03",
    "guest_name": "Minh Tran", "guest_email": "minh@example.com", "guest_phone": "+84 901 234 567"
  }'
```

---

## `GET /places/search`

| Param | Required | Notes |
|-------|----------|-------|
| `city` | ✓ | Fuzzy |
| `category` | — | e.g. `restaurant`, `landmark` |
| `recommended` | — | `true` to filter recommended only |

```bash
curl "http://localhost:8000/places/search?city=Da%20Nang&category=restaurant"
```

---

## `GET /places/nearby`

Places near a given place, nearest-first, each annotated with `distance_km`. Straight-line only (no external call).

| Param | Required | Default | Notes |
|-------|----------|---------|-------|
| `place_id` | ✓ | — | |
| `radius_km` | — | `5` | 0–50 |
| `limit` | — | `10` | 1–50 |
| `category` | — | — | Optional filter |

`404` if the place is unknown. Nothing in range → empty results.

```bash
curl "http://localhost:8000/places/nearby?place_id=56f5b6d7-f0e2-5867-a9dd-087a98cff34c&radius_km=3&category=cafe"
```

---

## `GET /places/route`

Route between two places by UUID.

| Param | Required |
|-------|----------|
| `origin` | ✓ |
| `destination` | ✓ |

```bash
curl "http://localhost:8000/places/route?origin=<uuid>&destination=<uuid>"
```

```json
{
  "origin":      { "kind": "place", "id": "...", "name": "Dragon Bridge",    "latitude": 16.0607, "longitude": 108.2275 },
  "destination": { "kind": "place", "id": "...", "name": "Marble Mountains", "latitude": 15.9736, "longitude": 108.2625 },
  "straight_line_km": 10.38,
  "recommended_mode": "car",
  "legs": [
    { "mode": "walk", "distance_km": 13.49, "duration_minutes": 179.9 },
    { "mode": "bike", "distance_km": 13.49, "duration_minutes": 54.0 },
    { "mode": "car",  "distance_km": 13.49, "duration_minutes": 23.1 }
  ],
  "source": "estimate",
  "attribution": "Offline straight-line estimate (set ORS_API_KEY for real road routing)"
}
```

`recommended_mode`: ≤1.5 km → `walk`, ≤8 km → `bike`, otherwise `car`. Without `ORS_API_KEY` the source is `"estimate"` (haversine + detour factor); with it, real road routing via OpenRouteService. Results are cached. `404` if either place is unknown, `502` if a routing provider is unreachable.

---

## `GET /tips`

| Param | Required | Notes |
|-------|----------|-------|
| `city` | one of | Fuzzy. Merges country + city tips. |
| `country` | one of | Fuzzy. |
| `category` | — | `transport`, `money`, `safety`, `culture`, `food`, `connectivity`, `health`, `etiquette`, `best_time`, `language` |
| `essential_only` | — | `true` to return only must-know tips |

Provide `city` or `country`, not both — neither → `422`. Unknown → `count: 0`.

```bash
curl "http://localhost:8000/tips?city=Hanoi"
curl "http://localhost:8000/tips?country=Thailand&category=safety"
curl "http://localhost:8000/tips?city=Bali&essential_only=true"
```

```json
{
  "city": "Hanoi", "country": "Vietnam", "count": 11,
  "summary": "Vietnam is rewarding and affordable ...",
  "tips": [
    {
      "id": "tip_city_hanoi_00", "category": "transport", "scope": "city",
      "title": "Crossing the road: walk slow and steady",
      "content": "Traffic won't stop for you, but it will flow around you ...",
      "is_essential": true
    }
  ]
}
```

`scope` is `"country"` or `"city"`.

---

## `GET /visa`

| Param | Required | Notes |
|-------|----------|-------|
| `city` | one of | Resolves the city's country automatically |
| `country` | one of | |

Neither → `422`. Unknown → `found: false`, `entry: null` (not a 404).

```bash
curl "http://localhost:8000/visa?city=Da%20Nang"
```

```json
{
  "city": "Da Nang", "country": "Vietnam", "found": true,
  "entry": {
    "visa_free_days": 45, "visa_on_arrival": true, "e_visa": true,
    "passport_validity_months": 6,
    "summary": "Many nationalities get 45 days visa-free ..."
  },
  "disclaimer": "General guidance only — always confirm with the destination's official immigration authority before travel."
}
```

Always surface `disclaimer` to the end user. `entry.passport_validity_months: 0` means "valid for the duration of stay".

---

## `GET /weather`

Live current conditions + forecast from [Open-Meteo](https://open-meteo.com/) (no API key). Real outbound call — no cache.

| Param | Required | Default |
|-------|----------|---------|
| `city` | ✓ | — |
| `days` | — | `3` (1–16) |

`404` if city unknown, `502` if Open-Meteo is unreachable.

```bash
curl "http://localhost:8000/weather?city=Da%20Nang&days=5"
```

---

## `GET /air-quality`

Live US-AQI + six pollutants + daily max-AQI forecast from [Open-Meteo Air-Quality API](https://open-meteo.com/en/docs/air-quality-api) (no API key). Real outbound call.

| Param | Required |
|-------|----------|
| `city` | ✓ |

`404` city unknown, `422` city missing, `502` Open-Meteo unreachable.

```bash
curl "http://localhost:8000/air-quality?city=Da%20Nang"
```

```json
{
  "location": { "name": "Da Nang", "country": "Vietnam", "latitude": 16.07, "longitude": 108.22, "timezone": "Asia/Ho_Chi_Minh" },
  "time": "2026-06-16T14:00",
  "us_aqi": 35, "category": "Good",
  "pm2_5": 8.3, "pm10": 15.1, "ozone": 62.4,
  "nitrogen_dioxide": 10.7, "sulphur_dioxide": 2.1, "carbon_monoxide": 189.5,
  "forecast": [ { "date": "2026-06-16", "max_us_aqi": 42, "category": "Good" } ],
  "attribution": "Air quality data by Open-Meteo.com (CC BY 4.0)"
}
```

US-AQI bands: `Good` ≤50, `Moderate` ≤100, `Unhealthy for Sensitive Groups` ≤150, `Unhealthy` ≤200, `Very Unhealthy` ≤300, `Hazardous` >300. `us_aqi` and pollutant values are nullable.

---

## `GET /destinations/climate`

Monthly climate normals (avg temp, precipitation, rainy days, comfort label) from Open-Meteo historical archive. Includes `best_months` and a prose `summary`. Real outbound call — `502` on failure (no degradation).

| Param | Required | Notes |
|-------|----------|-------|
| `city` | ✓ | Fuzzy; unknown → `404` |
| `month` | — | 1–12. Returns only that month; `best_months` will be `[]`. |

```bash
curl "http://localhost:8000/destinations/climate?city=Da%20Nang"
curl "http://localhost:8000/destinations/climate?city=Bangkok&month=2"
```

```json
{
  "location": { "name": "Da Nang", "country": "Vietnam", "latitude": 16.05, "longitude": 108.20, "timezone": "Asia/Ho_Chi_Minh" },
  "based_on_years": [2022, 2023, 2024],
  "months": [
    { "month": 1, "name": "January", "avg_temp_max_c": 25.1, "avg_temp_min_c": 19.3, "avg_precip_mm": 83.4, "rainy_days": 12, "comfort": "mild, wet" }
  ],
  "best_months": [2, 3, 4],
  "summary": "Da Nang is driest and most comfortable around February, March and April.",
  "attribution": "Weather data by Open-Meteo.com (CC BY 4.0)"
}
```

---

## `GET /destinations/{city}/overview`

One-call city briefing: weather, top places, essential tips, hotel summary. Weather degrades gracefully (`null`) if Open-Meteo is unavailable — always returns `200`.

| Param | Default | Notes |
|-------|---------|-------|
| `include` | all | Comma-separated subset of `weather,places,tips,hotels`. Unknown member → `422`. |
| `place_limit` | `5` | 1–20 |
| `tip_limit` | `5` | 1–20 |

`404` if city unknown.

```bash
curl "http://localhost:8000/destinations/Da%20Nang/overview"
curl "http://localhost:8000/destinations/Bangkok/overview?include=weather,places&place_limit=3"
```

```json
{
  "city": "Da Nang", "country": "Vietnam", "latitude": 16.05, "longitude": 108.20,
  "weather": { "..." : "..." },
  "top_places": [ { "id": "...", "name": "Dragon Bridge", "category": "landmark", "rating": 4.7 } ],
  "essential_tips": [ { "id": "...", "category": "transport", "title": "Grab is the standard taxi app", "is_essential": true } ],
  "hotel_summary": { "count": 4, "price_range_usd": { "min": 45.0, "max": 450.0 }, "star_range": { "min": 3, "max": 5 }, "sample": [ "..." ] },
  "attribution": "Weather data by Open-Meteo.com (CC BY 4.0)"
}
```

`top_places` — recommended first, then by rating. `essential_tips` — `is_essential: true` only. `hotel_summary.sample` — up to 3 representative hotels.

---

## `GET /currency/convert`

Static FX snapshot (not live rates). Supported codes: `USD`, `EUR`, `GBP`, `AUD`, `VND`, `THB`, `SGD`, `MYR`, `IDR`, `PHP`, `KHR`, `LAK`, `MMK`, `BND`, `HKD`, `KRW`, `JPY`, `CNY`, `TWD`, `AED`, `TRY`.

| Param | Required | Default | Notes |
|-------|----------|---------|-------|
| `to` | ✓ | — | ISO 4217, case-insensitive. Unknown → `404`. |
| `from` | — | `USD` | ISO 4217, case-insensitive. Unknown → `404`. |
| `amount` | — | `1.0` | Must be > 0 → else `422`. |
| `country` | — | — | Fuzzy. Resolved → adds `local_currency`; unknown → ignored. |

```bash
curl "http://localhost:8000/currency/convert?from=USD&to=VND&amount=100&country=Vietnam"
```

```json
{
  "from": "USD", "to": "VND", "rate": 25400.0, "amount": 100.0,
  "converted": 2540000.0, "last_updated": "2026-06-01",
  "local_currency": { "code": "VND", "name": "Vietnamese Dong" }
}
```

---

## `GET /bookings`

| Param | Notes |
|-------|-------|
| `q` | Case-insensitive match on ID, confirmation code, customer name, or email |
| `type` | `flight` or `hotel` |
| `sort` | `created_desc` (default), `created_asc`, `price_desc`, `price_asc` |

```bash
curl "http://localhost:8000/bookings?type=hotel&sort=price_desc"
curl "http://localhost:8000/bookings?q=minh"
```

---

## `GET /bookings/{booking_id}`

Accepts the UUID **or** the `confirmation_code` (case-insensitive). Returns `404` if not found.

```bash
curl http://localhost:8000/bookings/<uuid>
curl http://localhost:8000/bookings/HDEAX4
```

### Booking object

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
  "notes": null,
  "details": { "..." : "..." },
  "confirmation_code": "HDEAX4",
  "summary": "Bamboo Airways QH331 · DAD→SGN · departs 2026-06-01 07:15 · Minh Tran"
}
```

`confirmation_code` is a 6-character PNR-style reference (ambiguous chars `0/O/1/I/L` omitted), interchangeable with the UUID everywhere. `summary` is a one-line human-readable description. `notes` is `null` if none provided.

---

## `POST /bookings/{booking_id}/cancel`

Soft cancel — row is kept, `status` becomes `"cancelled"`. Idempotent. Accepts UUID or confirmation code.

```bash
curl -X POST http://localhost:8000/bookings/HDEAX4/cancel
```

---

## `/trips` — itinerary planner

Trips are persisted freeform day-by-day itineraries. Items have a `kind` (`place` | `activity` | `meal` | `transport` | `note`) and a `day` number. Items are returned sorted by `(day, sort_order)`. All IDs are exact UUIDs (no fuzzy matching).

| Endpoint | Notes |
|----------|-------|
| `POST /trips` | Body: `title` (required), optional `city`, `start_date`, `end_date`, `travelers` (1–50, default 1), `notes`, `items[]`. → `201` |
| `GET /trips` | List, newest first, paginated |
| `GET /trips/{trip_id}` | Trip with items. `404` if unknown |
| `PUT /trips/{trip_id}` | Replace top-level fields (items unchanged). Omitted optional fields reset to defaults |
| `DELETE /trips/{trip_id}` | Delete trip and all items. → `204` |
| `POST /trips/{trip_id}/items` | Body: `day` (≥1), `kind`, `title`, optional `sort_order`, `place_id`, `start_time`, `notes`. → `201`, `409` if over a budget cap |
| `PUT /trips/{trip_id}/items/{item_id}` | Replace an item |
| `DELETE /trips/{trip_id}/items/{item_id}` | → `204` |

```bash
curl -X POST http://localhost:8000/trips \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Da Nang long weekend", "city": "Da Nang", "travelers": 2,
    "items": [
      { "day": 1, "kind": "place", "title": "Dragon Bridge", "start_time": "19:00" },
      { "day": 1, "kind": "meal",  "title": "Bánh xèo dinner", "sort_order": 1 }
    ]
  }'
```

### `POST /trips/estimate` — budget estimator (stateless)

Calculates a line-item budget breakdown. Persists nothing.

| Field | Required | Notes |
|-------|----------|-------|
| `nights` | ✓ | ≥1 |
| `travelers` | ✓ | 1–50 |
| `city` | — | Informational only |
| `flight_total_usd` | — | Omit to exclude flights |
| `hotel_price_per_night_usd` | — | Omit to exclude lodging |
| `meal_style` | — | `budget` / `mid` / `fine` (default `mid`) |
| `activity_level` | — | `none` / `some` / `lots` (default `some`) |

Rates (USD/person/day): meals `budget`=$15, `mid`=$30, `fine`=$70; activities `none`=$0, `some`=$20, `lots`=$50; local transport $15/day; +10% incidentals buffer.

```bash
curl -X POST http://localhost:8000/trips/estimate \
  -H "Content-Type: application/json" \
  -d '{ "city": "Da Nang", "nights": 3, "travelers": 2, "flight_total_usd": 240, "hotel_price_per_night_usd": 90, "meal_style": "mid", "activity_level": "some" }'
# → flights 240, accommodation 270, meals 180, activities 120, transport 45 → total 941, per_person 470.5
```

### `GET|POST /trips/{trip_id}/budget` — caps vs spend

Saved per-category caps tracked against booked spend. Categories: `flights`, `hotels`, `activities`, `buffer`. `spent` is summed from linked non-cancelled bookings.

`GET` returns current caps vs spend, `total_cap`, `total_spent`, `total_remaining`, and `over_budget`.  
`POST` **replaces** all caps — omit a category to leave it uncapped. Once caps are set, adding an item whose linked booking exceeds a cap returns `409`.

```bash
curl -X POST http://localhost:8000/trips/<trip_id>/budget \
  -H "Content-Type: application/json" \
  -d '{ "flights": 700, "hotels": 500 }'

curl http://localhost:8000/trips/<trip_id>/budget
```

---

## Errors

All errors use one consistent envelope:

```json
{ "error": "NotFoundError", "message": "Booking not found", "status_code": 404, "path": "/bookings/<uuid>" }
```

Validation errors (422) add an `errors` array with per-field detail:

```json
{ "error": "ValidationError", "message": "Request validation failed", "status_code": 422, "path": "/airports", "errors": [ { "loc": ["query", "limit"], "msg": "...", "type": "..." } ] }
```

---

## ID formats

All resource IDs are UUIDs. Hotel UUIDs are stable forever (derived from seed data). Flight UUIDs are stable within a server session — get them from `/flights/search`. Bookings also expose a `confirmation_code` (6-char, accepted anywhere a booking UUID is).
