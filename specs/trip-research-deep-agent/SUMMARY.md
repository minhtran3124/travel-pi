# trip-research-deep-agent — Summary

Lane: high-risk
Confidence: medium
Reason: Three manifest hard gates fire — `external-provider` (adds the `deepagents` runtime dependency to `apps/api/requirements-ai.txt`), `public-contract` (a new REST route to start/read a research job), `authorization` (the job is scoped to the signed-in owner of the trip). Direction is clear; four design forks have sensible defaults but change the shape of the work, so a human confirms them before planning.
Flags: external-provider, public-contract, authorization, existing-behavior, multi-domain
Affects: apps/api/requirements-ai.txt (dependency manifest); new module apps/api/app/research/ (deep agent graph + job); new router (public contract: start / status / files / SSE progress); app/agents/supervisor.py + prompts/supervisor v14 + route_tasks (chat entry, routing hop only); app/tools registry (read tools reused, no change intended); apps/web trip page + chat suggestion chip + stream contract in apps/web/src/lib/stream (lockstep); LangGraph Postgres store (new `research` namespace, no migration)
Input-type: new initiative

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> merge it, checkout to main branch, pull latest code and intake for trip-research-deep-agent

Scope-deciding sentences from the same session (2026-09-18, the deepagents assessment the user accepted by asking for "bước 1" and now this intake):

> Cái nên build: Trip Research job. Từ trang trip, user bấm "Research this trip" (hoặc gõ trong chat, supervisor route sang). Backend tạo job chạy vài phút. Agent nghiên cứu theo từng chiều (flights, stays, per-day plan, visa/entry, mùa/thời tiết, budget), tự chấm theo rubric, ra một dossier nhiều file. User xem, sửa ("ngày 3 nhẹ hơn"), rồi duyệt để agent ghi vào trip thật (itinerary items, shortlist). Dossier tồn tại qua nhiều phiên.

> Ranh giới rõ: không đụng 5 specialist, không đụng supervisor, không thay `plan_node`. Job là graph thứ hai, endpoint riêng, checkpointer/store dùng chung.

> Tái dùng 100% tool từ `app/tools` (read tools của planner + concierge + RAG). Không viết tool mới.

Route: brainstorming (E001–E004 decided) → xia2 Deep ✅ research-brief.md + design.md (2026-09-18) → writing-plans → subagent-driven-development on `feat/trip-research-deep-agent` → correctness/intent review → PR
Escalate: resolved 2026-09-18 — E001 StoreBackend · E002 BackgroundTask + poll + SSE progress in v1 · E003 both chat and trip page · E004 propose-only. Confidence after decisions: high for direction; ceremony stays high-risk.

## What changed

<pending — intake only>

### Rationale

The chat harness caps a turn (recursion 25, 12 tool rounds, ledger 4, 1 revision), which is exactly where "plan my whole trip end-to-end" fails today; a long-running job with an isolated-subagent harness, a file-backed dossier the user edits, and a rubric-driven self-check is the one place `deepagents` adds capability the repo does not already hand-roll (`specs/agent-middleware-spike/DECISION.md` deferred `create_agent` for the specialists; that decision stands).

### Alternatives considered

- Extend the chat harness (raise budgets, add a "research" specialist) — rejected: re-hits the same ceilings and mixes a minutes-long job into a turn-based SSE contract.
- Managed Deep Agents hosting — rejected: provider-agnostic design, per-user JWT auth, Docker-resident data and RAG; MDA needs its own identity/hosting and a LangSmith key.

### Deviations

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| Intake record shape | `python3 .claude/scripts/verify_summary.py --lane trip-research-deep-agent` | — | run after escalations are decided | |

### Not auto-verified

- none yet (intake only)

### Rollback

- `git revert <sha>` per commit; if StoreBackend is chosen, delete the `("users", <user_id>, "research", <trip_id>)` namespace — no schema change.

### Harness-Delta

- none
