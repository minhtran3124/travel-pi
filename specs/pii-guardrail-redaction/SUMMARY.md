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

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| PII guardrail tests | `../../.venv/bin/python -m pytest tests/agents/test_pii_redaction.py -q` | 0 | 12 pass: redact_pii (email/card/Luhn/name-untouched/phone-untouched) + node in-place + graph e2e |
| Regression agents+memory | `../../.venv/bin/python -m pytest tests/agents/ tests/memory/ -q` | 0 | 171 pass — entry-node chèn không phá flow nào |
| Lint | `../../.venv/bin/ruff check app/agents/guardrails.py app/agents/graph.py tests/agents/test_pii_redaction.py` | 0 | clean |

### Rollback

- Gỡ guardrail node khỏi `graph.py` (trỏ `START → load_context` lại) + `git revert <sha>`. Node thuần, không migration/schema.

### Harness-Delta

- none
