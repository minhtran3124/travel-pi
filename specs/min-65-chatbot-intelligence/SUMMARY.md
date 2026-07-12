---
slug: min-65-chatbot-intelligence
created: 2026-07-12
owner: Minh Tran
---

# MIN-65 — Intake & Record

Lane: normal
Confidence: high
Reason: Multi-layer agent change (state + supervisor + graph + nodes + tools + prompts + eval + FE i18n) → cần plan đầy đủ. Không hard gate: không auth, không migration DB, không external provider mới, không đổi public contract (`ChatResponse.suggestions` giữ shape list key). Nền tảng (store, extraction, suggestions, eval) đã ship và được map kỹ → high confidence.
Flags: existing-behavior (supervisor structured output, suggestions call sites), weak-proof (eval cần key thật để chạy baseline)
Affects: app/agents/{state,supervisor,graph,nodes,suggestions}.py, app/memory/store.py, app/tools/{_ranking,hotel_tools,flight_tools}.py, app/prompts/* (5 version mới), eval/*, apps/web/messages/*.json
Input-type: feature request (Linear MIN-65)
Route: research (3 agents) → HLD.md → DESIGN.md → PLAN.md (8 waves, 10 tasks) → chờ user review trước khi execute
Escalate: no

## Status

**Plan-only.** Artifacts: `HLD.md` (nghiên cứu + so sánh phương án), `DESIGN.md` (D1–D9 +
test matrix), `PLAN.md` (XML tasks). Chưa sửa code.

## Rationale

Áp decision-tree memory (working/semantic/episodic/procedural) cho từng loại thông tin:
gap thật duy nhất của memory là **working-memory slots** (`trip_facts` trong state) +
độ phủ injection của prefs; phần dài hạn đã ship (P1/P2). Reasoning giải bằng
secondary-intent bounded + dispatch node (zero LLM call thêm); suggestions giải bằng rule
engine deterministic giữ contract i18n; ranking bằng stable-sort re-rank trong tool.
Eval-first theo đúng note của ticket.

## Alternatives considered

- Adopt Mem0 / LangMem / Letta — rejected (HLD §3.1): hệ memory thứ hai song song
  checkpointer/store, quá tầm mock-backend; BaseStore + pgvector đã đủ cơ chế.
- Slot-extraction node riêng hoặc tool LLM-discretionary — rejected (HLD §3.2): +1 LLM
  call/turn hoặc lặp lại gap P1; gộp vào structured output supervisor là zero-cost.
- LLM-generated suggestions — rejected v1 (HLD §3.4): phá contract i18n key với FE.

### Verify

| Check | Command | Exit | Notes |
|---|---|---|---|
| (pending) per-task | xem PLAN.md `<verify>` rows | — | điền khi execute |

### Rollback

- Plan-only: xoá `specs/min-65-chatbot-intelligence/` nếu bỏ hướng này.
- Khi execute: mỗi task 1 commit → `git revert <sha>`; prompt rollback = flip `active.yaml` về version cũ (file cũ không bị sửa); không migration DB.
