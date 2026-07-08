# min-54-chat-ui-polish — Summary

Lane: normal
Confidence: medium
Reason: Touches existing chat behavior across two domains (apps/web message CSS + communication_style system prompt); 2–3 flags, no hard gate.
Flags: existing-behavior, multi-domain, weak-proof
Affects: apps/web chat message rendering (spacing/line-height CSS) + apps/api communication_style prompt (shared across all 5 sub-agents via _base.py)
Input-type: change request

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

<!-- The user's request VERBATIM at intake (Linear MIN-54 description). -->

## Vấn đề

UI hiện tại của chat chưa tối ưu về mặt trình bày & giọng điệu, cần cải thiện để trải nghiệm gọn gàng, sinh động hơn.

## Các điểm cần cải thiện

### 1. Spacing / Typography

* Khoảng cách giữa các dòng (line-height) hiện đang lớn → cần giảm để nội dung gọn hơn, dễ đọc hơn.
* Khoảng cách giữa header (heading) và phần text bên dưới hiện đang nhiều → cần giảm margin/padding cho hợp lý.

### 2. Định dạng nội dung trả lời

* Chỉ **in đậm (bold)** những thông tin thực sự quan trọng, cần thiết (vd: tên khách sạn, giá, ngày giờ, địa điểm...).
* Tránh lạm dụng bold tràn lan gây rối mắt.

### 3. Emoji sinh động

* Câu trả lời nên có emoji phù hợp theo ngữ cảnh du lịch để tạo cảm giác thân thiện, sinh động (vd: 🏨 khách sạn, ✈️ chuyến bay, 🌴 điểm đến, 💰 giá cả, 📅 ngày tháng...).
* Dùng vừa phải, đúng chỗ, không lạm dụng.

### 4. Đặt tên cho chatbot

* Cần một cái tên thân thiện, gần gũi, dễ nhớ để chatbot xưng hô khi giao tiếp với user (thay vì chỉ là "trợ lý ảo" chung chung).
* Gợi ý một số tên có thể cân nhắc: **Tin** (Trợ lý Tìm - Đi - Nghỉ), **Vali**, **Đi Đâu**, **Xê Dịch**, **Bay** — cần chọn 1 tên phù hợp với định vị thương hiệu và thử nghiệm phản hồi user.

## Việc cần làm

* Điều chỉnh CSS line-height, margin/padding cho message bubble và heading.
* Rà soát lại prompt/response format để giới hạn bold chỉ ở thông tin quan trọng.
* Bổ sung hướng dẫn dùng emoji theo ngữ cảnh vào system prompt của chatbot.
* Chốt tên chính thức cho chatbot và cập nhật xưng hô trong các câu trả lời/welcome message.

## What changed

Web: tightened assistant markdown typography — `leading-relaxed`→`leading-normal` on the bubble + Streamdown block, and added explicit tighter heading/paragraph/list margins (arbitrary rem values) in `AssistantMarkdown.tsx`. Prompt: added `communication_style/v5.md` (copied v4, sharpened the bold rule to mark only the specific value, added an `### Emoji` subsection with contextual travel emoji used sparingly and skipped on bad-news), bumped `active.yaml`→5, logged in `CHANGELOG.md`. Naming ("Tin") untouched.

### Rationale

Normal lane rather than tiny: the change spans two domains (apps/web message-bubble CSS and the shared `communication_style` system prompt) and modifies already-shipped chat behavior, so it needs proof gates + two-stage review, but no hard gate fires (no auth/authz/data/security/external/validation/high-blast file).

### Alternatives considered

- Tiny lane (direct patch) — rejected: multi-domain + existing-behavior change warrants a plan and per-task review.

### Scope note — prior work already covers parts of MIN-54

- **#4 Naming ("Tin") is already DONE** (MIN-60, PR #68 → v3). `communication_style/v4.md` §Identity already sets the name "Tin" and welcome/avatar shipped in apps/web. Remaining work = verify only, not re-implement.
- **#2 Bold discipline is largely DONE** in v4.md §How to Format ("Bold the few things that matter most: prices, dates, names, the recommendation…"). May only need a light tightening pass.
- **#3 Emoji guidance is NOT present** in v4.md (zero emoji mention) → genuine new work, likely a new `communication_style/v5.md`.
- **#1 Spacing/line-height CSS is NOT done** → genuine new work in apps/web chat message rendering (streamdown/markdown styles).

### Deviations

- none

### Verify

<!-- Populated during implementation — one row per check actually run. -->

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Prompt tests (incl. test_tin_identity) | `cd apps/api && ../../.venv/bin/python -m pytest tests/prompts -x -q` | 0 | 11 passed; confirms active=v5 resolves and still contains "Tin" |
| Web typecheck | `cd apps/web && pnpm exec tsc --noEmit` | 0 | no errors |
| Live agent reply — emoji present | `curl -s POST localhost:8000/agent/chat` (Docker, real OpenAI key) | 0 | Short reply → `✈️`; long itinerary → `🌴🍜 … 🙂`; bold only on values. Confirms v5 active + emoji default-present after guidance strengthened + graph reload. |
| Visual (line-height spacing) | _not run_ — needs web dev server render; phase-level UAT | — | CSS class change; verify visually in `apps/web` |

### Rollback

- `git revert <sha>`

### Harness-Delta

- none
