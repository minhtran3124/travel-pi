# Test Suite Reorg — by Test Layer

Lane: normal
Confidence: high
Reason: No risk flags fire — change touches only `tests/` (no auth/authz/data-model/external/public-contract surface). Sole hazard is breaking pytest collection, which is proof-checkable by re-running the suite.
Flags: none
Affects: none (test layout only; no production code, no public contract)
Input-type: Maintenance
Route: direct mechanical refactor on current branch + full-suite proof (subagent fan-out unwarranted for pure file moves)
Escalate: resolved — initial confidence was low ("by type" ambiguous between test-layer vs feature-domain); human selected **by test layer** via intake question.

### Intent

> refactor @tests/ folder, seperate test with multiple sub-folder for each type.

Clarified at intake: "each type" = **test layer** (unit / service / api / infra), not feature domain. Confirmed via AskUserQuestion ("By test layer").

### Plan

Move 30 `test_*.py` files into four layer subfolders; keep `conftest.py` and root `__init__.py` at `tests/` root (conftest discovery + the 5 absolute `from tests.conftest import …` imports stay valid). Add `__init__.py` to each subfolder to keep package import mode consistent.

| Layer | Folder | Files |
|---|---|---|
| Pure logic (network-free, no TestClient) | `tests/unit/` | test_text, test_migrations, test_weather_packing |
| Service layer | `tests/services/` | test_trip_value_layer_service |
| HTTP / endpoint (TestClient) | `tests/api/` | test_air_quality, test_airports, test_bookings, test_cities, test_climate, test_currency, test_destinations, test_flights, test_hotel_availability, test_hotels, test_places, test_routes, test_saved_places, test_tips, test_trip_budget, test_trip_shortlist, test_trip_value_layer_api, test_trips, test_visa, test_weather |
| Cross-cutting / operational | `tests/infra/` | test_errors, test_logging, test_rate_limit_headers, test_operation_ids, test_health, test_meta |

### Verify

Baseline (pre-move): `2 failed, 615 passed`. The 2 failures (`test_meta::test_root_endpoints_is_list`, `test_operation_ids::test_operation_ids_are_handler_names`) are pre-existing dependency drift (FastAPI/Starlette route introspection), unrelated to this change. Post-move must reproduce **exactly**: same 2 failures, 615 passed, 0 collection errors.

### Deviations

- `test_currency` was shown under `unit/` in the illustrative intake preview, but it drives the TestClient (`/currency/convert`), so by the chosen layer principle it belongs in `api/`. Placed in `api/`.
