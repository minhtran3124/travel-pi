# Decision — Adopt/Defer từng ứng viên Agent Middleware

**Slug:** `agent-middleware-spike` · **Issue:** MIN-61 · **Ngày:** 2026-07-06
**Dựa trên:** [research-brief.md](./research-brief.md) (finding pivot: middleware **chỉ** chạy trong `create_agent`).

---

## Quyết định kiến trúc gốc (gate mọi thứ)

> **Có refactor 5 subagent từ hand-rolled `StateGraph` sang `create_agent` không?**

**Khuyến nghị: DEFER — không migrate trong/ngay sau spike.** Lý do:

- Middleware chỉ chạy trong `create_agent` → muốn *bất kỳ* middleware nào cũng phải migrate trước.
- Migrate = tái hiện 5 behavior battle-tested (deferred model, dynamic prompt, tool filtering,
  tool-error mapping, RetryPolicy) dưới dạng middleware — rủi ro regression trung-cao, va chạm
  2 non-goal (RetryPolicy, memory).
- Phần lớn cross-cutting concern **đã idiomatic** bằng LangGraph thuần → migrate chủ yếu để lấy
  *một* năng lực net-new (PII), mà PII **lấy được không cần migrate** (xem A1 dưới).

→ Cost/benefit của fork âm ở thời điểm này. Nếu tương lai cần **nhiều** middleware net-new
(guardrails đa dạng, HITL mở rộng, tool-selection động) thì mở **issue riêng high-risk** cho migration,
bắt đầu từ **một** subagent ít rủi ro nhất (ví dụ `journal`) làm pilot, verify parity, rồi mở rộng.

## Bảng quyết định ứng viên

| # | Ứng viên | Quyết định | Đường đi | Ưu tiên |
|---|---|---|---|---|
| **A1** | **PII / guardrails** (gap thật) | **ADOPT — nhưng KHÔNG qua middleware** | Ship `redact_pii()` thuần như guardrail node/pre-model step trong kiến trúc hiện tại; issue riêng, phối hợp MIN-53 | **Cao nhất** |
| A2 | Hợp nhất dynamic prompt (`wrap_model_call`) | **DEFER** | Chỉ khả thi sau migrate `create_agent`; lợi ích = giảm lặp, không phải năng lực mới | Thấp (chờ fork) |
| A3 | `LLMToolSelectorMiddleware` cho concierge | **DEFER** | Cần `create_agent`; chỉ đáng khi số tool concierge tăng đáng kể | Thấp–trung (chờ tín hiệu) |
| B1 | `ModelRetryMiddleware` | **REJECT** | Non-goal. `LLM_RETRY` (`RetryPolicy`) đã idiomatic | — |
| B2 | `SummarizationMiddleware` | **REJECT (giữ nguyên)** | Node `summarize` hiện tại đã fix edge-case tool-pairing (PR #58), battle-tested | — |
| B3 | Memory extraction (`after_agent`) | **REJECT** | Non-goal. Cố ý chạy ngoài graph (FastAPI BackgroundTask) để giảm latency | — |
| B4 | `wrap_model_call` (dynamic model) | **REJECT** | `get_agent_llm()` + `AgentConfigCache` đã mạnh hơn | — |

## Insight quyết định: tách PII khỏi fork

`PIIMiddleware` là giá trị #1, nhưng bị **khóa vào `create_agent`**. Thay vì migrate cả harness chỉ để
lấy PII, **ship năng lực PII như hàm/node thuần** — đúng idiom hiện tại (giống `summarize`, `retry`,
memory extraction đều là cơ chế tự cài, không phải middleware). Kết quả: bịt lỗ hổng bảo mật **ngay**,
không gánh rủi ro refactor, và giữ cửa mở cho `create_agent` sau này nếu nhu cầu middleware tích lũy.

## Việc làm tiếp (đề xuất, mỗi việc re-intake riêng)

1. **[Cao] Issue mới: PII guardrail (net-new).** `redact_pii()`/guardrail node xử lý tên/email/phone;
   phối hợp phạm vi PII của MIN-53. **Re-intake → high-risk** (audit/security hard gate khi ship control thật).
2. **[Thấp] Theo dõi tín hiệu fork `create_agent`.** Khi ≥2 middleware net-new thực sự cần (ví dụ guardrails
   nâng cao + tool-selection động), mở issue high-risk migration, pilot 1 subagent trước.
3. **PoC (tùy chọn, evaluation-only).** Script throwaway `create_agent + PIIMiddleware` dưới
   `specs/agent-middleware-spike/poc/` để chốt API ở version pin — không đụng `app/`.

## Status

- [x] Xác nhận API `create_agent` + `AgentMiddleware` ở version pin (Context7 1.x) → research-brief.md
- [x] Xác định tương thích StateGraph vs create_agent → **chỉ create_agent** (pivot answered)
- [x] Trả lời câu hỏi kiến trúc refactor → **DEFER**, cost/benefit ghi trên
- [x] Quyết định adopt/defer từng ứng viên → bảng trên
- [ ] PoC `PIIMiddleware` chạy thật (tùy chọn) — chưa chạy; đường đi ghi ở research-brief §PoC
