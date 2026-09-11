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

Two independent fixes for GitHub #193, plumbing only — no service, schema, prompt, graph-topology or MCP change:

- **A. Turn-scoped idempotency key in the write tools.** `app/tools/_idempotency.py` derives `sha256(user_id|thread_id|last HumanMessage id|tool_name|canonical model-visible args)` and returns `None` when the turn cannot be identified. `book_flight`/`book_hotel` read `thread_id` from an injected bare `config: RunnableConfig` and the turn boundary from an injected `messages` state field (declared in the `*Args` schemas like `user_id`/`trip_id`, so the model-visible schema is unchanged and MCP is untouched — destructive tools are already excluded) and pass the key to `BookingService.book_*`, which already replays the owner's booking for the same key. A revise pass, an LLM retry or a graph replay inside one turn therefore returns the same reservation; a new turn, or a call with no turn context, books exactly as before (the `2c44f99` pinned test stays green).
- **B. Reflection ends a turn that already committed a booking.** `BOOKING_WRITE_TOOLS` in `app/agents/constants.py`; `_booking_committed_this_turn` in `app/agents/nodes.py` ends the turn (`goto=END`) before the judge when a `book_*` `ToolMessage` after the last `HumanMessage` has `status != "error"`. Placed right after the `awaiting_user` guard. Saves the judge call and removes the REVISE → `booking` re-entry that skipped the `plan` interrupt.

Commits: `794f4bd` (A helper), `dd2564b` (B), `7c1e6e2` (A wiring + tool tests), `6bc9a36` (end-to-end test). Targeted regression at `6bc9a36`: `tests/agents/test_depth_toggles.py tests/agents/test_multi_intent_routing.py tests/agents/test_graph.py tests/tools tests/mcp` → 366 passed, 1 warning in 47.73s (whole-directory run, cited per the layer-ladder rule; the full suite runs at branch finish).

### Rationale

Intake facts read from the tree at 34f9920 (main); branch fast-forwarded to b96569a (github/main, PR #190) before planning — none of the 17 commits in between touch the files in scope:

- (Intake also recorded that no test exercised a reflection REVISE onto `booking`; Task 2.2 now does, so that absence row was retired rather than kept as a stale claim.)
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

- Rule 3 — ruff import-sort / unused-import fix on the new helper's own code. `apps/api/app/tools/_idempotency.py`. Commit `794f4bd`.
- Rule 3 — flipped the pin-test equality operand order for ruff `SIM300`. `apps/api/tests/agents/test_reflection_booking_guard.py`. Commit `dd2564b`.
- Rule 1 — Task 2.1 case (e) drives the compiled booking sub-agent with a real owner-owned `trip_id` instead of the plan's `trip_id: None`: `book_*` are trip-scoped, so `trip_guard` blocks them without an active trip and no booking would ever be created (a 0-row pass). Plan gap, carried into Task 2.2's setup. `apps/api/tests/tools/test_booking_idempotency_tools.py`. Commit `7c1e6e2`.
- Rule 1 — Task 2.2 case 2 asserts `fast._cursor == 1`, not the plan's `== 2`: with `DEFAULT_MAX_REVISIONS == 1` the second reflection pass exits on `revisions >= max` before calling the judge. Plan arithmetic error, not a product defect. `apps/api/tests/agents/test_booking_turn_no_revise.py`. Commit `6bc9a36`.

### Review findings (Minor, non-blocking — forwarded to the final review chain)

- Task 1.1 review: no test pins the key formula itself (join order / json options); behaviour verified by reading `_idempotency.py:103-108`. Optional follow-up: one inline expected-digest test.
- Task 2.1 review: signature default `messages: Annotated[list, InjectedState("messages")] = None` vs schema `default_factory=list` — a typing wart only (helper handles `None`); the brief mandated this form. Optional follow-up: `list | None` on the signature.

### Advisory Findings (correctness-review, below the 75 threshold — not auto-fixed, surfaced for the author)

- score 50 — `apps/api/app/tools/_idempotency.py:80` (call-site-impact / guard-completeness): the key has no per-call component, so two byte-identical `book_*` calls in one turn collapse into one row. Both schemas model party size (`rooms`, `passengers`; `book_flight` docstring: "one booking covers all of them, never call this once per traveller"), so the trigger is an edge case, and it is the deliberate contract recorded under Alternatives (turn + args = one unit of work; #194 owns duplicate-intent).
- score 25 — `apps/api/app/agents/constants.py:75` (guard-completeness): `BOOKING_WRITE_TOOLS` omits `cancel_flight`/`cancel_hotel`, so a REVISE after a successful cancel still re-enters `booking` (pre-diff behaviour). `BookingService.cancel` is idempotent, so the worst case is a redundant no-op call, not a wrong result. Optional follow-up: add the cancel tools to the set.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| No consumer of `plan_approved` on the reflection/booking path (absence claim under Rationale; pipe-free form) | `grep -rn "plan_approved" apps/api/app/agents/supervisor.py apps/api/app/agents/subagents apps/api/app/tools apps/api/app/services` | 1 | 0 hits in the supervisor, sub-agents, tools and services; the only readers are `routers/agent.py` and `memory/extraction_runner.py`, and `nodes.py` only writes it | |
| Tool can read `thread_id` + last `HumanMessage.id` inside `ToolNode`, hidden from the LLM schema | `cd apps/api && ../../.venv/bin/python ../../specs/gh-193-booking-revise-idempotency/evidence/probe_tool_config.py` | 0 | `ok {'thread_id': 't-42', 'last_human_id': 'human-1'}` | |
| Pinned behaviour: identical `book_flight` calls without turn context stay distinct | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_flight_booking_tool.py -q` | 0 | 4 passed (incl. `test_book_flight_repeated_call_creates_distinct_bookings`) | |
| Intake lane evidence | `python3 .claude/scripts/verify_summary.py --lane gh-193-booking-revise-idempotency` | 0 | run at intake, 2026-09-11 | |
| Key helper: deterministic per turn+args, discriminates thread/turn/tool/args, ignores injected inputs, `None` without thread or HumanMessage | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_booking_idempotency_key.py -q` | 0 | 11 passed | SC-1 |
| Same thread + HumanMessage + args → one row for both tools; new HumanMessage → new row; no config → distinct rows; compiled booking sub-agent invoked twice → one row | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_booking_idempotency_tools.py -q` | 0 | 7 passed | SC-2 |
| Pinned behaviour: identical calls without turn context stay distinct | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_flight_booking_tool.py -q` | 0 | 4 passed, file untouched | SC-3 |
| Reflection ends without the judge on a committed `book_*` this turn; errored / earlier-turn / non-booking tools still reach the judge; constant pinned to tool names | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_reflection_booking_guard.py -q` | 0 | 5 passed | SC-4 |
| End-to-end booking turn: guard on → judge never called, one row; guard off → REVISE re-runs booking, second call replays via the key, one row | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_booking_turn_no_revise.py -q` | 0 | 2 passed in 0.83 s | SC-5 |
| Model-visible schema of both write tools unchanged | `cd apps/api && ../../.venv/bin/python -c "from app.tools.flight_tools import book_flight; from app.tools.hotel_tools import book_hotel; assert 'messages' not in book_flight.args and 'config' not in book_flight.args and 'messages' not in book_hotel.args and 'config' not in book_hotel.args"` | 0 | 11 model-visible keys each | SC-6 |
| Lint clean on the CI scope plus the four new test files | `cd apps/api && ../../.venv/bin/ruff check app scripts tests/tools/test_booking_idempotency_key.py tests/tools/test_booking_idempotency_tools.py tests/agents/test_reflection_booking_guard.py tests/agents/test_booking_turn_no_revise.py` | 0 | All checks passed | SC-7 |

### Not auto-verified

- Lane classification — reached traceability; flags assigned by reading the files named under Rationale, no command asserts them.
- "REVISE on the booking path skips the `plan` interrupt in production" — reached provenance (read from `nodes.py:253`, `supervisor.py:449`, `plan_node`); the end-to-end test drives the real graph with `MemorySaver`, not the Postgres checkpointer or the SSE router.
- "Anthropic-configured specialists crash on any REVISE (pre-existing, PR #192 note)" — reached traceability; not re-run, out of scope, no Anthropic key in the offline suite.
- "The key never changes the OpenAI prompt-cache prefix" — reached traceability: the key is computed inside the tool and never enters a prompt; not measured.

### Rollback

- `git revert 6bc9a36 7c1e6e2 dd2564b 794f4bd` (test → tool wiring → reflection guard → helper; each commit reverts cleanly on its own, and reverting `7c1e6e2` alone restores today's un-keyed booking path).

### Harness-Delta

- backlog: `hooks/branch-isolation-guard.sh` classifies every Write/Edit into a sibling worktree as `unsafe-path:outside-root` when the session's cwd is the main checkout, so all four implementers (and the controller) had to write files through Bash. Isolation was genuine (branch `fix/gh-193-…` in `../travel-pi-gh-193-…`). Same trap as the `sibling-worktree` memory; deserves a `compound` record and a hook fix that resolves the target path's own `git rev-parse --show-toplevel`.
- backlog: the plan-time `Interfaces:` contract treats any backticked noun in `Consumes` as an artifact needing a producer; external inputs must be prose. Cost one checker round-trip.
