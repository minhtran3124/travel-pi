# gh-194-duplicate-booking-warning — Summary

Lane: normal
Confidence: high
Reason: initially high-risk/low (public-contract hard gate + open decisions); user narrowed scope 2026-09-14 (E001 C: opt-in service flag passed only by agent tools, REST unchanged; E002 A; E003 A) — no hard gate remains; 3 flags → normal.
Flags: existing-behavior, multi-domain, weak-proof
Affects: app/services/booking_service.py (book_flight / book_hotel, opt-in check), app/repositories/booking.py, app/exceptions.py, app/tools/flight_tools.py + app/tools/hotel_tools.py (agent book_* tool schema: allow_duplicate)
Input-type: change request
Route: using-git-worktrees (../travel-pi-gh-194, feat/gh-194-duplicate-booking-warning) → subagent-driven-development (PLAN.md, 2 waves)
Escalate: no (E001–E003 decided by user 2026-09-14)

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

/feature-intake for https://github.com/minhtran3124/travel-pi/issues/194

Issue #194 — "booking: warn on duplicate-intent bookings (same user, flight/hotel, dates) instead of silently creating a second one":

> This is the **user-level** case: the traveller asks to book the same flight/room again in a new turn or a new conversation — e.g. they repeat "book it" because the stream dropped, or they open a fresh chat and ask again. That is a genuinely new request, so an idempotency key must *not* block it (it would silently return a cancelled booking or prevent a legitimate second ticket). Today the service just creates a second booking with no signal to the model or the user.
>
> In `BookingService.create_flight_booking` / `create_hotel_booking` (`app/services/booking_service.py`), before inserting: query for an **active** booking owned by the same user with the same flight (or hotel + room) and the same dates/passengers. If one exists, do not book; return a structured "possible duplicate" result that the tool relays, e.g.: "You already have booking #ABC123 for this flight on 2026-10-02 (2 passengers). Book another one anyway?" The model asks; a follow-up call with an explicit override (e.g. `allow_duplicate=True`) proceeds.
>
> Decisions needed before implementing: What counts as "the same"; whether cancelled bookings count (proposal: no); wording + i18n via `system_reply` (vi/en), and whether the warning should also surface in the HITL `plan` draft; MCP exposure.
>
> #193 handles the same turn replayed by REVISE / retries. This issue handles a *different* turn or thread with the same intent. Both are needed.

Follow-up turn (user, 2026-09-14), verbatim: "E001 C, E002 mặc định, E003 A — tiếp tục"

## What changed

The agent's `book_flight` / `book_hotel` tools now refuse to silently create a second identical booking: if the traveller already has an active booking for the same flight + passenger count, or the same hotel + exact check-in/check-out, the tool returns a "possible duplicate" error naming the existing booking (confirmation code, dates, count), and the model must ask before retrying with `allow_duplicate=true`. The logic lives in `BookingService` behind `check_duplicate` (default `False`), so the REST `POST /flights/book` and `/hotels/book` routes behave exactly as before.

### Rationale

E001 C keeps the matching rule in one place (the service, next to `_replay`) while limiting the behaviour change to the agent path, so no public contract moved. Idempotent replay runs first, so a same-turn revise re-run still returns the original booking instead of tripping the check; `allow_duplicate` is deliberately excluded from the turn idempotency key so a re-run with the flag flipped cannot mint a second row. The warning reaches the traveller through the existing `ConflictError → tool_error` path, which needed no prompt, copy or HITL change.

### Alternatives considered

- Service-level check always on (issue proposal, E001 A) — would change the REST contract (new 409) and require FE handling on `/flights` + `/hotels`; declined by the user.
- Tool-level check only (E001 B) — duplicates the matching rule outside the service; the web pages still double-book either way.
- Surfacing the warning in the HITL plan draft (E003 B) — extra graph-state plumbing; declined.
- `SYSTEM_COPY` / `system_reply` wording — unnecessary: the English tool error is relayed by the model in the conversation language.

### Deviations

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| unit — service raises on duplicate (flight, hotel, unpadded hotel dates) | `cd apps/api && /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/python -m pytest tests/services/test_booking_duplicate.py -q -k raises` | 0 | 3 passed @ cc8c32c; re-checked exit 0 @ 4fca57a (`verify_summary.py --check`) | SC-1 |
| unit — cancelled / other passengers / other dates / other owner / flag off not flagged (flight + hotel) | `cd apps/api && /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/python -m pytest tests/services/test_booking_duplicate.py -q -k not_flagged` | 0 | 8 passed @ cc8c32c; re-checked exit 0 @ 4fca57a (`verify_summary.py --check`) | SC-2 |
| unit — agent tools warn, override books, schema exposes allow_duplicate | `cd apps/api && /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/python -m pytest tests/tools/test_booking_duplicate_tools.py -q` | 0 | 6 passed @ cc8c32c; re-checked exit 0 @ 4fca57a (`verify_summary.py --check`) | SC-3 |
| integration — REST booking/flight/hotel routes unchanged | `cd apps/api && /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/python -m pytest tests/api/booking tests/api/flight tests/api/hotel -q` | 0 | 201 passed @ cc8c32c; re-checked exit 0 @ 4fca57a (`verify_summary.py --check`) | SC-4 |
| unit — all agent tool tests (idempotency, passengers, owner, trip_id, cancel, MCP exclusion) | `cd apps/api && /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/python -m pytest tests/tools -q` | 0 | 350 passed @ cc8c32c; re-checked exit 0 @ 4fca57a (`verify_summary.py --check`) | SC-5 |
| lint | `cd apps/api && /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/ruff check app tests/services/test_booking_duplicate.py tests/tools` | 0 | All checks passed @ cc8c32c; re-checked exit 0 @ 4fca57a (`verify_summary.py --check`) | SC-6 |

### Not auto-verified

- A live model actually asks the traveller and retries with `allow_duplicate=true` only after confirmation — reached traceability (tool description + error hint text are asserted in tests); not re-run because the offline suite uses FakeLLM and no eval golden covers this flow.
- MCP does not expose `book_flight` / `book_hotel` (so `allow_duplicate` is not a public MCP schema) — reached provenance via the pre-existing `tests/tools/test_booking_owner.py::test_booking_tools_absent_from_mcp`, run inside SC-5.

### Advisory Findings

Final correctness review (6 FIND angles over b1b4a73..cc8c32c, 7 distinct candidates, each scored by an independent scorer; threshold 75 — none reached it, so none entered the auto-fix loop):

- CR-1 (50) — check-then-insert race: two concurrent book calls with different idempotency keys both pass the check and both insert (`booking_service.py:419-431`, `:512-528`). Atomic fix needs a lock / partial unique index = Rule 4 (schema or transaction scope). Accepted limitation: the check is best-effort; before this change there was no check at all.
- CR-2 (50) — hotel duplicate message quotes the new request's room count, not the existing booking's (`booking_service.py:524`).
- CR-3 (50) — flight match ignores `passenger_name` (`booking_service.py:423`); by design per E002 A.
- CR-4 (25) — `_as_date` on a malformed stored date would raise (`booking_service.py:519`); no writer of such rows found.
- CR-5 (50) — same-turn REVISE can flip `allow_duplicate=true` after a duplicate warning: the warning ToolMessage is `status="error"`, so the gh-193 guard (`agents/nodes.py:209-229`) does not end the turn; no row exists under the turn key, so `_replay` misses and a second booking commits without traveller confirmation (`flight_tools.py:465-472`, `hotel_tools.py:581-588`). LLM-dependent last step caps the score. **Fixed in 4fca57a by user decision (2026-09-15)** despite the sub-threshold score: the tools ignore `allow_duplicate` while a marker-tagged (`[possible-duplicate]`) duplicate warning from the same tool sits after the latest HumanMessage (`app/tools/_idempotency.py::duplicate_warned_this_turn`); tests cover same-turn refusal, new-turn acceptance and no-context acceptance for both tools.
  - Re-review of 4fca57a (cc8c32c..4fca57a): **fix verdict closed**, 0 bugs. Traced in the real runtime: marker survives `tool_error`, the booking subgraph shares `TravelAgentState.messages`, so the warning is visible after the last HumanMessage on a REVISE re-run. Two P3 advisories left open: CR-5a the scan matches on tool name only, so a different booking warned earlier in the same turn also refuses an override (fails safe — the traveller repeats once); CR-5b tests hand-build the warning ToolMessage rather than running the real `ToolNode` error handler (`app/agents/subagents/_base.py:278`), so a change to that handler's message format would not be caught.
- CR-6 (50) — hotel match ignores rooms/adults/children (`booking_service.py:512-528`); by design per E002 A.
- CR-7 (50) — duplicate check runs before `is_available`, so a sold-out hotel prompts a duplicate confirmation first (`booking_service.py:512`); the retry still fails safely with 409.

### Intent Findings

Intent review over b1b4a73..4fca57a (plan-blind, verbatim-intent oracle): ✅ no divergence; no gap, no excess.

- IR-1 drift (equivalent, advisory) — "wording + i18n via `system_reply` (vi/en)": the warning is an English tool-error string, not `system_reply`. Superseded by the user's E003 A ("English source, localized through the reply-language path").
- IR-2 unknown → resolved — "MCP exposure": the reviewer assumed the book tools are auto-exposed over MCP. They are not: `app/mcp/server.py:61` skips every destructive tool, pinned by `tests/tools/test_booking_owner.py::test_booking_tools_absent_from_mcp` (runs inside SC-5, exit 0 @ 4fca57a). No action.

### Rollback

- `git revert <fix-sha> 0c79f9e fd6fe2c` (no migration, no data written by this change).

### Harness-Delta

- backlog — PostToolUse hooks (ruff-on-edit, render-plan-on-write, blast-radius) skip files in a sibling worktree (`unsafe-path:outside-root`), and the worktree has no `.claude/scripts`, so plan/summary checks must be run from the main checkout against worktree paths.
