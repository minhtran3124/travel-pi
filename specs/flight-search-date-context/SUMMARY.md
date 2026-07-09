# flight-search-date-context — Summary

Lane: normal
Confidence: high
Reason: Changes existing agent flight-search collection behavior (flag #8) with weak/absent proof around relative-date resolution and multi-turn info stitching (flag #9); no hard gate — prompt/tool/agent-logic only, no auth/authz/data-loss/external-provider/public-contract.
Flags: existing-behavior, weak-proof
Affects: agent flight-search flow — app/agents (supervisor.py, subagents/_base.py, state.py ground_current_date), app/tools/flight_tools.py, planner/booking prompts
Input-type: change request

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

<!-- User's request VERBATIM at intake (Vietnamese). Investigate conversation
     7a22074c-4611-4690-8b64-b24856a52ef4. -->

check messages of conversation 7a22074c-4611-4690-8b64-b24856a52ef4
- user yêu cầu tìm chuyến bay, những tin nhắn có đầy đủ thông tin nhưng agent vẫn ko thể hiểu chính xác để collect info
- agent nên có khả năng phán đoán và biết chính xác hnay là ngày nào, ngày mai là ngày nào
- agent phải có khả năng hiểu những tin nhắn gần đây của convo để có thể thu thập, tóm tắt thông tin 1 cách thông minh

## What changed

<!-- Not yet implemented — intake only. Routed to normal-lane workflow. -->

Intake classification only. No code changed yet.

### Rationale

Reproduced the bug from the live thread: user asked for "chuyến bay Đà Nẵng đi HCM
sáng mai", then supplied "10/07" then "2026" across consecutive turns; the agent never
called the flight tool (all `tool_calls` NULL) and kept re-asking, finally claiming it
"only has the year 2026" — i.e. it failed to (a) resolve the relative date "sáng mai"
and (b) stitch "10/07" + "2026" from adjacent turns. Notably `ground_current_date()`
(`app/agents/state.py:79-100`) already injects today into every sub-agent, so the fix is
not "add date injection" but closing the gap between injected date and actual tool use —
a genuine design fork, hence normal lane with a short design step before planning.

### Alternatives considered

- Classify as `tiny` — rejected: touches shared agent prompts + tool contract and has no test proof; multi-turn/date behavior needs verification, not a direct patch.
- Classify as `high-risk` — rejected: no hard gate; ≤2 flags; changes are internal to the agent (prompt/tool arg parsing), not public API/auth/data.

### Deviations

- none

### Verify

<!-- To be filled by the implementation task. Investigation evidence below. -->

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Reproduce (read live thread) | `docker exec api-db-1 psql -U travel -d travel -c "SELECT role,substring(content,1,120) FROM messages WHERE conversation_id='7a22074c-4611-4690-8b64-b24856a52ef4' ORDER BY created_at"` | 0 | 26 msgs; flight-collect loop confirmed, no tool_calls |

### Rollback

- `git revert <sha>`

### Harness-Delta

- none
