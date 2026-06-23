---
slug: router-metadata-dedup
status: proposed
owner: Minh Tran
created: 2026-06-22
lane: normal
confidence: high
---

# Router metadata dedup — FastAPI bigger-applications follow-ups

> Outcome of the `/deep-research` comparison against
> <https://fastapi.tiangolo.com/tutorial/bigger-applications/> and 2024-2026
> FastAPI best practices. The codebase already **meets or exceeds** the tutorial
> (factory, aggregate router, `Annotated` deps, `generate_unique_id_function`,
> 3-handler error envelope, `lifespan`, `lru_cache` settings, `dependency_overrides`).
> Only three incremental, doc-backed gaps remained; this plan covers the two worth doing.

## 1. Motivation

Two patterns are endorsed by primary FastAPI docs but not yet applied:

- **P1 — lift shared `responses=` to the `APIRouter` level.** Today every route
  repeats `responses=error_responses(...)` (~50 call sites across 13 routers).
  Tutorial: *"instead of adding all that to each path operation, we can add it to
  the `APIRouter`."* Per-route `responses` **merge** with router-level ones, so the
  error codes common to *all* routes in a group can be declared once.
  Sources: [bigger-applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/),
  [APIRouter reference](https://fastapi.tiangolo.com/reference/apirouter/).
- **P2 — store tags in an `Enum`.** 16 routers use plain-string tags that can drift.
  Docs: *"you would want to make sure you always use the same tag… it could make
  sense to store the tags in an `Enum`."*
  Source: [path-operation-configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/).

Neither changes runtime behavior. P2 is engineered to leave the generated OpenAPI
byte-identical; P1 deliberately changes the OpenAPI *error documentation* (see Risks).

## 2. Non-goals

- **P3 (router-level `dependencies=`)** — skipped. Low value for a mock with no
  auth / cross-cutting deps by design. Revisit only if a genuine shared per-router
  concern appears.
- **No restructure to a by-domain layout.** Research *refuted* (0-3 votes) the claim
  that the current by-type layout (`routers/ services/ repositories/ schemas/`)
  diverges from best practice — it is explicitly endorsed for small-to-mid apps.
- No auth / pagination / rate-limiting (intentionally out of scope for the mock).
- No change to `operationId` generation (stays `route.name`; the FE TS client
  depends on current method names).

## 3. Success Criteria

1. A single `Tags` enum is the source of truth for every router tag; enum values
   equal today's tag strings, so `GET /openapi.json` tag names are unchanged.
2. Error codes shared by *all* in-schema routes of a group are declared once on the
   `APIRouter`; per-route `responses=` carry only route-specific extras.
3. `make test` stays green (663 tests).
4. The OpenAPI diff is reviewed and intentional: empty for P2; for P1, each route
   still documents a **superset-or-equal** of the error codes it documents today.

## 4. Tasks

Both concerns edit the `APIRouter(...)` constructor line in the same router files,
so they cannot run in parallel — execute as sequential phases (no `wave` attr).
Do **P2 first** (zero-risk) to shrink the diff before the P1 judgment work.

### Task 1 — Tags enum (P2)

```xml
<task id="1">
  <files>app/routers/tags.py, app/routers/*.py (all 16 group routers; not main.py)</files>
  <action>Add app/routers/tags.py with `class Tags(StrEnum)` (use `str, Enum` base for py3.10 compat). One member per existing tag; VALUES MUST EQUAL the current strings exactly: airports, cities, flights, hotels, places, tips, destinations, currency, visa, weather, air-quality, bookings, trips, health, meta, dashboard. Replace every `tags=["x"]` in the APIRouter(...) constructors with `tags=[Tags.X]`. Leave routers/main.py (no tags) and dashboard's include_in_schema=False untouched. Add the import + usage together in each file (ruff-on-edit strips imports added before use).</action>
  <verify>make test</verify>
  <done>All routers reference Tags.*; openapi tag names byte-identical to pre-change; tests green.</done>
</task>
```

Extra acceptance check for Task 1 (run once, not the per-task verify): capture
`/openapi.json` before and after and confirm an **empty** diff of the tag set.

### Task 2 — Lift shared responses to router level (P1)

```xml
<task id="2">
  <files>app/routers/flights.py, app/routers/hotels.py, app/routers/places.py, app/routers/bookings.py, app/routers/trips.py, app/routers/cities.py, app/routers/destinations.py, app/routers/weather.py, app/routers/currency.py, app/routers/tips.py, app/routers/visa.py, app/routers/air_quality.py, app/routers/airports.py</files>
  <action>Per router: compute the set of error status codes present on EVERY in-schema route of that group. Move that shared set into the APIRouter(...) constructor as responses=error_responses(<shared>). In each route decorator, keep only the route-specific extra codes (drop the now-redundant shared ones); if a route had only shared codes, remove its responses= entirely. Do NOT add a code to a route that did not have it (router-level responses merge into every route — only lift codes that were already on all of them, so no route gains a spurious documented error). Leave routers whose routes share no common code (e.g. mixed 422-only and 404+422) with only the truly-common subset lifted, or unchanged if the intersection is empty.</action>
  <verify>make test</verify>
  <done>No router repeats a shared error code on every route; per-route responses= hold only extras; tests green.</done>
</task>
```

Extra acceptance check for Task 2: diff `/openapi.json` error responses per
operation before/after and confirm each operation documents a **superset-or-equal**
set (never fewer) of error codes than before.

## 5. Risks

- **Public-contract surface (P1).** Lifting `responses=` changes the generated
  OpenAPI error documentation. The merge rule means a router-level code is added to
  *every* route in the group — only safe when that code was already on all of them,
  hence the "compute the intersection" instruction. Mitigation: the superset-or-equal
  acceptance check; `make test`. Note: per memory `public-contract-hard-gate`, the
  risk-corroboration hook may flag this — authorize at commit time if it does.
- **`StrEnum` availability.** `enum.StrEnum` is py3.11+. Local is py3.14 but Docker
  is py3.12 (memory `docker-py312-vs-local-py314`) — both fine, but to be safe use
  `class Tags(str, Enum)` which works on 3.10+. Run `make test-docker` before PR.
- **ruff-on-edit import stripping** (memory `ruff-on-edit-strips-unused-imports`):
  add `from app.routers.tags import Tags` together with its first use in each file.
- **No schema change** → no `travel.db` rebuild needed
  (cf. `stale-travel-db-breaks-suite-on-schema-change`).

## 6. Open question (decide before Task 1)

The deep-research run flagged: does the FE TypeScript codegen consume OpenAPI `tags`
for client method grouping? It does not matter for P2 as planned (enum values =
current strings → identical output), but confirm before any future change that would
alter tag *strings*.

## 7. Status Log

- 2026-06-22 — Plan drafted from `/deep-research` workflow `wf_6babc996-186`
  (17 sources, 23 verified claims). Status: **proposed**, awaiting review.
