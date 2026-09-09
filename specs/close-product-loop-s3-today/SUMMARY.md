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

Nothing yet — this is the intake record. Planned delta: a **Today** tab on
`/trips/[tripId]`, visible only while `start_date ≤ today ≤ end_date` and otherwise showing a
"trip not in progress" empty state carrying the trip dates. The tab renders today's ordered
day plan with its travel-time annotations, current weather and air quality for the
destination, and walking/driving directions from the previous item to the next unstarted one.

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

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| Intake evidence complete | `python3 .claude/scripts/verify_summary.py --lane close-product-loop-s3-today` | 0 | run at intake, before any implementation | |

### Not auto-verified

- The "unstarted" decision matches traveller expectation — reached traceability; the rule is
  grounded in the schema and the day-plan ordering, but no user has exercised the tab yet.
  Browser UAT at `finishing-a-development-branch` is what raises this to truth.

### Rollback

- `git revert <sha>` — the slice is additive frontend work on its own branch.

### Harness-Delta

- none
