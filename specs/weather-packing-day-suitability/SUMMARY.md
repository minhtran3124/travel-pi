<!--
  Canonical SUMMARY.md shape. Header block is machine-read by
  hooks/risk-corroboration.sh (Lane:) and the trust-metrics ledger.
-->

# weather-packing-day-suitability — Summary

Lane: normal
Confidence: medium
Reason: Public-contract flag (new GET /weather/{city}/packing + new weather_score field on the already-shipped DayPlanResponse), existing-behavior flag (modifies day-plan response), and multi-domain flag (weather ↔ trips) fired — 3 flags, no hard gate.
Flags: public-contract, existing-behavior, multi-domain
Affects: weather router/schema (new packing contract), trips DayPlanResponse (new field), trip_service↔weather_service coupling
Input-type: spec slice

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane.

### Intent

> 14. ⬜ Weather-aware packing & day suitability
>
> You already have `/weather` (and a new `/air-quality`). Add:
>
> - `GET /weather/{city}/packing?days=7` — returns clothing/gear suggestions derived from forecast highs/lows/precipitation
> - A `weather_score` (0–1) on each day inside `GET /trips/{id}/day-plan` — agent can use it to suggest reshuffling indoor activities to rainy days

## What changed

Added `GET /weather/packing?city=…&days=1..16` returning categorized clothing/gear
suggestions (essentials, hot/warm/mild clothing, rain gear, sun protection) plus a forecast
summary (overall low/high, rainy-day count), and an additive `weather_score` (0–1) on the
`/trips/{id}/day-plan` response computed from the trip's city forecast. Both derive purely
from the existing Open-Meteo `weather_service.get_weather`; the day-plan score degrades to
`null` on city-unset / out-of-window / upstream error, mirroring the existing routing
annotation. +21 tests.

### Rationale

Both deliverables are pure computations over the forecast the `weather_service` already
fetches — no new external dependency, no new state. Normal lane (not high-risk) because the
only client-visible changes are an additive new endpoint and an additive response field, both
reversible; medium confidence because the scoring formula and clothing-threshold mapping are
unspecified but have sensible defaults (temperature bands + precipitation/WMO-code rules).

### Alternatives considered

- Reshape into a richer `day-suitability` object vs. a flat `weather_score` float — deferred;
  the spec asks for a 0–1 scalar, keep it additive and minimal.

### Deviations

- Authorized drift (intake decision) — endpoint shipped as `GET /weather/packing?city=…`
  (mirrors `/weather`) instead of the doc's path-style `GET /weather/{city}/packing`.
- Rule 1 — correctness-review found clothing branches were mutually exclusive
  (`if/elif/else`), so a hot-by-day/cold-by-night destination got only hot-weather advice.
  Decoupled into independent `if`s + regression test. `app/services/weather_service.py`,
  `tests/test_weather_packing.py`.
- Rule 1 (×2, subagents) — post-edit ruff formatter stripped a not-yet-used import on first
  write; re-added once the usage was present (`weather_service.py`, `trip_service.py`).

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Full suite | `.venv/bin/python -m pytest tests/ -q` | 0 | 536 passed (515 baseline + 21 new) |
| Lint | `.venv/bin/python -m ruff check app tests` | 0 | All checks passed |
| Correctness review | reviewer agent (sonnet) over `git diff v2` | 0 | No runtime bugs; 1 low design defect fixed (clothing branches) |

### Rollback

- `git revert <sha>`

### Harness-Delta

- none
