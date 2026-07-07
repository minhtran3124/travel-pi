# pii-guardrail-redaction (MIN-62) — Summary

Lane: high-risk
Confidence: high (scope confirmed by human)
Reason: Audit/security hard gate — thêm PII redaction cho user input trước khi tới LLM provider. Net-new security control; chạm luồng message + persisted state; tương tác với MIN-53 (name capture qua background extractor).
Flags: audit/security (PII redaction — hard gate), existing-behavior (chạm message flow + tương tác MIN-53 personalization)
Affects: apps/api agent harness — thêm guardrail node ở entry (`app/agents/graph.py`), file mới `app/agents/guardrails.py`; KHÔNG đổi supervisor/subagent/reflection
Input-type: change request (net-new security control, tách từ MIN-61 DECISION A1)
Route: high-risk — intake (bản này) → surface design fork (PII scope × MIN-53) → PLAN nhỏ → implement → test → PR (target v3, closes MIN-62)
Escalate: yes — 1 fork intent: "name detector" issue yêu cầu XUNG ĐỘT với MIN-53 (redact name sẽ phá background extractor). Cần human chốt scope PII trước khi code.

### Intent

<!-- User's request verbatim. Oracle for /intent-review. -->

> "merge PR and start for MIN-62"

MIN-62 (verbatim từ issue, tách từ MIN-61 DECISION A1): ship một **guardrail PII thuần (hàm/node
pre-model)** trong kiến trúc hand-rolled hiện tại — redact email, mask credit_card, custom detector
name/phone (phối hợp phạm vi PII của MIN-53). Non-goals: KHÔNG chờ/phụ thuộc migration create_agent;
KHÔNG dùng PIIMiddleware ở bước này. Success: PII redaction live pre-model trên ≥1 luồng subagent chạm
PII; test xanh.

### Design finding (grounded)

- Graph flow: `START → load_context → summarize → supervisor → subagents → reflection → END` (`graph.py:141-143`).
  Điểm chèn 1-lần sạch nhất = **guardrail node ở entry** (`START → pii_guardrail → load_context`).
- **Name capture (MIN-53) chạy qua background memory extractor** (`app/memory/extractor.py`,
  `extraction_runner.py`) — đọc persisted messages SAU response. → **Redact name ở entry sẽ phá MIN-53
  personalization** (extractor không còn thấy tên). Đây là xung đột với chữ "name detector" trong issue.
- `add_messages` reducer replace theo id → guardrail return human message redacted cùng id để thay tại chỗ
  (redact-in-place: raw PII nhạy cảm không persist, không re-gửi provider các lượt sau).

### Rationale (đề xuất)

Redact email/phone/credit_card in-place ở entry node; **KHÔNG redact name** (để MIN-53 extractor hoạt động).
Chờ human chốt scope (xem ESCALATIONS/AskUserQuestion) trước khi implement.

### Alternatives considered

- **Redact per-subagent (to-model-only)** — bác: 5 điểm, gần cách middleware đang defer, phức tạp hơn.
- **Redact-in-place at entry** — chọn: 1 điểm, raw PII nhạy cảm không lưu.
- **Redact name** — bác (đề xuất): phá MIN-53 background extractor. Chờ human confirm.

### Scope confirmed (human)

Redact **email + credit_card** (mask last-4, Luhn-gated). **KHÔNG** redact name (giữ MIN-53) hay phone.
Mode: **redact-in-place ở entry node** (`START → pii_guardrail → load_context`, replace theo id).

### Deviations

- **Rule 2 (security auto-add)** — redact PII ở router boundary trong `app/routers/agent.py` (2 handler,
  trước `append_message` + graph). Security review bắt: raw PII persist vào **conversation DB** (không chỉ
  checkpointer/LLM). Guardrail node giữ làm defense-in-depth. Ngoài file-set plan gốc (blast-radius warn) —
  intentional, là core security fix của MIN-62.

### Review fixes (2-persona panel: security + correctness)

- 🔴 **Card regex leak** (cả 2 reviewer): `"card 4111 1111 1111 1111 08/25"` (card+expiry) + dấu phân cách
  dot/newline/glued-to-letter đều lọt. Sửa: run rộng `\d[\d\s.\-]{11,}\d` + Luhn **window search** ưu tiên
  độ dài chuẩn (16/15/13/14/19 trước 18/17) → bắt card dù có expiry.
- 🟠 **Persistence leak** → Rule 2 ở trên.
- 🟡 **Field loss**: dùng `model_copy(update={"content"})` giữ id + name/additional_kwargs.
- Test bổ sung: card+expiry, dot/newline sep, glued-to-letter, no-id no-op, multimodal no-op, field-preserve,
  router persistence e2e.

### Verify

> Local: `apps/api/.env` hard-set `DATABASE_URL=postgres:5433` → TestClient lifespan fail. Chạy với
> `DATABASE_URL="sqlite:///..."` override (hoặc `make test`). `.env` cũng chứa **OPENAI key thật** — nên flag.

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| PII guardrail tests | `pytest tests/agents/test_pii_redaction.py -q` | 0 | 18 pass (incl. các case leak review bắt) |
| Router persistence | `DATABASE_URL=sqlite pytest tests/api/agent/test_agent_chat.py -q` | 0 | 13 pass (incl. redacted-persist e2e) |
| Regression | `DATABASE_URL=sqlite pytest tests/agents/ tests/memory/ tests/api/agent/ -q` | 0 | **248 pass** |
| Lint | `ruff check app/agents/guardrails.py app/agents/graph.py app/routers/agent.py tests/...` | 0 | clean |

### Rollback

- Gỡ guardrail node khỏi `graph.py` (trỏ `START → load_context` lại) + `git revert <sha>`. Node thuần, không migration/schema.

### Harness-Delta

- none
