---
slug: geocode-cache
lane: normal
confidence: high
status: active
owner: minhtran
created: 2026-07-04
---

# Geocode dedupe cache

Lane: normal
Confidence: high
Reason: transient Open-Meteo geocoding timeout handled correctly by MIN-49 fault-tolerance (retry → graceful fallback); observed inefficiency is the same city geocoded twice per tools-node and re-geocoded on every node retry. No hard gate.
Flags: #5 external-systems (Open-Meteo, pre-existing), #8 existing-behavior (adds caching to geocode_city)
Affects: weather_service.geocode_city — shared by /weather, /air-quality, /*/climate, /*/route, and the concierge/planner agent tools
Input-type: Change request (investigation → fix)
Route: normal — feature branch + tests; direct implementation (single-wave)
Escalate: no (direction confirmed by user: cache/dedupe geocoding)

## Intent

User invoked `/feature-intake` "to investigate issue" with a docker log showing the
`concierge` sub-agent firing 4 parallel tool calls; `get_weather` geocoded "Da Nang"
successfully, then `get_air_quality` geocoded the **same** city again and hit an
Open-Meteo `ReadTimeout` → `WeatherUnavailableError` (`UpstreamError`), which LangGraph's
`TRANSIENT_RETRY` retried at the whole-`tools`-node level (re-running all 4 tool calls).

After investigation the user chose: **"Cache/dedupe geocoding"** — add a cache to
`geocode_city` so the same city is not geocoded twice per node (and is not re-geocoded on
retry), halving Open-Meteo geocoding calls and the transient-timeout surface.

## Rationale

- The failure is **not a crash** — the system self-recovers (retry then graceful fallback).
  The fix targets the redundant geocoding that inflates the upstream-timeout surface and
  makes node retries re-fetch already-known coordinates.
- **Chosen: simple module-level result cache** (success results only), keyed by normalized
  city name. This resolves the two real problems: (a) node retry re-geocoding — the first
  successful geocode is cached so the retry is a hit; (b) cross-turn/repeat lookups. City
  coordinates are static, so no TTL/eviction is needed for this mock backend.

## Alternatives

- **In-flight async dedup (Future-keyed)** — also collapses the concurrent first-call race
  (two tools geocoding the same city simultaneously). Rejected as over-engineering for the
  observed problem: from the log the second geocode fires after the first completes, so a
  result cache already turns it into a hit; the extra Future lifecycle + event-loop handling
  is not justified. Revisit only if concurrent first-call double-geocoding is measured.
- **Reduce retry blast radius** (retry only the failed tool) — a LangGraph ToolNode
  architecture change; larger and riskier. Out of scope.
- **Do nothing** — rejected; user wants the redundant calls removed.

### Verify

| Check | Command | Exit | Notes |
|-------|---------|------|-------|
| geocode cache tests | `../../.venv/bin/python -m pytest tests/services/test_weather_geocode_cache.py -x` | | new file |
| weather/air-quality/climate/routing unaffected | `../../.venv/bin/python -m pytest tests/api/weather tests/services/test_routing_service.py -q` | | isolation fixture |

### Rollback

- Revert code: `git revert <sha>` (single reversible commit; no schema/migration).
</content>
</invoke>
