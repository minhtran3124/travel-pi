<!--
  Header block is machine-read by hooks/risk-corroboration.sh (Lane:) and the
  trust-metrics ledger.
-->

# poi-library — Summary

Lane: high-risk
Confidence: low
Reason: New persistence entities (a saved-places store + a trip↔place M2M link) + new endpoints + multi-domain (places ↔ trips) + schema migration → 4 flags including the data-loss/migration hard gate; AND an unresolved architectural fork (keep `data/places.py` static catalog + add `saved_places`, vs unify into one table) → two materially different designs → low confidence.
Flags: data-model, public-contract, existing-behavior, multi-domain
Affects: places (data/places.py, schemas/place.py, place_service), trips (crud/trip.py, trip_service, schemas/trip.py), new tables (saved_places, trip_place_link); trip + place response contracts
Input-type: spec slice (roadmap A1) — design-fork → design.md required

> `Lane` drives **ceremony**. `Confidence` drives **interruption**. A hard gate forces
> `high-risk`. Low confidence / ambiguous direction escalates regardless of lane.

### Intent

> (CHECKLIST.md A1) Thư viện POI tái sử dụng — places là entity hạng-nhất (M2M với trips):
> place tồn tại độc lập, được link vào nhiều trip qua bảng join, thay vì nhúng cứng trong
> `trip_items`. Quyết định mô hình: giữ `data/places.py` (seed tĩnh) làm catalog gốc, thêm bảng
> `saved_places` (place do user/agent lưu) — hoặc hợp nhất. Bảng join `trip_place_link`.
> Trường POI giàu hơn cho saved place: `favorite`, `visited`, `links: list[str]`, `duration`.
>
> User (2026-06-18): "Merge PR và tiếp tục với A1".

## What changed

Reusable POI library (Option A — see design.md). **Wave 1:** a mutable `saved_places` store
(`app/schemas/saved_place.py`, `crud/saved_place.py`, `services/saved_place_service.py`) with
`POST/GET/list/DELETE /places/saved`, idempotent favorite/visited SET, dedup-by-distance (409),
soft-delete, `SPL-` short codes. **Wave 2:** a `trip_place_link` M2M shortlist + a
`place_service.resolve(place_id, source)` unifying catalog (seed) and saved places;
`POST/GET/DELETE /trips/{id}/places`; additive `TripDetail.places`. `data/places.py` catalog,
`/places` endpoints, and `trip_items` are **unchanged**. New tables only (no `ALTER`).

### Rationale

Chosen **Option A** (catalog + saved overlay) over unifying into one DB table, to preserve CLAUDE.md
"deterministic generation, never stored" and leave the existing `/places` read path untouched. The
trip↔place link is a NEW table (`trip_place_link`) distinct from `trip_items`, carrying a `source`
discriminator so the resolver knows catalog vs saved. favorite/visited are idempotent SET (not flip)
to fit the project's idempotency theme. Full reasoning in `design.md` §2; alternatives in `ESCALATIONS.md`.

### Alternatives considered

- **Option A — Static catalog + `saved_places` overlay:** keep `data/places.py` (231 seed POIs,
  deterministic IDs) as the read-only catalog; add a `saved_places` table for user/agent-created
  POIs; `trip_place_link` M2M references either. Preserves deterministic seed IDs; clear split.
- **Option B — Unify into one `places` table:** migrate the seed into the DB on startup; one table,
  one ID space. Simpler model but loses the "everything-generated-deterministically" ethos and
  touches the existing `/places` read path more.
- (To be decided in brainstorming.)

### Deviations

- Rule 2 — Added `DomainValidationError` (422) domain exception (`app/exceptions.py`) for invalid `source`; renamed from `ValidationError` to avoid shadowing `pydantic.ValidationError`. Commits `73165d2`, `1c6e6fa`.
- Rule 1 — `delete()`/`set_flag()` resolve `SPL-` short code → UUID before the repo write (else silent no-op). Found by final correctness review. Commit `17d0208`.
- Rule 1/3 — conftest repoints the `saved_place_service` module singleton at the temp DB (resolver uses the singleton, not DI), mirroring `flight_service.set_index_repo`. Commit `73165d2`.

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Full suite | `.venv/bin/python -m pytest tests/ -q` | 0 | 594 passed (573 baseline; +21) |
| Saved-places | `.venv/bin/python -m pytest tests/test_saved_places.py -q` | 0 | 12 passed |
| Shortlist | `.venv/bin/python -m pytest tests/test_trip_shortlist.py -q` | 0 | 9 passed (incl. same-place-two-trips M2M) |
| Lint | `ruff check app && ruff format --check <touched>` | 0 | clean |

### Review gates

- Per-wave spec + quality + correctness review (sonnet) ✅.
- Final adversarial correctness review (whole diff) — 1 P1 fixed (`SPL-` short-code delete/flag no-op) + test; P2 (redundant SELECT) / P3 (city-None dedup) accepted as perf/documented.
- Final intent review (blind to PLAN) — faithful; added a test locking the core "same place across multiple trips" M2M promise (`2548fdb`).

### Rollback

- New tables are additive; `git revert <sha>` + drop unused tables. Detail after design.
