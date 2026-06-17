---
slug: weather-packing-day-suitability
status: proposed
owner: Minh Tran
created: 2026-06-17
---

# Weather-aware packing & day suitability (AGENT_IMPROVEMENTS #14)

## 1. Motivation

Give the agent two weather-derived helpers it can't reliably compute itself:

1. `GET /weather/packing?city=…&days=7` — clothing/gear suggestions derived from the
   forecast highs/lows/precipitation the `weather_service` already fetches.
2. A per-day `weather_score` (0–1) on `GET /trips/{id}/day-plan` — so the agent can
   suggest moving indoor activities to low-score (rainy/uncomfortable) days.

Both are pure computations over the existing Open-Meteo forecast — no new provider, no
new persistent state.

## 2. Non-goals

- No new external dependency or API key (reuse `weather_service.get_weather`).
- No precipitation **amount** modelling — the forecast only exposes
  `precipitation_probability_max`; use that.
- No schema/migration changes (both deliverables are additive response fields).
- No change to the `/trips/{id}/day-plan` request contract — only the response gains a field.

## 3. Success Criteria

- `GET /weather/packing?city=Hanoi&days=7` returns 200 with location echo + forecast
  summary + categorized suggestions; 404 on unknown city, 502 on upstream failure
  (same envelope as `/weather`).
- `GET /trips/{id}/day-plan?date=…` response includes `weather_score: float | None`,
  populated when the trip has a `city` and the date is within the forecast window,
  `None` otherwise (city unset / date out of window / upstream error — degrade silently
  like the existing routing annotation).
- `weather_score = round(clamp(0.5·comfort + 0.3·(1−precip_penalty) + 0.2·(1−code_severity), 0, 1), 2)`.
- Full suite green: `.venv/bin/python -m pytest tests/ -q` and `ruff check app`.

## Design decisions (locked at intake)

- **Score model** = weighted blend (temp comfort + precip probability + WMO-code severity).
  - `mean_temp = (temp_min_c + temp_max_c)/2`; comfort = 1.0 in [18,26]°C, linear decay to
    0 at ±12°C past the band edges.
  - `precip_penalty = (precipitation_probability_max or 0)/100`.
  - `code_severity`: clear 0.0 · partly-cloudy 0.1 · overcast 0.2 · fog/drizzle 0.4 ·
    rain/showers 0.5 · heavy rain 0.7 · freezing rain 0.8 · snow 0.7 · thunderstorm 1.0 ·
    default 0.5.
- **Packing input** = mirror the existing `/weather` query contract:
  `GET /weather/packing?city=…&days=1..16` (default 3). NOT the path-style
  `/weather/{city}/packing` from the doc — chosen for consistency with `/weather`.

## 4. Tasks

### Task 1.1 — Packing response schema

```xml
<task id="1.1" wave="1">
  <files>app/schemas/weather.py</files>
  <action>Add PackingSuggestion (category: str, reason: str, items: list[str]) and PackingResponse (location: WeatherLocation; days: int; overall_low_c: float; overall_high_c: float; rainy_days: int; suggestions: list[PackingSuggestion]; attribution: str default same as WeatherResponse). All fields carry Field(description=…, examples=…) for parity with the newer-schema sweep. Extend AppBaseModel.</action>
  <verify>cd /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.claude/worktrees/weather-packing-day-suitability && .venv/bin/python -c "from app.schemas.weather import PackingResponse, PackingSuggestion"</verify>
  <done>Schemas import clean; fields described.</done>
</task>
```

### Task 1.2 — `weather_score` field on day-plan response

```xml
<task id="1.2" wave="1">
  <files>app/schemas/trip.py</files>
  <action>Add `weather_score: float | None = Field(default=None, ge=0, le=1, description="Day suitability 0–1 derived from the forecast; None when the trip has no city, the date is outside the forecast window, or weather is unavailable.")` to DayPlanResponse.</action>
  <verify>cd /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.claude/worktrees/weather-packing-day-suitability && .venv/bin/python -c "from app.schemas.trip import DayPlanResponse; assert 'weather_score' in DayPlanResponse.model_fields"</verify>
  <done>Field present, optional, bounded 0–1.</done>
</task>
```

### Task 2.1 — Scoring + packing derivation in weather_service

```xml
<task id="2.1" wave="2">
  <files>app/services/weather_service.py, tests/test_weather_packing.py</files>
  <action>Add pure helpers: `_code_severity(code: int) -> float` (mapping above), `compute_weather_score(day: DailyForecast) -> float` (blend formula, clamp 0–1, round 2), `_derive_packing(daily: list[DailyForecast]) -> PackingResponse-parts` building categorized suggestions from overall low/high + rainy-day count (rainy = prob ≥ 40 or precip/snow/storm code). Add async `get_packing(city: str, days: int | None = None) -> PackingResponse` that calls get_weather and assembles the response. New test file: unit-test compute_weather_score boundaries (clear-warm ≈ high, thunderstorm-cold ≈ low, clamp), _code_severity buckets, and get_packing via monkeypatching get_weather with a fake WeatherResponse (no network).</action>
  <verify>cd /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.claude/worktrees/weather-packing-day-suitability && .venv/bin/python -m pytest tests/test_weather_packing.py -q</verify>
  <done>Helper unit tests pass; get_packing returns categorized suggestions from a faked forecast.</done>
</task>
```

### Task 3.1 — `GET /weather/packing` route

```xml
<task id="3.1" wave="3">
  <files>app/routers/weather.py, tests/test_weather.py</files>
  <action>Add GET "/packing" on the existing weather router: same `city` (Query, min_length=1) + `days` (Query, ge=1, le=16, default 3) params as get_weather, response_model=PackingResponse, responses=error_responses(404, 422, 502), async, returns await weather_service.get_packing(city, days=days). Add router tests (monkeypatch weather_service.get_weather or _fetch_json like existing weather tests): 200 + suggestions for a known city, 422 on days=0, and that 404/502 propagate.</action>
  <verify>cd /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.claude/worktrees/weather-packing-day-suitability && .venv/bin/python -m pytest tests/test_weather.py -q</verify>
  <done>Endpoint returns packing payload; validation + error codes correct.</done>
</task>
```

### Task 3.2 — Populate `weather_score` in get_day_plan

```xml
<task id="3.2" wave="3">
  <files>app/services/trip_service.py, tests/test_trip_value_layer_service.py</files>
  <action>In get_day_plan, after building plan_items, compute weather_score: if trip.city is set, try `forecast = await weather_service.get_weather(trip.city, days=16)`, find the DailyForecast whose date == target_date.isoformat(), and set weather_score = weather_service.compute_weather_score(day). Wrap in try/except (swallow all errors → None, logger.warning) exactly like the routing block, so a missing/failed upstream never breaks the day-plan. Pass weather_score into DayPlanResponse(...). Add service tests: monkeypatch weather_service.get_weather to a fake forecast covering target_date (asserts a float in [0,1]); city=None → None; date outside forecast → None; get_weather raising → None.</action>
  <verify>cd /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.claude/worktrees/weather-packing-day-suitability && .venv/bin/python -m pytest tests/test_trip_value_layer_service.py -q</verify>
  <done>weather_score populated within window; None on city-unset / out-of-window / upstream error.</done>
</task>
```

## 5. Risks

- **Day-plan now depends on weather upstream.** Mitigated by swallow-to-None (mirrors the
  existing routing annotation) — no new failure path for the day-plan.
- **Forecast window is ~16 days from today**, so trips far in the future/past get
  `weather_score: None`. Documented in the field description; acceptable.
- **Public-contract commit gate.** New `/weather/packing` endpoint trips
  `hooks/risk-corroboration.sh` at normal lane — commit with
  `RISK_WARN_CATEGORIES="public-contract"` (memory: public-contract-hard-gate).

## 6. Status Log

- 2026-06-17 — Plan drafted (proposed). Worktree `weather-packing-day-suitability` off `v2`,
  baseline 515 tests green.

## Wave map

| Wave | Tasks | Parallelism | Disjoint files |
|------|-------|-------------|----------------|
| 1 | 1.1 weather schema, 1.2 trip schema | 2 parallel | `schemas/weather.py` vs `schemas/trip.py` |
| 2 | 2.1 service helpers + unit tests | single | `services/weather_service.py`, new `tests/test_weather_packing.py` |
| 3 | 3.1 route, 3.2 day-plan score | 2 parallel | `routers/weather.py`+`tests/test_weather.py` vs `services/trip_service.py`+`tests/test_trip_value_layer_service.py` |
