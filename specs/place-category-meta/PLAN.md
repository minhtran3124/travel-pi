---
slug: place-category-meta
status: shipped
owner: Minh Tran
created: 2026-06-25
---

# Place Category Metadata (color + icon)

## 1. Motivation

`GET /places/categories` currently returns `list[str]`. Roadmap **A2** wants each
place category to carry a **color + icon** so the FE / dashboard can color-code
places consistently. Per intake (`SUMMARY.md`), the approach is a **static
name→{color,icon} metadata map** — no table, no migration, no `category_id` FK.
The string `category` and the seed-derived categories list are untouched.

Colors are **not invented**: they mirror the existing dashboard palette already
defined in `app/templates/places.html` (`cat_colors`), so dashboard + API + any
FE codegen share one source of truth (the "Sunset" system, DESIGN.md). Icon keys
are short lucide-style strings the FE maps to its icon set.

## 2. Non-goals

- No `categories` DB table, no migration, no `place.category_id` FK.
- No change to `Place` / `SavedPlace` / search response shapes — **only**
  `GET /places/categories` changes.
- No icon asset/binary handling — `icon` is a short string key.

## 3. Success Criteria

- `GET /places/categories` returns `list[PlaceCategoryInfo{name, color, icon}]`,
  sorted by `name` (same order as the old `list[str]`).
- Every seed-derived category has a metadata entry; an unknown category falls
  back to a neutral color/icon (never errors).
- A test asserts the new shape **and** full coverage of seed categories.
- `make test` green; `ruff check`/`format` clean.

## 4. Tasks

### Task 1 — Schema + static metadata map + service

```xml
<task id="1">
  <files>app/schemas/place.py, app/services/place_service.py, tests/api/place/test_place_categories.py</files>
  <action>
    1. In app/schemas/place.py add `PlaceCategoryInfo(AppBaseModel)` with fields
       `name: str`, `color: str` (hex, e.g. "#38bdf8"), `icon: str` (lucide key).
    2. In app/services/place_service.py add a module-level `CATEGORY_META: dict[str, tuple[str, str]]`
       (color, icon) mirroring app/templates/places.html `cat_colors`:
         attraction #38bdf8 camera · restaurant #fb923c utensils · cafe #fbbf24 coffee ·
         activity #34d399 ticket · nightlife #f87171 wine · shopping #c4b5fd shopping-bag
       plus a `_FALLBACK = ("#94a3b8", "map-pin")` neutral for any unmapped category.
    3. Change `PlaceService.categories()` to return `list[PlaceCategoryInfo]`: map each
       distinct category through CATEGORY_META (fallback when missing), preserving the
       existing sorted-by-name order.
    4. Add tests/api/place/test_place_categories.py: assert response items are
       {name,color,icon}; assert sorted by name; assert EVERY category from the seed
       data (place service distinct categories) has a non-fallback metadata entry;
       assert an unknown category resolves to the fallback (unit-level on CATEGORY_META).
  </action>
  <verify>.venv/bin/pytest tests/api/place/test_place_categories.py -q</verify>
  <done>Service returns typed PlaceCategoryInfo list; every seed category mapped; fallback covered; test green.</done>
</task>
```

### Task 2 — Router response_model + endpoint shape test

```xml
<task id="2">
  <files>app/routers/places.py, tests/api/place/test_places.py</files>
  <action>
    1. In app/routers/places.py change the GET /places/categories route
       `response_model=list[str]` → `response_model=list[PlaceCategoryInfo]`
       (import PlaceCategoryInfo from app.schemas.place; add+use the import together so
       ruff-on-edit does not strip it). Update the route docstring/summary to say it now
       returns name+color+icon. Body still just `return places.categories()`.
    2. Update the existing categories assertion in tests/api/place/test_places.py (if any
       asserts a list[str]) to the new object shape; add a 200-shape check that each item
       has name/color/icon keys and color is a "#rrggbb" string.
  </action>
  <verify>.venv/bin/pytest tests/ -k "categor" -q</verify>
  <done>Endpoint returns 200 with [{name,color,icon}]; old list[str] assertions updated; no other route changed.</done>
</task>
```

### Task 3 — Full suite + lint gate

```xml
<task id="3">
  <files>(none — verification only)</files>
  <action>Run the full suite + lint to confirm no regression from the contract change.
    If the public-contract commit gate blocks, authorize per [[public-contract-hard-gate]]
    with RISK_WARN_CATEGORIES="public-contract" (the shape change is intended + intake-authorized).</action>
  <verify>.venv/bin/pytest tests/ -q && ruff check app && ruff format --check app</verify>
  <done>Full suite green, lint clean.</done>
</task>
```

## 5. Risks

- **Public-contract change** (`/categories` element `str`→object). Intended +
  intake-authorized; FE codegen must regenerate types. Authorize the commit gate
  with `RISK_WARN_CATEGORIES="public-contract"` if it fires
  (see memory `[[public-contract-hard-gate]]`).
- **Icon representation fork** — chose **lucide-style string keys** (FE-agnostic,
  codegen-friendly, matches TREK convention) over emoji (which `tips.html` uses).
  If the FE prefers emoji, only `CATEGORY_META` icon values change (1-line each),
  contract shape unchanged.
- **`shopping`** has no TREK analogue → icon `shopping-bag` chosen locally.
- **Seed drift** — if a new place category is seeded later without a metadata
  entry, the coverage test (Task 1.4) fails loudly rather than shipping a silent
  fallback. That is the intended guard.

## 6. Status Log

- 2026-06-25 — PLAN drafted (status: active). Colors locked to `places.html`
  `cat_colors`; icons from lucide keys (TREK-informed).
- 2026-06-25 — **Shipped.** Tasks 1–3 done. `/categories` now returns
  `list[PlaceCategoryInfo{name,color,icon}]`. Touched: `app/schemas/place.py`,
  `app/services/place_service.py`, `app/routers/places.py`,
  `tests/api/place/test_places.py` (updated), `tests/api/place/test_place_categories.py`
  (new). Verify: 699 passed, lint clean (see SUMMARY ### Verify). status → done.
