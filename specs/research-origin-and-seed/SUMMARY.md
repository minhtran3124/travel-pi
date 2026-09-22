# research-origin-and-seed — Summary

Lane: normal
Confidence: high
Reason: research launcher ask + run input line, supervisor v15 wording, one optional additive request field, web Start field, seed data rows; no access-control change, no migration, no new endpoint.
Flags: none
Affects: app/research (launcher, context, runner, flights skill), supervisor v15, research start request, apps/web Research tab, app/data seed
Input-type: change request

### Intent

> - muc 3: luon hoi diem xuat phat nếu thông tin này bị thiếu, ko bao giờ dc assume cho cái này
> - mục 4: đồng ý

Item 3 = a trip has no departure point and a live run invented DNA→DAD. Item 4 = Phu Quoc seed had
3 hotels (all 5★, USD 195+) and no restaurants or cafes.

## What changed

**Item 3.** Research runs in the background and cannot ask mid-run, so the ask happens before a
run is booked. Chat: with no `trip_facts.origin` (the supervisor's slot from what the traveller
said), the launcher replies `research_needs_origin`, sets `awaiting_user`, books nothing;
supervisor v15 routes the answer back to research with the place as `origin`. A finished or
running run still answers its status without an origin. The origin rides `ResearchContext.origin`
into the turn message as `Departing from: <place>`. REST: `ResearchStartRequest.origin` (optional,
additive); the Research tab's Start needs a non-blank "Where are you travelling from?" field. The
flights skill takes the origin only from that line; without it it does not search flights and says
so.

**Item 4 (subagent).** Phu Quoc: +5 hotels (1★ USD 15 … 4★ USD 110), +4 restaurants, +3 cafes, vi
descriptions for all 12; same uuid5 id scheme; existing rows unchanged. The live "no availability"
was the budget `max_price` excluding all three 5★ hotels, not the availability generator. Dev DB
re-seeded (`seed_all` merges by id).

### Rationale

"Never assume" leaves only the traveller's own words as a source: nothing on the trip or profile
holds a departure point, and the supervisor already lifts a stated origin into `trip_facts`.

### Alternatives considered

- A `trips.origin` column — rejected: a migration for a value the traveller states per trip in conversation; `trip_facts` already persists per thread (one thread per trip).
- Let the research agent ask mid-run — impossible: the run is a background job with no chat turn to ask in.

### Deviations

- Rule 1 — `tests/agents/test_reflection_research_guard.py` graph test now passes a known origin (it hit the new ask).

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| unit | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_research_node.py -q` | 0 | no/blank origin → ask, no start; status replies without origin; launch gets origin; failed before (ImportError) | SC-1 |
| unit | `cd apps/api && ../../.venv/bin/python -m pytest tests/research/test_runner.py tests/api/research/test_routes.py -q` | 0 | `Departing from:` only when known; REST passes trimmed origin | SC-2 |
| unit | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_supervisor_research_routing.py -q` | 0 | v15 origin-answer rule + example | SC-3 |
| unit (web) | `cd apps/web && pnpm vitest run src/components/trips/research` | 0 | Start disabled for empty/blank origin; POST body carries trimmed origin | SC-4 |
| unit | `cd apps/api && ../../.venv/bin/python -m pytest tests/data -q` | 0 | 6 passed (subagent) | SC-5 |
| behavior | real `search_hotels(max_price=120)` / `search_places(restaurant)` for Phu Quoc in `api-api-1` after re-seed | 0 | 5 hotels USD 15–110 and 4 restaurants, with ids | |
| full BE suite | `pytest --rootdir apps/api -c apps/api/pyproject.toml apps/api/tests` from a cwd without `apps/api/.env` | 0 | 3016 passed, 9 skipped | |
| full web suite + typecheck + lint | `cd apps/web && pnpm vitest run && pnpm exec tsc --noEmit -p . && pnpm lint` | 0 | 393 passed; 0 lint errors | |

### Not auto-verified

- A real model routes "Từ Sài Gòn nhé" back to research after the ask — prompt rule + example only; no multi-turn golden (the routing dataset is single-turn).
- The Research tab's new field was not screenshotted.

### Rollback

- `git revert <sha>`; dev DB seed rows are additive (remove by code PQC004–PQC008 / the new place ids if needed).

### Harness-Delta

- none
