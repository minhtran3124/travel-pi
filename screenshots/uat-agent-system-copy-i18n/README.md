# UAT — agent-system-copy-i18n (PR #145)

**Date:** 2026-09-07
**Environment:** local Docker (`api-api-1` on the PR branch via bind mount, Postgres `api-db-1`), Next.js dev server on :3100, real Supabase auth, real OpenAI.
**UI locale:** vi (cookie `locale=vi`); every message typed in Vietnamese.
**Accounts (seeded with `scripts/seed_supabase_user.py`):** `uat-copy-free@example.com` (tier free, id `0690c2b2-…`), `uat-copy-premium@example.com` (tier premium, id `693a43dc-…`).
**Runner:** scratchpad Playwright script (`uat.cjs`, Node 24 + `@playwright/test` 1.61 chromium, 1280×900). Not checked in.

## Incident reproduced

Free user, Vietnamese thread: search flights, then "ok, book cho mình cái rẻ nhất đi". Before the fix the tier gate replied in English ("Booking is a premium feature. Please upgrade your plan to book trips.").

## Cases

| # | User | Steps | Expected (cached vi translation) | Result | Evidence |
|---|---|---|---|---|---|
| A1 | free | "Tìm giúp mình chuyến bay từ Hà Nội đi Đà Nẵng ngày 20/12/2026, 1 người, ưu tiên giá rẻ" | flights found, reply in vi | PASS | `A1-free-search-flights-vi.png` |
| A2 | free | "ok, book cho mình cái rẻ nhất đi" | **Đặt chỗ là một tính năng cao cấp. Vui lòng nâng cấp gói của bạn để đặt chuyến đi.** | PASS | `A2-free-booking-upgrade-notice-vi.png` |
| B1 | premium | same search, then "ok, book cho mình cái rẻ nhất đi" | HITL prompt (Đồng ý / Để sau) | PASS | `B1-premium-interrupt-prompt-vi.png` |
| B2 | premium | click **Để sau** | **Đặt chỗ đã được hủy theo yêu cầu.** | PASS | `B2-premium-booking-cancelled-vi.png` |
| B3 | premium | "thôi book luôn cái rẻ nhất đi" → click **Đồng ý** | plan approved, booking agent continues in vi | PASS (see note) | `B3-premium-plan-approved-vi.png` |

Backend log for the run (`docker logs api-api-1`): `plan → END (booking cancelled)` for B2 and `plan → booking (approved)` for B3; no `SYSTEM_COPY` fallback errors (every reply was served from the `content_translations` cache — zero translator calls during the UAT).

## Notes

- **B3:** the "Kế hoạch đã được phê duyệt. Tin đang tiến hành đặt chỗ." line is emitted as a `token` on the `plan` node, but the booking sub-agent runs in the same turn right after it and its reply ("Mình chưa thể đặt ngay vì còn thiếu thông tin hành khách…") is what the bubble ends on. Same presentation as before this change (the English line behaved identically); not in scope.
- **Not covered in the UI:** `unknown_intent` (needs the router to return an invalid target) and `agent_error_fallback` (needs an LLM outage). Both are covered by unit tests (`tests/agents/test_system_copy.py`) and their vi translations were produced by the real LLM in the container (see PR #145 description).
- The `screenshot-in-report` case from the user (English gate reply in a Vietnamese thread) is A2, now Vietnamese.
