# min-60-chatbot-branding — Test Matrix

Status: a row is `implemented` only when a re-runnable evidence artifact exists.

| # | Success criterion | Status | Evidence artifact |
|---|---|---|---|
| 1 | Bot tự xưng "Tin" trong prompt các sub-agent (không "trợ lý ảo") | implemented | `apps/api/tests/prompts/test_tin_identity.py` — asserts active `communication_style` chứa "Tin". `pytest tests/prompts/ -q` → 10 passed. Identity ở `communication_style/v4.md`, prepend qua `_base.py:93` → phủ 5 sub-agent. |
| 2 | Welcome + header (en & vi) giới thiệu "Tin" | implemented | `apps/web/messages/{en,vi}.json` greetingTitle/greetingBody/headerTitle chứa "Tin"; JSON hợp lệ (node parse check PASS). |
| 3 | Avatar chat mang dấu ấn "Tin" (1 nguồn dùng chung) | implemented | `AgentAvatar.tsx` monogram "T" (role=img aria-label="Tin"); `pnpm vitest run src/components/chat` → 26 passed (9 files), gồm `MessageList.render.test.tsx`. |
| 4 | Màu branding | implemented (reuse) | Tái dùng accent lime hiện có (`--color-lime`/`--color-lime-soft`); `globals.css` không cần token mới. Hue signature riêng cho Tin = việc `/impeccable` sau (xem PLAN Risks). |
| 5 | Visual xác nhận (welcome + avatar + 1 câu trả lời xưng "Tin") | pending | Cần dev server localhost:3000 (Supabase dummy env) + API; chưa chạy live. Automated tests phủ phần substance. |

## Notes / follow-ups

- `dialogLabel` (aria label của chat dialog, `messages/{en,vi}.json`) vẫn là "Travel Assistant"/"Trợ lý Du lịch" — chưa đồng bộ tên. A11y-only, không hiển thị. Cân nhắc đổi thành "Tin · ..." cho nhất quán (follow-up nhỏ).
- Path deviation: i18n messages ở `apps/web/messages/` (không phải `src/messages/`).

## Verify (commands run)

| Check | Command | Exit | Notes |
|---|---|---|---|
| BE prompts | `cd apps/api && ../../.venv/bin/python -m pytest tests/prompts/ -q` | 0 | 10 passed |
| FE chat | `cd apps/web && pnpm vitest run src/components/chat` (Node v24) | 0 | 26 passed, 9 files |
