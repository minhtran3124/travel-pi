# min-42-implement-mcp-tool — Summary

Lane: high-risk
Confidence: high
Reason: Originally normal (additive MCP tools). Escalated to high-risk for the post-review follow-ups, which change booking money-path behaviour: reverting the content-hash idempotency fix (a deep-review found it regressed cancel-then-rebook + swallowed intentional duplicates) and re-scoping the planner off the destructive tools. These touch reservation semantics and remove test asserts, warranting the higher scrutiny.
Flags: public-contract, weakening-validation
Affects: MCP tool surface (auto-exposed from app/tools/registry.py via app/mcp/server.py); no HTTP route / schema change
Input-type: spec slice

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

Implement MIN-42 "Implement MCP tool" (https://linear.app/minhtran3124/issue/MIN-42/implement-mcp-tool):

> Expose flight & hotel **book / cancel** operations as agent tools so they are callable over MCP by external clients (Claude Desktop / Agent SDK), alongside the existing search tools.
>
> The MCP layer is already done — `app/mcp/server.py` → `build_mcp_server()` iterates `ALL_TOOLS` from `app/tools/registry.py` and exposes every registry tool as an MCP tool. Any tool added to the registry is served over MCP automatically — no per-tool `app/mcp/` wiring is required. The real gap is the tools layer.
>
> Scope — 3 new tools:
> - `book_flight` (`app/tools/flight_tools.py`) — wrap `BookingService.book_flight`. Mirror `book_hotel`: `confirm=True` guard, `session_scope()`, map `AppError`/`ValueError` → `ToolException`. Build `FlightBookingRequest` from args (`flight_id` **or** `flight_number`+`origin`+`destination`+`departure_date`, plus passenger/contact fields). `destructive=True`.
> - `cancel_flight` + `cancel_hotel` (new `app/tools/booking_tools.py`) — each takes a `booking_id` (UUID or 6-char confirmation code) + `confirm=True`. Load booking via `BookingService.get`, guard on `booking.type`, then `BookingService.cancel`. Map errors → `ToolException`. `destructive=True`.
> - Register in `registry.py`: add `book_flight` to FLIGHT_TOOLS / booking domain; add the two cancel tools to the `booking` domain group. Add all three names to `_WRITE` and `_DESTRUCTIVE`. `ALL_TOOLS` + `TOOL_METADATA` pick them up automatically.
> - MCP exposure — automatic via the registry; no `server.py` change expected.
> - Tests: `tests/tools/` happy path + errors (unknown flight, unknown booking id, missing `confirm`, wrong-type guard); `tests/mcp/test_mcp_server.py` assert the three are exposed with `destructiveHint=True` and "Cannot be undone." in the description.
>
> Resolved decisions: (1) Cancel = destructive + confirm guard (no un-cancel). (2) Two separate cancel tools — `cancel_flight` + `cancel_hotel` — each wraps the same `BookingService.cancel(booking_id)` but first loads the booking and raises `ToolException` if `booking.type` does not match.
>
> Acceptance: the three tools are discoverable/callable over MCP with correct destructive annotations; valid input returns/cancels the correct Booking; invalid input (unknown id, missing `confirm`, wrong booking type) raises a graceful `ToolException`; `make test` passes.

## What changed

Added three agent tools that auto-expose over MCP: `book_flight` (`app/tools/flight_tools.py`) and `cancel_flight` + `cancel_hotel` (new `app/tools/booking_tools.py`), each a thin wrapper over the existing `BookingService` (`book_flight`, `get`, `cancel`) cloning the `book_hotel` pattern — `confirm=True` guard, `session_scope()`, `AppError`/`ValueError` → `ToolException`. The cancels load the booking first and refuse a booking of the other `type`. Registered all three in `app/tools/registry.py` `_WRITE` + `_DESTRUCTIVE` and the `booking` domain, so `build_mcp_server()` serves them with `destructiveHint=True` + "Cannot be undone." No `app/mcp/server.py` change. 11 new tests (3 book_flight, 5 cancel, 1 MCP exposure covering all three).

### Rationale

MCP exposure is registry-driven (`build_mcp_server()` iterates `ALL_TOOLS`), so the change is confined to the tools layer + registry, keeping the router→service→repository layering intact — tools are thin adapters over the existing `BookingService` with no new business logic.

### Alternatives considered

- One generic `cancel_booking` tool vs. two type-specific tools — the issue resolved on two separate `cancel_flight`/`cancel_hotel` tools for an explicit MCP surface, each guarding on `booking.type`. Following that decision.

### Deviations

- Rule 2 — `_cancel` now also maps `ValueError` → `ToolException` (mirrors `book_flight`/`book_hotel`), so a malformed-row `ValidationError` from `svc.get()` surfaces as a clean `ToolException` instead of escaping raw. `app/tools/booking_tools.py`. Commit `f9e0e38`. (correctness-review — error handling for a documented failure mode.)
- Rule 2 — `book_flight` logs only non-PII flight identifiers, not passenger name/email/phone (guidelines: never log sensitive data). `app/tools/flight_tools.py`. Commit `f9e0e38`.

### Advisory Findings

- LOW — `book_hotel` (`app/tools/hotel_tools.py`) logs guest name/email/phone via `log_tool_call(..., locals())` — the same PII-in-logs pattern `book_flight` was fixed to avoid. Pre-existing; out of MIN-42 scope. See Harness-Delta.

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| New tool + MCP tests | `DATABASE_URL="sqlite:///:memory:" pytest tests/tools/test_flight_booking_tool.py tests/tools/test_cancel_tools.py tests/mcp/test_mcp_server.py -q` | 0 | 12 passed |
| Lint | `ruff check app/tools/booking_tools.py app/tools/flight_tools.py app/tools/registry.py` | 0 | All checks passed |
| Full suite | `DATABASE_URL="sqlite:///:memory:" pytest -q` | 1 | 1378 passed, 5 failed — all pre-existing/environmental from local `.env` keys, none in changed files: 2 `test_routing_tools` (real `ORS_API_KEY` → `source=="openrouteservice"` not `"estimate"`); 3 `test_config_llm`/`test_embeddings` (`OPENAI_API_KEY=test` breaks no-key-default assertions, per `env-openai-key-test-breaks-llm-tests`). New tool/registry/MCP tests all pass. |

### Rollback

- `git revert f9e0e38 f034fa5 41433cf` (or drop the whole branch — all changes are additive; no migration).
- Post-review follow-ups (2026-07-16): PII-log fix + planner scoping — `git revert <commit>`; idempotency revert — the change itself is a revert of `91f7ad2`'s idempotency portion, re-adding it would re-introduce the money-path regressions the deep review found, so it should not be rolled back.

### Review follow-up (2026-07-16, post multi-agent review)

Three review findings addressed on this branch:
1. PII-log — `book_hotel` now logs an explicit identifier-only dict (not `locals()`); guest name/email/phone stay out of logs. Kept.
2. Planner scoping — planner bound to flight/hotel **search only**; every destructive tool lives in the `booking` domain, whose route is the only one passing the HITL `plan_node` interrupt. Kept. A registry invariant test blocks a destructive tool ever leaking back into the planner.
3. Idempotency — the initially-shipped content-hash idempotency key was **reverted** after a high-effort deep review found it net-negative: it permanently replayed cancelled bookings on cancel-then-rebook, silently swallowed an intentional second identical booking, and hashed un-normalised inputs (so it did not even prevent the duplicate it targeted). The booking sub-agent has no auto-retry, so the original "retry double-books" vector does not exist on the agent path; MCP-retry idempotency is the client's concern (as with the REST `Idempotency-Key` header, which is client-supplied, not server-derived). Tool booking now matches REST-without-a-key semantics: each call creates a new booking. A positive test asserts two identical calls create distinct bookings.

### Harness-Delta

- backlog — PII in tool logs: `book_hotel` (and possibly other write tools) log guest/passenger name/email/phone via `log_tool_call(..., locals())`. `book_flight` was fixed here; a codebase-wide sweep of the tool layer against the "never log sensitive data" guideline is worth a dedicated task (→ `/compound`).
