# min-60-chatbot-branding — Escalations

Default: **deny-on-no-response**. No recorded decision → work stays blocked.

---

## E001

- raised_by: orchestrator
- date: 2026-07-06
- trigger: low-confidence
- question: Chốt tên chính thức nào cho chatbot để xưng hô (từ shortlist), và bot sẽ xưng "mình" hay xưng bằng tên?
- context: Toàn bộ code (system prompt + welcome message) bị chặn cho tới khi có tên chốt — đây là product/branding decision, không tự chọn thay user.
- options:
  - A) Tin (Tìm–Đi–Nghỉ) — ngắn, dễ thương, xưng hô tự nhiên "Tin gợi ý cho bạn..."
  - B) Vali — gợi hành lý/du lịch
  - C) Đi Đâu — đúng ngữ cảnh hỏi điểm đến
  - D) Xê Dịch — trẻ trung, "dịch chuyển"
  - E) Bay — ngắn gọn, gợi chuyến đi
  - F) Tên khác / brainstorm thêm trước khi chốt
- default_if_no_response: BLOCK
- decision: A) **Tin** — bot xưng bằng tên trong câu trả lời ("Tin gợi ý cho bạn..."); scope MIN-60 lần này gồm cả avatar/màu branding (option optional trong ticket).
- decided_by: Minh Tran
- decided_at: 2026-07-06
