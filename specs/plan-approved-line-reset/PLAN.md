# plan-approved-line-reset — Plan

## 1. Goal

Option B (ESCALATIONS E001): approving a booking plan no longer appends a chat `AIMessage`; approval is shown as a status step in the assistant turn's activity trail. No `reset` fires, the booking reply is the only bubble text, and persisted history matches the UI.

## Global Constraints

- No SSE contract change (no new event kinds/fields).
- `plan_approved: True` state flag and the reject path's cancel line are unchanged.
- Remove the now-dead `plan_approved` system copy (constant + key + tests); do not touch other copy.
- FE: status rendered through the existing activity-trail family mechanism (no raw tool name in UI), localized en + vi.

## 2. Tasks

### Task 1.1 — Plan node: approval is state, not a message (wave 1)

- **Files:** apps/api/app/agents/nodes.py, apps/api/app/agents/constants.py, apps/api/app/agents/copy.py, apps/api/tests/agents/test_system_copy.py, apps/api/tests/api/agent/test_stream_events.py
- **Action:** In `plan_node` approve branch drop the `messages` update (keep `plan_approved: True`, `goto="booking"`). Delete `PLAN_APPROVED_MSG` and the `plan_approved` `SYSTEM_COPY` key. Update the plan-node test to assert approve emits no message. Add a mapper test: plan update WITHOUT messages followed by a booking chunk yields `start, subagent, token, done` (no `reset`).
- **Verify:** `cd apps/api && DATABASE_URL="sqlite:///$(mktemp -d)/t.db" ../../.venv/bin/python -m pytest tests/agents/test_system_copy.py tests/agents/test_hitl_plan.py tests/api/agent/test_stream_events.py -q`
- **Done:** tests green; `grep -rn plan_approved app/agents/copy.py` empty.
- **Criteria:** SC-1, SC-2
- **Interfaces:** Consumes the existing HITL plan node and the mapper reset rule; produces `app/agents/nodes.py`, `app/agents/constants.py`, `app/agents/copy.py`.

### Task 1.2 — FE: approval status step in the activity trail (wave 1)

- **Files:** apps/web/src/components/chat/useAgentStream.ts, apps/web/src/components/chat/AgentActivityTrail.tsx, apps/web/messages/en.json, apps/web/messages/vi.json, apps/web/src/components/chat/useAgentStream.stream.test.tsx, apps/web/src/components/chat/AgentActivityTrail.test.tsx
- **Action:** In `resume(approved)`, when `approved` is true push a synthetic `ActivityStep` `{ id: "plan-approved:<assistantId>", tool: "plan_approved", subagent: "booking", status: "ok" }` onto the assistant message before streaming. Map `plan_approved` → family `approved` in `TOOL_FAMILY` with a check icon and labels `Chat.activity.approved` (en "Plan approved · booking now", vi "Đã duyệt · Tin đang tiến hành đặt chỗ") + `Chat.activity.error.approved`. Tests: resume(true) adds the step; trail renders the localized label for it.
- **Verify:** `cd apps/web && export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm exec vitest run src/components/chat/useAgentStream.stream.test.tsx src/components/chat/AgentActivityTrail.test.tsx`
- **Done:** tests green; `pnpm lint` clean for touched files.
- **Criteria:** SC-3
- **Interfaces:** Consumes the existing stream-hook resume path and the trail family mapping; produces `apps/web/src/components/chat/useAgentStream.ts`, `apps/web/src/components/chat/AgentActivityTrail.tsx`.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
| --- | --- | --- | --- |
| SC-1 | Approve emits no chat message; `plan_approved` flag still set | `cd apps/api && DATABASE_URL="sqlite:///$(mktemp -d)/t.db" ../../.venv/bin/python -m pytest tests/agents/test_system_copy.py tests/agents/test_hitl_plan.py -q -k "plan"` | exit 0 |
| SC-2 | No `reset` between plan node and booking sub-agent | `cd apps/api && DATABASE_URL="sqlite:///$(mktemp -d)/t.db" ../../.venv/bin/python -m pytest tests/api/agent/test_stream_events.py -q -k "plan"` | exit 0 |
| SC-3 | Approval shows as a localized activity step | `cd apps/web && export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm exec vitest run src/components/chat/useAgentStream.stream.test.tsx src/components/chat/AgentActivityTrail.test.tsx` | exit 0 |
