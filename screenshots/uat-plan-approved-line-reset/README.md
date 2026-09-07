# UAT — plan-approved-line-reset (PR #158)

**Date:** 2026-09-07
**Environment:** local Docker (`api-api-1` on the PR branch via bind mount, graph rebuilt; Postgres `api-db-1`), Next.js dev server on :3100 on the PR branch, real Supabase auth, real OpenAI. UI locale vi.
**Account:** `uat-copy-premium@example.com` (tier premium, seeded for PR #145's UAT).
**Runner:** scratchpad Playwright script (`uat2.cjs`, Node 24 + `@playwright/test` 1.61 chromium, 1280×900). Not checked in.

## Before (PR #145 UAT, `screenshots/uat-agent-system-copy-i18n/B3-*.png`)

Approve → the "Kế hoạch đã được phê duyệt. Tin đang tiến hành đặt chỗ." line was streamed, then erased by the booking hand-off `reset`; only the booking reply remained, and history never had the line.

## After

| # | Step | Expected | Result | Evidence |
|---|---|---|---|---|
| 1 | search flights HN→ĐN (vi), then "ok, book cho mình cái rẻ nhất đi" | HITL card Đồng ý / Để sau | PASS | `01-interrupt-prompt-vi.png` |
| 2 | click **Đồng ý** | no approval bubble; booking reply is the only bubble text; trail summary counts the approval | PASS — "Đã sắp xếp 2 việc cho chuyến đi · 2s" + booking reply asking for passenger details | `02-after-approve-collapsed-vi.png` |
| 3 | expand the trail summary | first row "✓ Đã duyệt · Tin đang tiến hành đặt chỗ" (green dot), then the booking agent's own step | PASS | `03-after-approve-trail-expanded-vi.png` |

Script assertions on `document.body.innerText`: `Đã duyệt` present after expanding; the old line `Kế hoạch đã được phê duyệt` absent everywhere.

## Notes

- The second trail row renders the generic "Đang xử lý…" label because the booking agent's first tool is not in the trail's `TOOL_FAMILY` map — pre-existing labeling, unrelated to this fix.
- Reject path was not re-captured here; it is unchanged (see PR #145 UAT B2) and covered by `tests/agents/test_system_copy.py`.
