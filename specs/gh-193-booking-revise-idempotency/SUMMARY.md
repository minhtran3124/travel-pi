# gh-193-booking-revise-idempotency — Summary

Lane: normal
Confidence: high
Reason: No manifest hard gate fires — no auth/authorization change, no schema change (`bookings.idempotency_key` and `BookingService._replay` already exist), no provider, no client-visible contract (injected tool params are invisible to the LLM schema and `book_*` are already excluded from MCP as destructive). Two flags fire — existing-behavior (reflection routing and the write path of two booking tools change) and multi-domain (agent graph + tools + tests) — and the diff spans more than two files, so normal, not tiny.
Flags: existing-behavior, multi-domain
Affects: agent reflection node (`app/agents/nodes.py`), booking tools (`app/tools/flight_tools.py`, `app/tools/hotel_tools.py`); `BookingService` unchanged
Input-type: change request
Route: using-git-worktrees → writing-plans → subagent-driven-development
Escalate: no

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

User messages (2026-09-11), in order:

> ok, mở 2 issue trên github cho 2 ticket này

> ok làm luôn #193 trên nhánh riêng

The scope-deciding text is GitHub issue #193 (minhtran3124/travel-pi), "Proposed fix" section, quoted verbatim:

> **A. Deterministic idempotency key in the `book_*` tool wrappers.**
> `key = sha256(user_id · thread_id · id(last HumanMessage) · tool_name · canonical(args))`, passed as `idempotency_key=` to `BookingService.create_*`. Same turn + same args → the service replays the existing booking; the model sees "already booked" and only rewrites its reply.
>
> Note: do **not** key on `tool_call_id` (the generic advice). A REVISE generates a *new* tool call with a new id, so that key would not protect this path. The unit of work is the user turn, so the turn id must be in the key. Do **not** drop `thread_id`/turn either — a `user_id + args` key would silently return a cancelled booking, or block a legitimate second ticket for the same flight.
>
> **B. Skip reflection when the turn already committed a write.**
> Next to the existing `awaiting_user` guard (`nodes.py:231`): if this turn contains a `ToolMessage` from `book_flight`/`book_hotel` with `status != "error"`, `goto=END`. A booking confirmation is not something a rewrite improves, and this saves the judge call.
>
> ## Tests
>
> - REVISE on the booking path with a `FakeLLM` that calls `book_flight(confirm=True)` again on the revise pass → exactly one booking row.
> - Reflection does not call the judge when the turn already committed a booking.
> - `LLM_RETRY` re-run of the booking assistant with the same args → one booking.
>
> ## Out of scope
>
> Detecting a user *intentionally* re-booking the same flight in a different turn/thread is a product decision (duplicate-intent warning), tracked separately.

## What changed

<not started — intake only>

### Rationale

Intake facts read from the tree at 34f9920 (main); branch fast-forwarded to b96569a (github/main, PR #190) before planning — none of the 17 commits in between touch the files in scope:

- `app/agents/nodes.py:253` — reflection REVISE does `goto=state["current_flow"]`; `app/agents/supervisor.py:449` sets `current_flow=target` (`"booking"` on this path) and `plan_node` (`nodes.py:268-303`) never overwrites it, so a REVISE re-enters `booking` without the `plan` interrupt. `plan_approved` is read only by `routers/agent.py:491` and `memory/extraction_runner.py` (episodic outcome), never by reflection or booking.
- `app/tools/flight_tools.py:348` / `app/tools/hotel_tools.py:470` — `book_*` take `user_id`/`trip_id` via `InjectedState` and call the service without `idempotency_key`; `app/services/booking_service.py:276-291` already implements `_replay(idempotency_key, user_id)` and `create_*` accept the kwarg. The fix is plumbing in the tool wrappers, no service or schema change.
- `app/mcp/server.py:61` — destructive tools are skipped from the MCP surface, so a new injected parameter on `book_*` cannot leak into a caller-supplied schema (the gh-166 trap).
- Why not re-gate through `plan`: an extra approval round-trip for a step the model already has context for; idempotency belongs in the tool layer (decision recorded in #193).

- Intake probe (`evidence/probe_tool_config.py`, exit 0): inside `ToolNode` a `@tool` receives `configurable.thread_id` through a `config: RunnableConfig` parameter and the last `HumanMessage.id` through `InjectedState("messages")`, and neither appears in the model-visible schema (`probe.args == ["x"]`). So the key can be derived in the wrapper with no new state key and no schema change.
- Pinned constraint: `tests/tools/test_flight_booking_tool.py::test_book_flight_repeated_call_creates_distinct_bookings` asserts two identical `book_flight.invoke(args)` calls (no thread/turn context) create two distinct bookings — the PR #80 deep-review revert `2c44f99` of a content-hash key. This change must keep it green: the key includes `thread_id` and the turn id, and is `None` when either is absent.

Documented default (not an ambiguity): when `thread_id` or a last `HumanMessage` is unavailable in the tool's runtime context, the wrapper passes `idempotency_key=None` — today's behaviour, never a fabricated key.

### Alternatives considered

- Key on `tool_call_id` (generic advice) — rejected: a REVISE emits a new tool call id, so the key would not cover the failing path.
- Key on `user_id + args` only (content hash) — rejected, and already reverted once in `2c44f99` (MIN-42, PR #80 deep review): silently returns a cancelled booking and blocks a legitimate second ticket (#194 covers duplicate intent separately).
- Strip `book_*` tools when `revisions > 0` — weaker: the model can still attempt the call and surface an error in the reply.
- Move the HITL `interrupt()` into the tool (LangChain HITL pattern) — cleanest long-term but changes the approval UX and still needs A; deferred.

### Deviations

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| No consumer of `plan_approved` on the reflection/booking path (absence claim under Rationale) | `grep -rn "plan_approved" apps/api/app --include='*.py' \| grep -v "routers/agent.py\|memory/extraction_runner.py\|agents/state.py\|agents/nodes.py\|agents/constants.py"` | 1 | 0 hits outside the listed files; `nodes.py` only writes it | |
| No test asserts a reflection REVISE onto `booking` (absence claim) | `grep -rn 'goto == "booking"\|current_flow="booking"\|current_flow": "booking"' apps/api/tests` | 0 | 4 hits, none in a reflection test: `test_system_copy.py:184` is `plan_node` approval; the other 3 are SSE done-event fixtures | |
| Tool can read `thread_id` + last `HumanMessage.id` inside `ToolNode`, hidden from the LLM schema | `cd apps/api && ../../.venv/bin/python ../../specs/gh-193-booking-revise-idempotency/evidence/probe_tool_config.py` | 0 | `ok {'thread_id': 't-42', 'last_human_id': 'human-1'}` | |
| Pinned behaviour: identical `book_flight` calls without turn context stay distinct | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_flight_booking_tool.py -q` | 0 | 4 passed (incl. `test_book_flight_repeated_call_creates_distinct_bookings`) | |
| Intake lane evidence | `python3 .claude/scripts/verify_summary.py --lane gh-193-booking-revise-idempotency` | 0 | run at intake, 2026-09-11 | |

### Not auto-verified

- Lane classification — reached traceability; flags assigned by reading the files named under Rationale, no command asserts them.

### Rollback

- `git revert <sha>` (no code change yet)

### Harness-Delta

- none
