# UAT — plan-approved-line-reset (PR #158)

**Date:** 2026-09-07
**Environment:** local Docker (`api-api-1` on the PR branch via bind mount, graph rebuilt; Postgres `api-db-1`), Next.js dev server on :3100 on the PR branch, real Supabase auth, real OpenAI.
**Accounts (seeded via `scripts/seed_supabase_user.py`):** `uat-copy-free@example.com` (free), `uat-copy-premium@example.com` (premium).
**Runner:** scratchpad Playwright script (`uat3.cjs`, Node 24 + `@playwright/test` 1.61 chromium, 1280×900); each case asserts on `document.body.innerText` before the screenshot. Not checked in.

## Before this fix (PR #145 UAT, `screenshots/uat-agent-system-copy-i18n/B3-*.png`)

Approve → "Kế hoạch đã được phê duyệt. Tin đang tiến hành đặt chỗ." streamed, then erased by the booking hand-off `reset`; only the booking reply remained and history never had the line.

## Cases — all PASS (5/5)

| # | Locale / user | Steps | Assertion | Evidence |
|---|---|---|---|---|
| C1 | vi / free | search HN→ĐN flights, then "ok, book cho mình cái rẻ nhất đi" | gate reply "Đặt chỗ là một tính năng cao cấp…" (PR #145 regression check) | `C1-free-upgrade-notice-vi.png` |
| C2 | vi / premium | same, HITL card → **Để sau** | bubble "Đặt chỗ đã được hủy theo yêu cầu."; no approval step | `C2a-interrupt-prompt-vi.png`, `C2b-reject-cancelled-vi.png` |
| C3 | vi / premium | "thôi book luôn cái rẻ nhất đi", HITL card → **Đồng ý**, expand trail | trail row "✓ Đã duyệt · Tin đang tiến hành đặt chỗ"; booking reply is the only bubble text; old line absent | `C3a-interrupt-prompt-vi.png`, `C3b-after-approve-collapsed-vi.png`, `C3c-after-approve-trail-expanded-vi.png` |
| C4 | vi / premium | reload the page, reopen the widget | persisted history: cancelled line kept, approve turn shows only the booking reply, no orphan "Kế hoạch đã được phê duyệt" | `C4-history-after-reload-vi.png` |
| C5 | en / premium | search, "ok, book the cheapest one", **Approve**, expand trail | trail row "✓ Plan approved · booking now"; old "Plan approved. Proceeding…" absent | `C5-after-approve-trail-expanded-en.png` |

Backend log: `plan → END (booking cancelled)` for C2, `plan → booking (approved)` then `node=booking` for C3/C5; no `SYSTEM_COPY` fallback errors.

## Observations (pre-existing, not changed by this PR)

- C5: the booking agent called `book_flight` before collecting passenger details, the tool rejected it, and the trail shows the family error row "Couldn't finish the flight search · Retry" before the agent asks for name/email/phone. The booking prompt could ask first; separate follow-up.
- C3: the booking agent's second trail row renders the generic "Đang xử lý…" because that tool is not in the trail's `TOOL_FAMILY` map.
- The activity trail (and therefore the approval step) is a client-side artifact of the live turn; after a reload (C4) the trail is not rehydrated for past turns, same as every other activity step today.
