# close-product-loop — Summary

Lane: high-risk
Confidence: medium
Reason: new initiative spanning 7 product surfaces (FE + BE); hard gates authorization (share link exposes a trip to non-owners), public-contract (new routes: .ics export, share, booking↔trip link), data-loss/migration (share token / booking.trip_id schema); plus multi-domain, existing-behavior, weak-proof (FE e2e broken per deep review) → 4+ flags.
Flags: authorization, public-contract, data-model, external-systems(none new; flights/hotels stay simulated), existing-behavior, weak-proof, multi-domain
Affects: apps/web routes (trips/[tripId], bookings, new pages), apps/api routers flights/hotels/bookings/trips/visa/tips, bookings ↔ trips data model
Input-type: new initiative
Route: brainstorming → xia2 (Deep) → writing-plans → using-git-worktrees → subagent-driven-development; compound for durable decisions
Escalate: resolved (E001 = umbrella program with phased roadmap; E002 = booking stays premium, free tier search-only; see ESCALATIONS.md)

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

cho phan
"""
Vòng lặp sản phẩm chưa đóng
Agent làm được mọi thứ REST làm được, nhưng khoảng một phần ba tool của agent không có màn hình tương ứng. User free không đặt được gì.

Chưa bắt đầu — thiếu UI tìm và đặt vé/khách sạn, màn "Hôm nay" cho pha đang đi, trang recap sau chuyến, map trên trip, export .ics, share link, trang visa và tips.
"""

Source of the quoted text: `docs/reviews/2026-09-02-deep-review.md` §1 ("Parity chỉ đúng một chiều") and §4 "Đóng vòng plan → book → travel → recap" (items 1–5); the review itself splits these across đợt 2 (UI search/book + booking↔trip link) and đợt 3 (Hôm nay, recap, map, .ics, share, visa/tips).

## What changed

Intake only — no code. Classified as a high-risk umbrella initiative; scope confirmed by user (E001: umbrella design.md + per-slice PLAN.md; E002: no tier change). Next: brainstorming → design.md.

### Rationale

Seven independent surfaces cannot be one PLAN.md; the review already orders them (slice 1 = flights/hotels UI + booking↔trip). Share link and booking exposure touch authorization and public contracts, which force high-risk regardless of slice. Whether free users may book via UI is a product/tier decision the agent must not make.

### Alternatives considered

- Intake as `normal` for slice 1 only — rejected until the user narrows scope; the request as written is the umbrella.
- Reuse `specs/agent-platform-roadmap` (stalled 06-18, covers .ics/copy_trip) — kept as reference, not reopened; its scope is agent-side, this one is UI-side.

### Deviations

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| SUMMARY shape | `python .claude/scripts/verify_summary.py --lane close-product-loop` | | | |

### Not auto-verified

- "~1/3 agent tools have no screen" — reached traceability (review claim + web has 8 pages: /, auth×3, bookings, places, trips, trips/[tripId]); tool-by-tool parity matrix deferred to xia2.

### Rollback

- `git rm -r specs/close-product-loop` (intake artifacts only)

### Harness-Delta

- none
