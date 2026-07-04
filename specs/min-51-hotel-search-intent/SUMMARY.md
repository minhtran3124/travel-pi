---
slug: min-51-hotel-search-intent
created: 2026-07-04
owner: Minh Tran
linear: MIN-51
---

# MIN-51 — Hotel search shouldn't force the booking flow — Intake

Lane: normal
Confidence: high (approach confirmed 2026-07-04 — Option A)
Reason: 2 flags (existing-behavior, weak-proof); changes agent intent routing + hotel tool binding + supervisor/concierge prompts — no schema/API-contract change, no hard gate. Design fork resolved: user chose Option A.
Flags: existing-behavior, weak-proof
Affects: agent intent routing + tool registry — `app/agents/supervisor.py`, `app/tools/registry.py`, `app/agents/subagents/{concierge,booking}.py`, supervisor/concierge prompts. No public API contract or DB schema change.
Input-type: Change request (bug fix / behavior)
Route: design.md (fork) → /writing-plans → /using-git-worktrees → /subagent-driven-development
Escalate: yes — confirm approach (design fork below) before planning.

## Intent

> Linear MIN-51 (High): "Fix: Hotel search flow luôn hỏi thông tin booking dù user chỉ tìm kiếm thông tin"
>
> **Vấn đề:** khi user hỏi thông tin về khách sạn (tìm kiếm, so sánh, tra cứu), hệ thống luôn
> yêu cầu thông tin booking ngay lập tức.
> **Hành vi mong muốn:** Chỉ hỏi thông tin booking khi user thực sự có booking intent rõ ràng.
> Khi user chỉ tìm kiếm thông tin khách sạn (giá, vị trí, tiện ích, đánh giá…): không hỏi
> booking ngay — sau khi trả lời, đề xuất nhẹ nhàng hỏi user có muốn đặt phòng không.
> **Việc cần làm:** Rà soát logic phân loại intent (search vs booking) trong sub-agent xử lý
> khách sạn. Tách rõ 2 nhánh: (1) tra cứu → trả lời + soft prompt; (2) đặt phòng → mới hỏi
> thông tin booking. Kiểm thử: "khách sạn ở Đà Nẵng giá dưới 1tr", "tôi muốn đặt phòng khách sạn X".

## Root cause (investigated)

- `app/tools/registry.py:36` binds **all** `HOTEL_TOOLS` (`search_hotels` + `book_hotel`) to the
  `booking` sub-agent. Concierge (the retrieval agent) has no hotel tools.
- `app/agents/supervisor.py:82`: `next_node = "plan" if target == "booking" else target` — any
  routing to `booking` goes through the HITL plan-approval interrupt first.
- So a pure hotel-search query is classified as `booking` → plan interrupt → asks booking info.

## Design fork (needs user pick — see question)

- **A (recommended):** Move `search_hotels` (non-destructive) → concierge; keep `book_hotel`
  (destructive) on booking. Supervisor routes hotel *info* → concierge (answers + soft "want to
  book?" prompt), explicit *booking* → booking → plan interrupt. Matches existing architecture
  (concierge = retrieval, booking = transactions) and the ticket's "tách rõ 2 nhánh."
- **B:** Keep both tools on booking; move the plan-approval interrupt from supervisor-level to
  fire only when the destructive `book_hotel` is actually invoked (tool-level HITL). Bigger change
  to the HITL mechanism; keeps all hotel logic in one sub-agent.

**Decision (2026-07-04): Option A.** Move `search_hotels` → concierge; keep `book_hotel` on
booking; supervisor routes hotel info → concierge (+ soft booking prompt), explicit booking →
booking → HITL. Note: hotel search becomes free-tier accessible (concierge is not premium-gated,
booking is) — this is desired (searching info shouldn't require premium; only booking does).

### Verify

| Check | Command | Exit | Notes |
|---|---|---|---|
| _(fill on execute)_ | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/ -x` | | search→no interrupt; explicit book→interrupt |
