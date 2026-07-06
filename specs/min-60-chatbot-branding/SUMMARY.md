# min-60-chatbot-branding — Summary

Lane: normal
Confidence: high  (resolved — ESCALATIONS E001 decided 2026-07-06)
Reason: Đổi cách bot tự xưng + welcome message + avatar/màu branding. ~2 flags, không hard gate. Blocker branding đã gỡ: tên chốt = **Tin**, bot xưng bằng tên. Scope mở rộng gồm avatar/branding (chạm apps/web UI).
Flags: existing behavior, weak proof, cross-platform (avatar/branding trên FE)
Affects: agent system prompts (cách bot tự xưng), FE welcome message + avatar/branding (apps/web chatbot) — không đổi public API contract
Input-type: change request
Route: normal → /using-git-worktrees → /writing-plans (>2 files, multi-layer) → /subagent-driven-development
Escalate: resolved (E001 — tên chốt = Tin, xưng bằng tên, kèm avatar/branding)

## Decision (E001)

- **Tên chính thức:** Tin (Trợ lý Tìm–Đi–Nghỉ)
- **Xưng hô:** bot xưng bằng tên trong câu trả lời — "Tin gợi ý cho bạn..."
- **Scope MIN-60:** system prompt (cách xưng) + welcome message + avatar/màu branding (apps/web)

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

<!-- MIN-60 verbatim (Vietnamese, from the Linear ticket). Oracle for /intent-review. -->

Đặt tên & xưng hô cho chatbot (branding)

## Mục tiêu

Chốt một cái tên thân thiện, gần gũi, dễ nhớ cho chatbot du lịch để xưng hô khi giao tiếp với user (thay vì gọi chung chung là "trợ lý ảo").

> Tách ra từ MIN-54 vì đây là **quyết định sản phẩm / branding** (cần thảo luận & chốt), không phải task code thuần — không nên để nó chặn phần CSS/emoji của MIN-54.

## Bối cảnh

* Đặt tên giúp chatbot có "nhân cách", tăng sự thân thiện và gắn kết với user.
* Tên sẽ xuất hiện ở: welcome message, cách bot tự xưng trong câu trả lời, có thể cả avatar/branding sau này.

## Gợi ý tên (brainstorm ban đầu)

* **Tin** — Trợ lý Tìm - Đi - Nghỉ; ngắn, dễ thương, dễ nhớ.
* **Vali** — gợi liên tưởng hành lý / du lịch.
* **Đi Đâu** — thân thiện, đúng ngữ cảnh hỏi điểm đến.
* **Xê Dịch** — mang màu sắc "dịch chuyển", hơi trẻ trung.
* **Bay** — ngắn gọn, gợi chuyến đi.

(Danh sách mở, có thể brainstorm thêm.)

## Tiêu chí lựa chọn

* Dễ đọc, dễ nhớ, dễ phát âm với người Việt.
* Phù hợp tông giọng thân thiện của chatbot du lịch.
* Không trùng/nhầm với thương hiệu du lịch lớn đã có.
* Xưng hô tự nhiên trong câu (vd: "Tin gợi ý cho bạn...").

## Việc cần làm

- [ ] Brainstorm & shortlist 3-5 tên.
- [ ] Chọn tên chính thức (có thể khảo sát nhanh vài user nếu cần).
- [ ] Cập nhật cách xưng hô của bot trong system prompt.
- [ ] Cập nhật welcome message / các điểm chạm hiển thị tên.
- [ ] (Optional) Cân nhắc avatar / màu sắc branding đi kèm tên.

### Rationale

<!-- filled at ship time -->

### Alternatives considered

<!-- filled at ship time -->

### Deviations

<!-- filled during execution -->
