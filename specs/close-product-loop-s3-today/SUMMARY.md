# close-product-loop-s3-today — Summary

Lane: normal
Confidence: high
Reason: Web-only slice over existing REST routes; no hard gate fires (no auth, authorization, migration, audit, external provider, public contract, or weakening validation), but it exceeds one file and adds new shared modules, so it is not tiny.
Flags: existing behavior
Affects: apps/web/src/app/trips/[tripId]/page.tsx (shared tab host), apps/web/messages/{en,vi}.json (parity-tested)
Input-type: spec slice

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

Umbrella intake (verbatim, 2026-09-08):

> Vòng lặp sản phẩm chưa đóng
> Agent làm được mọi thứ REST làm được, nhưng khoảng một phần ba tool của agent không có màn hình tương ứng. User free không đặt được gì.
> Chưa bắt đầu — thiếu UI tìm và đặt vé/khách sạn, màn "Hôm nay" cho pha đang đi, trang recap sau chuyến, map trên trip, export .ics, share link, trang visa và tips.

Slice continuation (verbatim):

> tiếp tục slice S2 di

This slice is S3, the màn "Hôm nay" (Today screen) named in the umbrella intake. Its scope is
fixed by the approved design `specs/close-product-loop/design.md` §5 S3.

## What changed

A **Today** tab on `/trips/[tripId]`, always visible. Inside the trip window it renders today's
ordered day plan with the travel-time annotations the backend already computes, current weather and
air quality for the trip's city, and directions from the previous item to the next unstarted one.
Outside the window it renders a "trip not in progress" state carrying the trip's dates, or a
no-dates variant. Zero backend: every data source was already a REST route and already typed in the
generated frontend schema.

Weather and air quality are localized from the numbers the responses already carry — the WMO
`weather_code` and the `us_aqi` integer — rather than from the API's English prose. Both are
published standards, so the frontend maps cannot drift from the backend's, and the tab speaks
Vietnamese without a `lang` parameter that would have made this a public-contract change.

### Rationale

Chosen lane is `normal`, not `high-risk`: every data source already exists as a REST route
(`GET /trips/{id}/day-plan?date=`, `GET /weather`, `GET /air-quality`, `GET /places/route`), so
the slice adds zero backend and trips no manifest hard gate. It is not `tiny` because it adds a
tab to the shared trip-detail page, a query-hook module, and strings to both message files.

**Resolves the design's open question on "unstarted".** The design left S3 to choose between
including `constraint` in the unstarted set and switching the selector to "first item whose
`start_time` is later than now". Code evidence settles it:

- `TripItem.start_time` is `str | None`, documented as "Optional local start time, e.g. '09:00'",
  free text with no validation and no timezone (`apps/api/app/schemas/trip.py:55`,
  `apps/api/app/db/models/trip.py:55`).
- `TripService.get_day_plan` orders a day's items purely by `sort_order`
  (`apps/api/app/services/trip_service.py:634`). `start_time` takes no part in ordering.

A selector keyed on `start_time` would therefore silently return nothing for the common case of
items with no time set, and could not compare a naive "09:00" against the traveller's actual
now. **Decision: keep `sort_order` as the ordering and widen the unstarted set to
`pending | booked | constraint`, excluding only `optional`.** That directly fixes the concern
the design raised — a fixed anchor such as a train departure is the item a traveller most needs
directions to. `start_time` may be displayed, never used to select.

### Alternatives considered

- **"First item whose `start_time` is later than now."** Rejected on the evidence above:
  the field is nullable, unvalidated free text with no timezone, and the day-plan endpoint does
  not order by it. Adopting it would make the tab's core affordance depend on data most trips
  do not carry.
- **Keep the design's original exclusion of `constraint`.** Rejected: it hides exactly the
  fixed anchors the feature exists to route the traveller toward.
- **Add a real progress state (a new `TripItemStatus` value or a `completed_at` column).**
  Rejected for this slice. It is a schema change, which would force the lane to `high-risk` and
  pull a migration into a slice the design scoped as frontend-only. Worth its own spec if
  manual "mark done" is ever requested.

### Deviations

- Rule 1 — Task 1.1 mirrors the local-date mechanism in `tripVisuals` instead of importing its
  `todayUTC` helper as the plan directed. That helper is module-private, reads the clock internally
  and returns a UTC timestamp rather than a date string, so it can neither be imported nor accept a
  supplied `now`. Exporting it would have meant editing a file outside the task's Files set.
  Commit `effd159`.
- Rule 2 — Task 1.3 added `Today.plan.travelToNext` for the day plan's `travel_to_next_minutes`
  annotation. It was not in the plan's key enumeration, but task 3.1 renders that field and the
  unit needs translating; omitting it would have forced a wave-3 catalog edit and a same-file
  conflict. Commit `f4eae36`.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| Intake evidence complete | `python3 .claude/scripts/verify_summary.py --lane close-product-loop-s3-today` | 0 | run at intake, before implementation | |
| Plan contract | `python3 .claude/scripts/check_plan_contract.py specs/close-product-loop-s3-today/PLAN.md` | 0 | | |
| Date and ordering rules across every anchor | `cd apps/web && pnpm test src/components/trips/today/todaySelectors.test.ts` | 0 | 16 tests | SC-1 |
| A constraint item can be next, an optional one never is | `cd apps/web && pnpm test -t "next unstarted" src/components/trips/today/todaySelectors.test.ts` | 0 | | SC-2 |
| Hooks call the right routes and stay disabled without input | `cd apps/web && pnpm test src/lib/query/today.test.ts` | 0 | 10 tests | SC-3 |
| Weather localizes from the WMO code, falls back on unknown | `cd apps/web && pnpm test src/components/trips/today/TodayWeatherCard.test.tsx` | 0 | | SC-4 |
| Air quality derives its band from us_aqi, falls back on null | `cd apps/web && pnpm test src/components/trips/today/TodayAirQualityCard.test.tsx` | 0 | every band boundary pinned at both edges | SC-5 |
| Directions render via RoutePanel, and fire no request without a place | `cd apps/web && pnpm test src/components/trips/today/TodayDirections.test.tsx` | 0 | | SC-6 |
| The tab shows the plan inside the window and the dated state outside | `cd apps/web && pnpm test src/components/trips/today/TodayTab.test.tsx` | 0 | | SC-7 |
| The chat Route panel is unchanged | `cd apps/web && pnpm test src/components/chat/panel/RoutePanel.test.tsx` | 0 | consumed, never modified | SC-8 |
| Both locales carry the same keys | `cd apps/web && pnpm test src/messages.parity.test.ts` | 0 | 54 leaf keys each | SC-9 |
| Frontend typechecks | `cd apps/web && pnpm exec tsc --noEmit` | 0 | | SC-10 |
| Frontend lint | `cd apps/web && pnpm exec eslint src` | 0 | one pre-existing warning outside this slice | SC-11 |

Every frontend command above is prefixed with `PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH"`.
Run together, the slice's eight test files total 71 passing tests.

### Not auto-verified

- The "unstarted" decision matches traveller expectation — reached traceability; the rule is
  grounded in the schema and the day-plan ordering, but no user has exercised the tab yet.
- Seven tab labels read acceptably at 390px — not reached. The tablist carries `overflow-x-auto`
  with `shrink-0` buttons so the page cannot widen the way it did at six tabs, but legibility is a
  browser question. Deliberately left to UAT.
- The Vietnamese WMO and AQI strings read naturally to a native speaker — reached traceability
  only; parity is machine-checked, wording is not.
- Directions on a real trip — reached traceability. `GET /places/route` needs a `place_id` on both
  items, which a hand-typed itinerary lacks, so the card's populated path needs a trip seeded with
  catalog places to exercise.

### Rollback

- `git revert <sha>` — the slice is additive frontend work on its own branch.

### Harness-Delta

- backlog — `commit-quality-gate.sh` audits the index of `CLAUDE_PROJECT_DIR` (the main checkout)
  rather than the repository the commit is running in, so a broken staged `SUMMARY.md` in one
  session blocks commits from every other worktree. It blocked this branch for work belonging to
  `specs/gh-173-supervisor-local-tips-fanout`, which this slice never touched.
- backlog — `tripVisuals.todayUTC` is the repo's local-date helper but is module-private and reads
  the clock internally, so it cannot be reused by anything that needs a supplied `now`. Exporting a
  shared `localIso(now)` would stop the next slice reimplementing it.
