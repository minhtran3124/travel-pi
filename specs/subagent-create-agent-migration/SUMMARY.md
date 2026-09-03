# subagent-create-agent-migration — Summary

Lane: high-risk
Confidence: medium
Reason: Architecture-direction change — chuyển 5 subagent hand-rolled sang `create_agent` nhúng làm node (path B). Hard gates: external-provider behavior (đổi cách gọi model), existing-behavior (5 hành vi battle-tested phải giữ parity), high-blast (`agents/` core). Supervisor graph GIỮ NGUYÊN (không phải path C).
Flags: external-systems (model call path), existing-behavior (retry/tool-error/prompt/tool-filter parity), audit/security (mở đường PII middleware), weak-proof (chưa có golden parity test), multi-domain (5 subagent)
Affects: apps/api agent harness — `app/agents/subagents/_base.py` (factory), wiring trong `graph.py`; supervisor/reflection/HITL KHÔNG đổi
Input-type: new initiative
Route: high-risk — brainstorming (done qua spike) → xia2 (done: research-brief/COMPARISON) → writing-plans (bản này) → multi-agent review → using-git-worktrees → subagent-driven-development. Execution re-intake per wave.
Escalate: yes — architecture-redefinition (agent harness direction). Đây là PLANNING; execution cần human confirm hướng B trước wave 1.

> Kế thừa spike MIN-61 (`specs/agent-middleware-spike/`). COMPARISON.md §3 verdict: **B là đích đường dài**.
> Bản này là PLAN cho B, chưa execute. Mỗi wave re-intake khi thực thi.

### Intent

<!-- User's request verbatim at intake. Oracle for /intent-review. -->

Yêu cầu (verbatim, nối tiếp phiên spike MIN-61):

> "now, i want to spawn multiple-agents to review, start planning to migrate for path B."

Bối cảnh path B (từ COMPARISON.md): **hybrid** — 5 subagent (planner/concierge/journal/booking/budget)
chuyển từ hand-rolled `StateGraph` (`build_subagent`) sang `create_agent` nhúng làm node trong supervisor
`StateGraph` **giữ nguyên**. KHÔNG phải path C (subagents-as-tools/LLM-routing). Giữ deterministic
orchestration: reflection loop, tier-gate, plan→booking HITL. Giữ parity 5 behavior: node-level retry,
tool-error split (transient vs logic), dynamic prompt (`system_with_summary`), tool filtering
(`allow_episodic`), per-request model resolution (`get_agent_llm`). Mở khóa middleware ecosystem
(PII là bước 1).

### What changed

Chưa đụng `app/` — bản này là PLANNING + multi-agent review. Deliverable: `PLAN.md` (waves, pilot
`journal` trước), sau đó panel review adversarial, rồi revise.

### Rationale

COMPARISON.md verdict: B tốt hơn A đường dài (bám upstream + velocity năng lực) mà không hy sinh tính
tất định (khác C). Đi tăng dần, mỗi subagent verify parity trước khi mở rộng; PII là cầu nối từ DECISION A1.

### Alternatives considered

- **Path A (giữ custom)** — bác cho mục tiêu đường dài (COMPARISON §3); vẫn là fallback nếu parity không giữ được.
- **Path C (full subagents-as-tools)** — bác: mất routing tất định, regression độ tin cậy luồng booking.
- **Big-bang migrate cả 5** — bác: rủi ro parity không kiểm soát; chọn pilot-first (`journal`).

### Verify

<!-- Planning stage — evidence điền khi execute từng wave. -->

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| plan not executed — nothing to verify | `! test -e apps/api/app/agents/middleware.py` | 0 | asserts the migration's first artifact is absent, i.e. no wave has run (retrofitted 2026-09-03) |

### Rollback

- Feature-flag/factory song song: giữ `build_subagent` cho tới khi mọi subagent verify parity; revert = trỏ wiring về factory cũ + `git revert <sha>`.

### Harness-Delta

- none

### Not auto-verified

- Everything this plan proposes. No wave was executed: there is no middleware module and no v2
  factory on `main`. The row above is a truthful negative check, not evidence of shipped work —
  adding a passing test row here would claim work that does not exist.
