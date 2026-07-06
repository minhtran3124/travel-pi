# agent-middleware-spike — Summary

Lane: normal
Confidence: high
Reason: Spike đánh giá (research + PoC hẹp) chạm chủ đề PII/guardrails và một quyết định kiến trúc; non-goals đã rào các thay đổi rủi ro (không migrate, không đụng RetryPolicy/memory). Không hard gate nào bị kích.
Flags: audit/security (chủ đề PII, PoC hẹp chạm luồng sensitive-data), existing-behavior (đánh giá agent harness đang chạy — non-goals rào lại)
Affects: apps/api agent harness (agents/, memory/, clients/llm.py) — evaluation-only trong spike; không đổi public contract
Input-type: new initiative

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

<!-- User's request verbatim at intake. Oracle for /intent-review. -->

Yêu cầu: `/feature-intake https://linear.app/minhtran3124/issue/MIN-61/spike-djanh-gia-langchain-agent-middleware-cho-agent-harness-djoi`

MIN-61 — "Spike: đánh giá LangChain Agent Middleware cho agent harness (đối chiếu kiến trúc hiện tại)". Các câu quyết định phạm vi (verbatim từ issue):

**Phạm vi spike đề xuất:**
- Xác nhận API `create_agent` + `AgentMiddleware` ở version đang pin (dùng Context7 / docs 1.x), xác định middleware nào tương thích **StateGraph tùy biến** vs chỉ chạy trong `create_agent`.
- Trả lời câu hỏi kiến trúc: có refactor subagents sang `create_agent` không? Chi phí vs lợi ích. (Đây là fork lớn — có thể tách issue riêng.)
- PoC `PIIMiddleware` trên một luồng subagent (hoặc tương đương thủ công nếu không tương thích StateGraph), đo overlap với PII handling của MIN-53.
- Ghi kết quả vào `specs/<slug>/` + quyết định adopt/defer từng ứng viên.

**Non-goals:**
- KHÔNG thay `RetryPolicy` hiện tại.
- KHÔNG kéo memory extraction trở lại trong graph.
- KHÔNG migration toàn bộ sang `create_agent` trong spike này (chỉ đánh giá + PoC hẹp).

**Ứng viên giá trị cao (ưu tiên):** 1) `PIIMiddleware` (net-new, gap thật); 2) hợp nhất dynamic prompt qua `wrap_model_call`; 3) `LLMToolSelectorMiddleware` cho concierge.

## What changed

Không đụng `app/` — spike research-only. Đã tạo trong `specs/agent-middleware-spike/`:
- `research-brief.md` — finding pivot (Context7 1.x): **middleware chỉ chạy trong `create_agent`**, không gắn được vào custom `StateGraph`; map 5 behavior của `build_subagent` sang middleware; chi phí migrate.
- `DECISION.md` — quyết định kiến trúc **DEFER migrate `create_agent`**; bảng adopt/defer 8 ứng viên; insight tách PII khỏi fork (ship PII như hàm/node thuần, không cần middleware).

PoC `PIIMiddleware` chạy thật để **tùy chọn** (evaluation-only, dưới `poc/`) — chưa chạy.

### Rationale

Phần lớn cross-cutting concern (retry, memory extraction, model resolution, summarization) đã tự cài idiomatic bằng LangGraph → giá trị lớn nhất là năng lực NET-NEW còn thiếu (PII/guardrails). Middleware giả định `create_agent`; codebase dùng custom `StateGraph` → câu hỏi tương thích phải làm rõ TRƯỚC khi bỏ công refactor. Lane normal vì spike là research + PoC hẹp có rào non-goals, không hard gate.

### Alternatives considered

- **tiny lane** — bác: output >1 file (specs docs) và PoC hẹp chạm luồng PII (sensitive-data), không đủ "≤1 file & no new public callable".
- **high-risk lane** — bác: spike không ship control bảo mật, không migrate, không đụng auth/data/high-blast file; non-goals rào các thay đổi rủi ro. Nếu spike chuyển thành migration `create_agent` thật hoặc ship PII redaction production → re-intake sang high-risk.

### Deviations

- none

### Verify

<!-- Spike/intake — chưa có check chạy được. Điền khi PoC/research có artifact. -->

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| API middleware ở version pin | `grep -E 'langchain>=1\|langgraph>=1' apps/api/requirements-ai.txt` | 0 | Xác nhận `create_agent`/`AgentMiddleware` có sẵn |
| Subagent hand-rolled (không create_agent) | `grep -c 'create_agent' apps/api/app/agents/subagents/_base.py` | 0 hit | Xác nhận middleware KHÔNG reach subagent hiện tại |
| PoC PIIMiddleware chạy thật | — | — | Chưa chạy — tùy chọn, đường đi ở research-brief §PoC |

### Rollback

- `git revert <sha>` (chỉ có specs/ metadata ở bước này)

### Harness-Delta

- none
