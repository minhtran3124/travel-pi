# API Tests Reorg — by Feature Domain

Lane: normal
Confidence: high
Reason: No risk flags fire — change touches only `tests/api/` (no auth/authz/data-model/external/public-contract surface). Sole hazard is breaking pytest collection, which is proof-checkable by re-running the suite.
Flags: none
Affects: none (test layout only; no production code, no public contract)
Input-type: Maintenance
Route: direct mechanical refactor on current branch (`v2`) + full-suite proof — subagent fan-out unwarranted for pure file moves (mirrors the prior [[test-suite-reorg]] decision).
Escalate: no — grouping granularity was the only material fork; resolved at intake via AskUserQuestion → **Per-domain (fine)**, ~9 subfolders.

### Intent

> refactor more @tests/ with seperate more modules inside api, ex: trip, hotel, ....

Continuation of `test-suite-reorg` (which split `tests/` by **test layer**: unit / services / api / infra). This sub-splits the **`tests/api/` layer by feature domain**. Grouping confirmed at intake as **Per-domain (fine)** (one folder per router/domain; singletons get their own folder).

### Plan

Move the 20 `tests/api/test_*.py` files into 9 domain subfolders. Keep `tests/conftest.py` and `tests/__init__.py` at the `tests/` root — the 5 `from tests.conftest import …` absolute imports stay valid because they anchor at the package root, not at `tests/api/`. Add `__init__.py` to each new subfolder to preserve package import mode (the suite already uses `tests/api/__init__.py`).

| Domain | Folder | Files |
|---|---|---|
| Trips | `tests/api/trip/` | test_trips, test_trip_budget, test_trip_shortlist, test_trip_value_layer_api |
| Hotels | `tests/api/hotel/` | test_hotels, test_hotel_availability |
| Flights | `tests/api/flight/` | test_flights |
| Bookings | `tests/api/booking/` | test_bookings |
| Places | `tests/api/place/` | test_places, test_saved_places |
| Geo / locations | `tests/api/geo/` | test_cities, test_airports, test_destinations |
| Weather / environment | `tests/api/weather/` | test_weather, test_climate, test_air_quality |
| Travel info | `tests/api/info/` | test_tips, test_visa, test_currency |
| Routing | `tests/api/routes/` | test_routes |

### Verify

Baseline (pre-move, `tests/api` only): **540 passed, 0 failures, 0 collection errors**. Post-move must reproduce exactly: 540 passed in `tests/api`, 0 collection errors. Full-suite run must also stay green (no cross-layer import regressions).

### Deviations

(none yet)
