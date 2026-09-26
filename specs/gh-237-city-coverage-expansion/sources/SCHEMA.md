# Provenance source files — shared schema

Every `*.json` file in this directory is checked by `apps/api/scripts/check_seed_sources.py`.
Each file has one of the three shapes below. **Every record carries `source_url`**: the page the
facts were read from (en.wikipedia.org, wikivoyage.org, commons.wikimedia.org, or ecb.europa.eu).

## 1. City files (japan.json, korea_taiwan.json, china.json, europe.json, oceania_me.json, usa.json)

A JSON list of city objects:

```json
{
  "city": {"name": "Osaka", "country": "Japan", "airport_codes": ["KIX", "ITM"],
           "latitude": 34.6937, "longitude": 135.5023, "source_url": "https://en.wikipedia.org/wiki/Osaka"},
  "hotels": [ /* 6-8 */ {
    "name": "...", "address": "street, district", "star_rating": 4, "price_per_night": 180,
    "currency": "USD", "amenities": ["Restaurant", "Gym"], "image_url": "https://upload.wikimedia.org/...",
    "rating": 4.5, "review_count": 2100, "description": "one or two sentences, English",
    "property_type": "Hotel", "chain": "Hyatt" /* or null */, "check_in_time": "15:00",
    "check_out_time": "11:00", "breakfast_included": false, "free_cancellation": true,
    "languages_spoken": ["English", "Japanese"], "source_url": "https://..."
  }],
  "places": [ /* 8+ ; >=5 attraction, >=2 restaurant|cafe */ {
    "name": "Osaka Castle", "category": "attraction", "description": "one or two sentences, English",
    "address": "...", "rating": 4.6, "review_count": 30000, "price_level": 1,
    "opening_hours": "09:00–17:00", "image_url": "https://upload.wikimedia.org/...",
    "tags": ["landmark", "history"], "is_recommended": true,
    "latitude": 34.6873, "longitude": 135.5262, "source_url": "https://en.wikipedia.org/wiki/Osaka_Castle"
  }],
  "city_tips": [ /* 3+ */ {"category": "transport", "title": "...", "content": "...",
                 "is_essential": true, "source_url": "https://en.wikivoyage.org/wiki/Osaka"}]
}
```

- `property_type` is one of: Hotel, Resort, Boutique Hotel, Villa Resort, Homestay, Hostel, Apartment.
- `category` (places) is one of: attraction, restaurant, cafe, shopping, activity, nightlife.
- `price_level` is 1–4. `star_rating` is 1–5. `rating` is 1.0–5.0.
- Coordinates are decimal degrees. Places must be within 60 km of the city centre.
- Tip `category` is one of: money, transport, best_time, safety, connectivity, etiquette, food, health, language, culture.
- `price_per_night`, `rating`, `review_count` and `price_level` are indicative. Keep them realistic for the star class and the city. Each city needs at least 2 hotels at or under $130 and at least 2 hotels of 4★ or above.

## 2. countries.json

```json
[{"country": "France", "summary": "2-3 sentences", "summary_source_url": "https://en.wikivoyage.org/wiki/France",
  "tips": [ /* 3+ */ {"category": "money", "title": "...", "content": "...", "is_essential": true, "source_url": "..."}]}]
```

## 3. foundations.json

```json
{
  "countries": [{"name": "France", "code": "FR", "region": "Europe", "latitude": 46.2, "longitude": 2.2, "source_url": "..."}],
  "visa": [{"country": "France", "visa_free_days": 0, "visa_on_arrival": false, "e_visa": false,
            "passport_validity_months": 3, "summary": "rule for Vietnamese passport holders, checked 2026-09",
            "source_url": "https://en.wikipedia.org/wiki/Visa_policy_of_the_Schengen_Area"}],
  "airports": [{"code": "KIX", "name": "Kansai International Airport", "city": "Osaka", "country": "Japan",
                "latitude": 34.4347, "longitude": 135.2440, "source_url": "..."}],
  "airlines": [{"code": "JL", "name": "Japan Airlines", "source_url": "..."}]
}
```

Airports must lie within 80 km of their city's coordinates. When the city is not in any city file,
the check uses the airport's own country centroid only for the range check.
