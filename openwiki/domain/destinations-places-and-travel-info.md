---
type: domain
title: Destinations, places and travel information
description: The read-mostly travel-information surface — seeded cities, countries, airports, places and tips, visa rules, the static FX snapshot for currency conversion, the destination overview aggregate, live weather, climate normals and air quality from keyless Open-Meteo, road routing from OpenRouteService with an offline haversine fallback, the shared fuzzy name matching that resolves free text to canonical names, and the LLM-backed content translation store that localizes catalog text to the conversation language.
tags: [destinations, places, tips, visa, currency, weather, climate, air-quality, routing, open-meteo, openrouteservice, i18n, fuzzy-matching, domain]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-25T03:45:43.723Z
sources:
  - id: openwiki-source-4678d82768922ea16df209d7
    resource: repo://apps/api/app/core/text.py
  - id: openwiki-source-40f2abc8aa65142a3b2f0512
    resource: repo://apps/api/app/services/air_quality_service.py
  - id: openwiki-source-171bb7f57d02b9933fe4db91
    resource: repo://apps/api/app/services/climate_service.py
  - id: openwiki-source-c013607ef2ad13e647fb8459
    resource: repo://apps/api/app/services/content_translation_service.py
  - id: openwiki-source-3452496309945566c86d5b86
    resource: repo://apps/api/app/services/currency_service.py
  - id: openwiki-source-94268046cfdb3f64672e33dc
    resource: repo://apps/api/app/services/destination_service.py
  - id: openwiki-source-2f2b4565b67bde3783f51ddd
    resource: repo://apps/api/app/services/place_service.py
  - id: openwiki-source-b2dd4239e9606b4af65de244
    resource: repo://apps/api/app/services/routing_service.py
  - id: openwiki-source-0e963df9819283dc41664a41
    resource: repo://apps/api/app/services/tip_service.py
  - id: openwiki-source-c582f2ce09cea95c9e4017ed
    resource: repo://apps/api/app/services/visa_service.py
  - id: openwiki-source-41b70976e433ce7b0af3f31e
    resource: repo://apps/api/app/services/weather_service.py
  - id: openwiki-source-fbd9573b3a515ae531651926
    resource: repo://apps/api/app/tools/hotel_tools.py
  - id: openwiki-source-9b71423931b7b792806d2ab5
    resource: repo://apps/api/app/tools/place_tools.py
  - id: openwiki-source-72a49711fd807be2d859954b
    resource: repo://apps/api/scripts/generate_translations.py
  - id: openwiki-source-f5d1a4d3af341f3491fd2bfc
    resource: repo://apps/api/tests/api/info/test_visa.py
  - id: openwiki-source-65aa93e6e1e98c42085d4082
    resource: repo://apps/api/tests/api/weather/test_weather.py
  - id: openwiki-source-a3671fec51b64abc86eae5f3
    resource: repo://apps/api/tests/services/test_content_translation_service.py
  - id: openwiki-source-1ccd6b18e1891448cb327e9b
    resource: repo://apps/api/tests/services/test_routing_service.py
  - id: openwiki-source-85d31e39eb2fff2015eda9f2
    resource: repo://apps/api/tests/services/test_weather_geocode_cache.py
generated: { by: "claude-code", at: "2026-09-18T04:47:06.927Z" }
---

# Destinations, places and travel information

Everything on this page is read-only from the traveller's point of view and comes from two kinds of source: **seeded reference rows** (cities, countries, airports, hotels, places, tips, visa rules, FX) that `app/data/*.py` defines and the seeder loads (see [Data layer and migrations](../architecture/data-layer-and-migrations.md)), and **live external services** that are keyless or key-optional. The services live under `apps/api/app/services/` and are exposed both as REST routes and as tools for the planner and concierge specialists (see [Specialist sub-agents and the tool registry](../agent/specialists-and-tools.md)).

## Fuzzy name resolution

Free-text destinations rarely match seed names exactly, so nearly every service resolves input through `app/core/text.py`. `fold_diacritics` maps Vietnamese and Latin accents to ASCII (`đ` is mapped explicitly because it has no NFD decomposition), `match_score` returns 1.0 for an exact match, 0.9 for a prefix, 0.8 for a substring, otherwise a `difflib` ratio that counts only at or above 0.6, and `best_match` returns the top candidate or `None` for both empty input and no match. This is orthographic matching only: it tolerates typos and accents, not semantic aliases.

## Reference data services

- **Cities, countries, airports.** `GET /cities` is a paginated fuzzy search on name and country with `has_hotels`-style filters; `GET /airports` lists and looks up airports by code. Every seeded city has at least three hotels and three places, enforced at startup.
- **Places.** `PlaceService` resolves a free-text city and category to canonical values and, crucially, a **given-but-unrecognised city or category yields no results rather than all results**. Search supports rating and price-level filters (`price_level` matches a band exactly; `price_level_max` is a ceiling for budget queries), a recommended-only flag, name exclusion for follow-up requests, and six sort keys. `parse_nl_query` extracts city, category, minimum rating and price level from a natural-language query with keyword and regex rules and ignores unrecognised words. Places resolve by id or their `PLC-` short code, and `nearby_places` uses the haversine helper. Saved places and the trip shortlist are described in [Trips, itinerary and budget](trips-itinerary-and-budget.md).
- **Tips.** `TipService.get_tips` merges **country tips inherited by every city** with city-specific tips on top; a city resolves its own country, category and essential-only filters apply afterwards, the country summary rides along, and an unknown location returns an empty list, never a 404.
- **Visa.** `VisaService.get_visa` resolves a city (which yields its country) or a country fuzzily and returns `found: False` with a disclaimer rather than a 404 when nothing is known; a visa-required country is still `found`.
- **Currency.** `CurrencyService.convert` uses the seeded FX snapshot: unknown ISO codes are a 404 listing the supported codes, the rate is `rate(dst) / rate(src)`, the snapshot's `last_updated` is returned, and an unrecognised free-text `country` simply omits `local_currency` instead of failing.
- **Destination overview.** `DestinationService.get_overview` fuzzy-resolves the city (404 with a pointer to `GET /cities` otherwise) and aggregates top places, tips, hotel statistics and optionally live weather into one response, driven by an `include` set.

## Live weather, climate and air quality (Open-Meteo)

`weather_service.py` makes the app's real outbound HTTP calls. `_fetch_json` wraps every request with the configured timeout and turns any transport or status error into `WeatherUnavailableError` (502). Geocoding goes through Open-Meteo's geocoder with a **process-wide cache of successful results only**, keyed case- and whitespace-insensitively, so a retry after a transient failure reuses coordinates while a miss or typo stays retryable; tests clear it around every case because it is shared across services. `get_weather` returns current conditions plus a daily forecast (1 to 16 days), or a single day when `date` is given; a date beyond the 15-day horizon raises a `DomainValidationError` whose detail itself points to `get_climate`, because agent tools surface only the detail to the model. `get_packing` derives packing suggestions and rainy-day counts from the same forecast.

`climate_service.get_climate` fetches several years of daily history from the archive API (ending a few days ago to avoid the archive's lag, and subtracting whole days so a leap-day end date cannot raise), aggregates monthly normals, labels temperature bands and comfort, picks the best months, and caches the full response per rounded coordinate. `air_quality_service.get_air_quality` returns the current US AQI with pollutant levels and a short max-AQI forecast. All three share the geocoder and raise `CityNotFoundError` (404) for an unknown place. The weather and air-quality tools return side-panel artifacts (see [Agent chat endpoints, SSE streaming and side panels](../agent/streaming-and-side-panels.md)).

## Routing (OpenRouteService with a haversine fallback)

`RoutingService` computes legs between two places or two cities for `walk`, `bike` and `car`. Endpoints resolve a place by id or short code (404 if unknown or missing coordinates) and a city by a **confident** seed match (score ≥ 0.8, because short proper nouns like "Phu Yen" versus "Phuket" collide), otherwise by the Open-Meteo geocoder, which also handles diacritics and cities outside the seed. When `ORS_API_KEY` is set, each mode queries the matching OpenRouteService profile for real distance, duration and best-effort road geometry (malformed geometry only drops the map line); a malformed summary raises `RoutingUnavailableError`. Without a key the service falls back to the straight-line distance scaled by a 1.3 detour factor at a per-mode speed, with an attribution string that says so. `recommend_mode` picks walk up to 1.5 km, bike up to 8 km, else car. Results are cached per request shape **including whether the provider is enabled**, so an offline estimate is never served after a key is configured. `tests/services/test_routing_service.py` covers seed-versus-geocoder resolution and the geometry behaviour of both modes.

## Content translation

Catalog text is seeded in English. `ContentTranslationService.localize(entity_type, items, fields, language)` overlays stored translations from the `content_translations` table onto entities and, when rows are missing, translates every miss **in one structured LLM call** and writes the results back with `source="llm"`; the default language is an identity with no query and no model call, a translator failure or a count mismatch keeps the source text and writes nothing, and a second call for the same rows makes zero model calls. The translator reuses the `extract_memory` agent-config node name deliberately, because a new node name would seed a `NULL` model row and fail in Docker. It is used by the hotel and place tools to localize descriptions to the conversation language, by the dashboard for its Vietnamese view, and by the agent's code-authored system replies. `scripts/generate_translations.py` pre-fills `app/data/content_translations.<lang>.json` for every seeded place and hotel description so a fresh deployment never pays a runtime translation for seed data; the seeder loads those files with `source="seed"`. Bounded vocabularies such as weather descriptions and hotel amenities are localized by lookup tables in the side-panel layer instead.

## Failure semantics at a glance

| Situation | Result |
|---|---|
| Unknown city for weather, climate, air quality, overview | 404 `CityNotFoundError` with a hint to search `/cities` |
| Open-Meteo or ORS unreachable or malformed | 502 `WeatherUnavailableError` / `RoutingUnavailableError`; agent tools relay it as a transient upstream problem |
| Unknown visa or tip location | `found: False` or an empty list, never 404 |
| Unknown currency code | 404 listing supported codes |
| Unrecognised place city or category | Empty result set |
| Translation failure | Source-language text, no error |
