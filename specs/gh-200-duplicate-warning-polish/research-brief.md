# Research Brief — gh-200-duplicate-warning-polish

Depth: **Standard** (intake lane `normal` → Standard per `.claude/rules/research-depth.md`;
re-run with evidence below — Standard holds, no upgrade to Deep). Worktree:
`../travel-pi-gh-200`, branch `fix/gh-200-duplicate-warning-polish`. Scope: GH #200 items 1–4
(item 5 out of scope). Date: 2026-09-15.

All `apps/api/…` paths below are relative to the worktree unless prefixed `github/main:`.

---

## Bottom Line

| Field | Value |
|---|---|
| **Recommendation** | reuse existing — extend the existing marker/guard/test seams; no new abstraction, no dependency |
| **Why this is the lightest credible path** | every item has an in-repo seam already: `DuplicateBookingError.existing` (id known at raise time), the tool's `except DuplicateBookingError` decorator branch, the `test_booking_turn_no_revise.py` FakeLLM harness that drives the real `ToolNode`, and the merged gh-198 lock block whose boundaries are explicit. |
| **Confidence** | 85% |
| **Next step** | **Before planning: bring `github/main` into the branch** (11 commits behind; the lock and PR #204 are not in the worktree — see Risks). Then `writing-plans` with the item-by-item recipe in Recommendation. |

---

## Repo Snapshot

| Field | Detected |
|---|---|
| Repo type | monorepo (pnpm + Turborepo): FastAPI backend `apps/api/`, Next.js `apps/web/` (`CLAUDE.md`) |
| Primary language + runtime | Python 3.14 in the worktree venv (`.venv/lib/python3.14`), Docker image py3.12 (`techstacks/guidelines.md:57`) |
| Frameworks / platforms | FastAPI + SQLAlchemy; LangGraph hand-built `StateGraph`, sub-agents = ReAct loop `assistant ⇄ ToolNode` (`techstacks/langgraph.md`) |
| Relevant packages | `langgraph`, `langgraph-prebuilt`, `langchain-core` (installed: langgraph 1.2.6, langgraph-prebuilt 1.1.0, langchain-core 1.4.8 — `python -c "importlib.metadata.version(...)"`) |
| Detectable versions | pins `langgraph>=1.0,<2.0`, `langgraph-prebuilt>=1.0.2,<2.0` (`apps/api/requirements-ai.txt:13,24`) |
| Important constraints | SQLite = unit tests only, every running env is Postgres (memory `runtime-envs-all-postgres-sqlite-tests-only`; lock is a Postgres no-op on SQLite `github/main:app/repositories/booking.py:200-204`); FakeLLM/no network in tests (`techstacks/guidelines.md:56-59`); stage and commit as separate commands (`CLAUDE.md`); absence claims need a cited search (`.claude/rules/behavior.md`) |

---

## Feature Understanding and Assumptions

- **Requested feature:** GH #200 items 1–4 — (1) hotel duplicate message built from `existing.details`; (2) same-turn override guard compares the warned booking with the current request instead of matching on tool name; (3) a FakeLLM test that drives warning → REVISE → `allow_duplicate=true` through the real `ToolNode` and asserts exactly 1 row; (4) run `is_available` before the duplicate prompt.
- **What success appears to mean:** (1) "3 room(s)" never appears when the existing booking has 1 room; (2) "book A and B, B again is fine" books B on the first override while an override for A in the same turn is still refused; (3) a test that fails if `_tool_error_to_message` / `ToolNode` output changes so the marker is no longer found; (4) a sold-out hotel says sold-out first, not "possible duplicate".
- **Assumptions from the request:** the issue's suggestion (embed the existing booking id in the marker) is the default for item 2; item 5 (`_as_date` leniency) stays out; no route/schema/migration change.
- **Assumptions still needing confirmation:** (a) the plan runs on top of `github/main` (lock present) — the worktree HEAD does **not** contain it; (b) for item 2, whether a bare legacy `[possible-duplicate]` marker (threads checkpointed before this change) should still refuse the override (recommended: yes, fail-safe).

---

## Evidence Ledger

| Label | Evidence |
|---|---|
| `Local` | Worktree HEAD = `ef9aec1` = local `main`; `github/main` (`63621d1`) is 11 commits ahead and is where PR #203 (gh-198 lock) and #204 (tool args_schema) landed: `git rev-list --count HEAD..github/main` → 11; `git diff --stat HEAD github/main -- apps/api` lists `app/repositories/booking.py (+51)`, `app/services/booking_service.py (+26/-…)`, `tests/services/test_booking_owner_lock.py`, `test_booking_duplicate_concurrency.py`. `gh pr view 203` → `state: MERGED, mergedAt 2026-09-15T04:54:34Z`. `grep -rn 'advisory\|xact_lock' apps/api/app` in the worktree → 0 code hits (only a tips string). |
| `Local` | Hotel message interpolates the request, not the row: `app/services/booking_service.py:522-526` (`request.check_in`, `request.check_out`, `request.rooms`). `HotelBookingDetails` carries `check_in, check_out, nights, rooms, adults, children, hotel_name, city` (`app/schemas/booking.py:54-96`, fields at rel. lines 35-41). The match condition compares dates only (`:519-520`), so `rooms/adults/children` can legitimately differ (gh-194 CR-6 "by design"). |
| `Local` | Flight message: `booking_service.py:424-431` uses `flight.flight_number`, `flight.departure_time` (resolved row = the row `existing.reference_id` points at) and `request.passengers`, which the match condition forces equal to `existing.details.passengers` (`:423`) → **no equivalent defect in `book_flight`**; switching to `existing.details.*` is optional symmetry. |
| `Local` | Marker: `DUPLICATE_WARNING_MARKER = "[possible-duplicate]"` (`app/exceptions.py:65`); `DuplicateBookingError.__init__` appends it when absent and stores `self.existing` (`app/exceptions.py:86-98`). Only consumers: `app/tools/_idempotency.py:28,110` and `flight_tools.py:29-30,449,497` / `hotel_tools.py:36-37,557,605` (`grep -rn "possible-duplicate\|DUPLICATE_WARNING_MARKER\|duplicate_warned_this_turn\|OVERRIDE_REFUSED_HINT" apps/api/app apps/api/tests apps/web/src`; no hit in `apps/web/src`, no hit in `app/streaming`). |
| `Local` | Guard: `duplicate_warned_this_turn(tool_name, messages)` (`_idempotency.py:85-113`) scans messages after the last `HumanMessage` for `ToolMessage(name==tool_name, status=="error", MARKER in text)`. `turn_idempotency_key` hashes `[user_id, thread_id, last_human_id, tool_name, canonical model-visible args]` (`:139-149`); `allow_duplicate` is excluded from the hashed args (`flight_tools.py:452-467`, `hotel_tools.py:560-577`). |
| `Local` | Tool flow: `override_refused = allow_duplicate and duplicate_warned_this_turn(...)`; `check_duplicate=not effective_allow_duplicate`; on `DuplicateBookingError` the tool re-wraps with `tool_error(e)` and appends `OVERRIDE_REFUSED_HINT` when refused (`flight_tools.py:449-498`, `hotel_tools.py:557-607`). The `try/except` sits **inside** `with session_scope() as s:` (`flight_tools.py:473`, `hotel_tools.py:580`) — a second service call in the `except` branch runs on the same transaction. |
| `Local` | Text the guard actually scans: `ToolNode(tools, handle_tool_errors=_tool_error_to_message)` (`app/agents/subagents/_base.py:278`, booking sub-agent has no `tool_fault` → this branch; `booking.py:19-30`) → `describe_tool_failure` → for an `AppError` cause: `"Tool call failed: {exc}. This is a definite answer about the data…"` (`app/agents/retry.py:122-138`); `{exc}` = `f"{detail} Hint: {hint}"` from `tool_error` (`app/tools/_base.py:61`). Marker survives because it lives in `detail`. |
| `Local` | Reflection: an error ToolMessage does **not** end the turn (`_booking_committed_this_turn` requires `status != "error"`, `app/agents/nodes.py:210-229`; pinned by `tests/agents/test_reflection_booking_guard.py:82-99`), so the judge runs, `REVISE` re-enters `current_flow` with a `SystemMessage(REFLECTION_REVISE_NOTE)` (`nodes.py:281-292`, not a `HumanMessage` → turn boundary unchanged), `DEFAULT_MAX_REVISIONS = 1` (`constants.py:78`). |
| `Local` | Test harness for item 3: `tests/agents/test_booking_turn_no_revise.py` — builds `build_graph(llm=FakeLLM, fast_llm=FakeLLM, checkpointer=MemorySaver(), store=InMemoryStore())` (`:72-75`), seeds a trip + flight (`:93-107`), scripts `book_flight` tool calls as `AIMessage(tool_calls=[…])` (`:110-136`), resumes the plan interrupt with `Command(resume={"approved": True})` (`:170-174`), asserts `ToolMessage.status` and `_rows(url)` (`:180-193`). `fast=FakeLLM(responses=["REVISE", "OK"])` drives the judge (`:164`). |
| `Local` | Lock boundaries (merged): `github/main:app/services/booking_service.py` — `book_flight` `if check_duplicate:` at 421: `lock_owner_bookings(user_id)` → re-run `_replay` → `list_active_by_reference` loop → raise; `book_hotel` at 525-551 same shape, then `guests = …; if not hotel_service.is_available(...)` at 552-561 **after** the block; insert via `self._repo.add` at the end of the method. Lock = `SELECT pg_advisory_xact_lock(:key)` on the caller-owned session, released at commit/rollback (`github/main:app/repositories/booking.py:186-218`). |
| `Local` | `hotel_service.is_available` / `available_rooms` are pure functions (md5-seeded `Random`, no session, `app/services/hotel_service.py:73-105`). `book_flight` has no availability/seat check (`grep -n "seats\|available" app/services/booking_service.py` → 0 hits; `flight_service.py:143` only seeds `seats_available`). |
| `Local` | Lock tests spy call count only (`patch.object(BookingRepository, "lock_owner_bookings")`, `github/main:tests/services/test_booking_owner_lock.py:88-140`) — order-agnostic; Postgres concurrency proof is `TEST_DATABASE_URL`-gated (`test_booking_duplicate_concurrency.py:52`). |
| `Upstream` | langgraph-prebuilt tag `prebuilt==1.1.0` `tool_node.py`: `TOOL_CALL_ERROR_TEMPLATE = "Error: {error}\n Please fix your mistakes."`; callable handler → `content = flag(e)`; error message is `ToolMessage(content=content, name=tool_call["name"], tool_call_id=tool_call["id"], status="error")`; caught types inferred from the callable's first-parameter annotation (`_infer_handled_types`). Identical in the installed copy (`.venv/lib/python3.14/site-packages/langgraph/prebuilt/tool_node.py:111,433,1154-1159`). |
| `Docs` | Reference page `reference.langchain.com/python/langgraph/prebuilt/#…ToolNode` → HTTP 404 at fetch time; version-matched source used instead (above). |
| `Inference` | Because the error `ToolMessage.name` is the tool-call name and `content` is exactly the handler's string, the marker survives unchanged into state; the only way the guard "silently stops working" is a change to `describe_tool_failure` / `tool_error` wording that drops `detail` — which is what the item-3 test must pin. |

---

## Local Findings

- **Relevant files, modules, scripts, docs, tests:**
  - `app/services/booking_service.py` (`book_flight` 352-460, `book_hotel` 461-590 in worktree; +lock block on `github/main`), `app/exceptions.py:62-98`, `app/tools/_idempotency.py`, `app/tools/flight_tools.py:367-500`, `app/tools/hotel_tools.py:486-608`, `app/tools/_base.py:45-62,105-116`, `app/agents/subagents/_base.py:49-70,268-283`, `app/agents/retry.py:77-150`, `app/agents/nodes.py:210-292`, `app/schemas/booking.py:30-96`.
  - Tests: `tests/tools/test_booking_duplicate_tools.py` (hand-built `_warning_message` at 26-30; same-turn cases 158-260), `tests/services/test_booking_duplicate.py` (service-level; message assertions at 96-109), `tests/agents/test_booking_turn_no_revise.py` (subgraph harness), `tests/agents/test_reflection_booking_guard.py`, `github/main:tests/services/test_booking_owner_lock.py`.
  - Docs: `docs/solutions/agent/reflection-humanmessage-language-flip.md` (revise note must stay a `SystemMessage` — the guard's turn boundary depends on it), `explicit-args-schema-breaks-tool-injection.md` (keep auto-derived schemas when touching tool signatures), `chat-booking-unreachable-three-blockers.md` (tests that invoke tools directly miss seams — exactly CR-5b).
- **Existing abstractions or extension points:** `DuplicateBookingError(existing=…)` already carries the booking at raise time; `DuplicateBookingError.__init__` is the single place the marker is minted; the tool's `except DuplicateBookingError` branch already post-processes the error; `_message_text` + `_last_human_index` helpers in `_idempotency.py`; `FakeLLM` scripted `tool_calls` + `Command(resume=…)` harness.
- **Conventions worth preserving:** `_idempotency.py` stays stdlib + `langchain_core` only (docstring `:16-17`); tool-error path stays `raise tool_error(e) from e`; assertions on `_rows(url)` and `ToolMessage.status` rather than prose; one `HumanMessage` per turn, id-less in graph tests.
- **What can likely be reused:** the whole `test_booking_turn_no_revise.py` scaffolding (fixture, `_seed_trip_and_flight`, `_book_flight_call`, `_drive/_invoke`, `_book_flight_tool_messages`) — copy the helpers into a new module (that file's docstring says it is deliberately self-contained) or promote them to `tests/agents/conftest.py`.
- **What appears missing locally:** (i) no way for the tool to know the existing booking id *before* the service call (it only exists on `e.existing`); (ii) no subgraph test exercises an error ToolMessage from `book_*` through the real `ToolNode` (`grep -rn "possible-duplicate" apps/api/tests` → only the tools test's hand-built message — 0 hits in `tests/agents`); (iii) no prompt text mentions `allow_duplicate` (`grep -rln allow_duplicate app/prompts/` → none) — the tool docstring is the only instruction.

---

## Upstream Findings

- **Repositories inspected:** `langchain-ai/langgraph` at tag `prebuilt==1.1.0`, `libs/prebuilt/langgraph/prebuilt/tool_node.py` (raw fetch).
- **Pattern or capability already present upstream:** `handle_tool_errors` accepts bool / str / callable / exception type(s); a callable's first-parameter annotation decides the caught set; the error ToolMessage is built as `content=handler(e), name=call["name"], tool_call_id=call["id"], status="error"`.
- **Files, modules, or areas worth modeling:** none beyond confirming the contract; the project already wraps it (`_tool_error_to_message`, `exc: Exception` annotation "load-bearing" per `_base.py:57-58`).
- **How closely the upstream pattern matches this repo:** exact — the installed file matches the tag byte-for-byte on the quoted lines.
- **Any upstream gaps or uncertainties:** none for this change. Note for the future: `ToolNode` also emits `status="error"` messages for arg-validation and trip-guard blocks with different wording; the guard's `MARKER in text` test is what keeps those from being mistaken for duplicate warnings.

---

## Docs Findings

- **Official sources checked:** `https://reference.langchain.com/python/langgraph/prebuilt/` (404 at fetch time); fallback = version-matched source at tag `prebuilt==1.1.0` (see Upstream).
- **Version-matched vs latest-stable status:** installed `langgraph-prebuilt 1.1.0` == tag inspected; pin `>=1.0.2,<2.0` allows drift within 1.x, so the item-3 test is the guard against a future minor changing the message shape.
- **Built-in capabilities that already support the feature:** callable `handle_tool_errors` (already used).
- **Current recommended APIs or workflows:** unchanged.
- **Important caveats, deprecations, or migration notes:** none found for `handle_tool_errors` between 1.0 and 1.1.
- No new dependency is added and no other external system is touched — beyond the single version-specific ToolNode item above: `- none (local-only; no external surface)`.

---

## Recommendation

- **Primary recommendation:** reuse existing seams, item by item:
  1. **Message (item 1):** in `book_hotel` build the string from `existing.details` — `hotel.name`/`existing.details.hotel_name`, `existing.details.check_in→check_out`, `existing.details.rooms room(s)` (optionally `adults/children` since CR-6 leaves them unmatched). Leave `book_flight` as is (no defect, evidence above) or use `existing.details.flight_number` for symmetry. Test at service level next to `tests/services/test_booking_duplicate.py:96-109`: existing 1-room booking + 3-room request → detail contains `"1 room(s)"` and not `"3 room(s)"`.
  2. **Per-booking override guard (item 2) — recommended scheme: embed `existing.id` in the marker and decide refusal *after* the service raises.**
     - `app/exceptions.py`: keep `DUPLICATE_WARNING_MARKER = "[possible-duplicate"`-style prefix constant and have `DuplicateBookingError.__init__` append `f"[possible-duplicate:{existing.id}]"` (id = canonical UUID, `app/schemas/booking.py:108-120`). Add `duplicate_warned_ids_this_turn(tool_name, messages) -> set[str]` in `_idempotency.py` (regex over the same message window); a bare legacy `[possible-duplicate]` with no id → return a wildcard sentinel so old checkpointed threads still refuse (fail-safe, matches today's behaviour).
     - Tools: `warned = duplicate_warned_ids_this_turn(...)`; call the service with `check_duplicate = (not allow_duplicate) or bool(warned)`. In `except DuplicateBookingError as e`: `refused = allow_duplicate and (WILDCARD in warned or e.existing.id in warned)`; if refused → raise with `OVERRIDE_REFUSED_HINT` (as today); if `allow_duplicate` and not refused (warning was about a *different* booking) → call the service again on the same session with `check_duplicate=False` and return it. The second call is on the same transaction the first one opened (`session_scope`, `flight_tools.py:473`), so the per-owner xact lock already held is simply re-entered.
     - Why this beats a request fingerprint: the tool cannot compute "which existing booking would I match" before the call — `flight_id` and `flight_number+route+date` are two spellings of the same row (`booking_service.py:389-418`), and `turn_idempotency_key` hashes `notes`, names, emails (`flight_tools.py:452-467`), so a fingerprint keyed on tool args would treat a same-booking re-run with an edited `notes` as "different" and honour the override without the traveller speaking — a regression from today's fail-safe. `existing.id` is resolved by the service for both spellings and is immune to arg noise.
  3. **Runtime test (item 3):** new `tests/agents/test_booking_duplicate_turn.py` modelled on `test_booking_turn_no_revise.py`. Seed an OWNER booking for the seeded flight via `BookingService.book_flight` (no turn context), then one graph turn: `main=FakeLLM(structured_responses=[SupervisorIntent(target_agent="booking")], responses=[book_flight(call-1), "There is already a booking — shall I book again?", book_flight(call-2, allow_duplicate=True), "Still waiting for confirmation"])`, `fast=FakeLLM(responses=["REVISE"])`; `_invoke` → interrupt → `Command(resume={"approved": True})`. Assert: 2 `book_flight` ToolMessages both `status=="error"`, first contains the marker text produced by the **real** handler (assert `DUPLICATE_WARNING_MARKER in content` and `content.startswith("Tool call failed:")`), second contains `OVERRIDE_REFUSED_HINT`, `fast._cursor == 1`, `main._cursor == 4`, `_rows == 1`. Second test: a new `HumanMessage` turn on the same thread with `allow_duplicate=True` scripted → `status=="success"`, `_rows == 2`. Third test (item 2): warning for flight A, then `book_flight(B, allow_duplicate=True)` in the same turn → B books, `_rows` grows by 1 (needs a second seeded flight or a different `passengers` count). Hotel mirror optional (same code path; the hotel tool differs only in args).
  4. **Check order (item 4):** in `book_hotel`, move `guests = …; if not hotel_service.is_available(...)` above the `if check_duplicate:` block. `is_available` is pure (no DB), so it needs no lock and the lock block still wraps replay-under-lock → `list_active_by_reference` → insert exactly as gh-198 requires. Keep `_replay` (pre-lock) first so an idempotent replay never re-runs availability. `book_flight` has no availability check → nothing to reorder. Update the `book_hotel` docstring ("before the availability check" at `booking_service.py:483-484` becomes "after"). Test: patch `hotel_service.available_rooms` to 0 (pattern `tests/tools/test_booking_tools.py:264-276`) with an existing identical booking → `ConflictError`, not `DuplicateBookingError`.
- **Why this is the lightest credible path:** no new module, no schema, one new helper + one regex; all four items are ≤ ~60 lines of production code plus tests, and every runtime seam is already exercised by an existing test file the new test can mirror.
- **Why the next-best alternative lost:** fingerprint-in-marker (hash of duplicate-key args) — cheaper at call time but unsound across `flight_id` vs `flight_number` spellings and arg noise (above). Comparing full args in the guard — heavier parsing of prose ToolMessages. Running a second `DuplicateBookingError` check inside the service — moves policy out of the tool that owns the turn context.
- **What would change this recommendation:** if the plan decides the tool must never issue two service calls in one invocation, fall back to embedding both `existing.id` *and* the resolved reference (`flight.id` / `hotel.id` + match key) in the marker and pre-resolving the reference in the tool via `FlightService.find_flight_by_*` — more code, same soundness.

---

## Risks, Unknowns, and Follow-Up Questions

- **Technical risks:**
  - **Branch is stale (blocker for planning, not for this brief):** the worktree branch was cut from local `main` (`ef9aec1`), 11 commits behind `github/main`; PR #203's lock block and PR #204's tool changes are absent, and `booking_service.py` is edited by both #203 and this slice → merge/rebase first, then verify `grep -n lock_owner_bookings apps/api/app/services/booking_service.py` → 2 hits before writing PLAN.md. Intake's "gh-198 also merged, so `book_hotel` now runs under the lock" is true on `github/main` only.
  - Item 2 changes the marker text; any external consumer would break — search surface shows none outside `app/tools` (`grep -rn "possible-duplicate"` over `apps/api/app`, `apps/api/tests`, `apps/web/src`), but persisted checkpoints carry the old bare marker → keep the wildcard fallback.
  - Item 4 makes a sold-out + duplicate request take the lock never (raises before) — fine; but keep the lock *before* `list_active_by_reference` or gh-198's concurrency proof (`test_booking_duplicate_concurrency.py`, Postgres-only) regresses silently on SQLite CI. Run `make test-docker` for that file.
  - `ruff-on-edit` strips unused imports — add helper import + usage in one edit (memory `ruff-on-edit-strips-unused-imports`).
- **Evidence gaps:** none material; Postgres lock behaviour on the double-call path (re-entering `pg_advisory_xact_lock` in the same transaction) is standard Postgres semantics, asserted from knowledge, not from a local test → cover with the existing concurrency test run on Docker.
- **Version uncertainties:** `langgraph-prebuilt` may drift within `<2.0`; the item-3 test is the tripwire.
- **Follow-up questions for the user:** (1) Should a legacy bare `[possible-duplicate]` marker (pre-change checkpoints) keep refusing the override (recommended yes)? (2) Should the hotel message also spell out `adults/children` of the existing booking, given they are not part of the match key?

---

## Source Pack

- **Local files read:** `specs/gh-200-duplicate-warning-polish/SUMMARY.md`; `.claude/rules/research-depth.md`; `.claude/rules/behavior.md`; `.claude/skills/xia2/references/research-brief-template.md`; `CLAUDE.md`; `techstacks/langgraph.md`; `techstacks/guidelines.md:56-64`; `../travel-pi/specs/gh-194-duplicate-booking-warning/SUMMARY.md:67-93`; `../travel-pi/specs/gh-198-booking-duplicate-check-atomic/SUMMARY.md`; `docs/solutions/agent/{explicit-args-schema-breaks-tool-injection,reflection-humanmessage-language-flip,chat-booking-unreachable-three-blockers}.md`; `apps/api/app/services/booking_service.py`; `apps/api/app/services/hotel_service.py:33-105`; `apps/api/app/exceptions.py:55-115`; `apps/api/app/tools/_idempotency.py`; `apps/api/app/tools/_base.py:45-130`; `apps/api/app/tools/flight_tools.py:367-505`; `apps/api/app/tools/hotel_tools.py:486-620`; `apps/api/app/agents/subagents/_base.py:46-290`; `apps/api/app/agents/subagents/booking.py`; `apps/api/app/agents/retry.py:77-160`; `apps/api/app/agents/nodes.py:196-300`; `apps/api/app/agents/constants.py:74-88`; `apps/api/app/agents/context.py:39-46`; `apps/api/app/agents/graph.py:61-80`; `apps/api/app/clients/llm.py:164-235`; `apps/api/app/schemas/booking.py:14-155`; `apps/api/requirements-ai.txt`; `apps/api/tests/tools/test_booking_duplicate_tools.py`; `apps/api/tests/tools/conftest.py:18-45`; `apps/api/tests/services/test_booking_duplicate.py`; `apps/api/tests/agents/test_booking_turn_no_revise.py`; `apps/api/tests/agents/test_reflection_booking_guard.py`; `github/main:apps/api/app/services/booking_service.py:415-575`; `github/main:apps/api/app/repositories/booking.py:36-60,184-230`; `github/main:apps/api/tests/services/test_booking_owner_lock.py`; `github/main:apps/api/tests/services/test_booking_duplicate_concurrency.py`; `.venv/lib/python3.14/site-packages/langgraph/prebuilt/tool_node.py:111,394-442,1140-1160`; `.claude/hooks/risk-corroboration.sh:167`.
- **Upstream repositories or pages checked:** `https://raw.githubusercontent.com/langchain-ai/langgraph/prebuilt==1.1.0/libs/prebuilt/langgraph/prebuilt/tool_node.py`
- **Official docs domains or pages checked:** `https://reference.langchain.com/python/langgraph/prebuilt/` (404); otherwise `- none (local-only; no external surface)`

---

## Depth classifier re-run (evidence)

- Migration/schema/data-loss: none (no `alembic/` or model change in scope; `grep -rn "check_duplicate=" app/routers` on gh-198 intake → 0, REST untouched).
- High-blast file: the hook's set is `settings.json`, `hooks/*`, `render_plan.py` (`.claude/hooks/risk-corroboration.sh:167`) — none touched.
- New dependency / external integration / shared runtime config: none.
- Auth / session / transaction scope: the lock block is reused, not changed; the double-call in item 2 stays inside the tool's existing `session_scope` transaction → not a scope change.
- → **Standard holds.** Deep signal found: **none** in the change itself; the stale-branch finding is a process blocker, not a risk-class change.

## Evidence Boundary

> Confirmed from artifacts: all `Local` rows above (file:line cited); PR #203 merged and absent from the worktree HEAD; installed langgraph-prebuilt 1.1.0 matches the tag source on the quoted lines; `is_available` is session-free; error ToolMessages carry `name=call["name"]`, `status="error"`, `content=handler(e)`.
> Inferred from patterns: re-entering `pg_advisory_xact_lock` within one transaction is harmless (Postgres semantics, not tested here); the FakeLLM script for item 3 will interrupt at `plan_node` exactly as gh-193's test does (same route, same tools).
> Not checked: the booking prompt's behaviour with real models on the refused-override reply (LLM-dependent, out of scope); PR #204's tool-schema refactor against `flight_tools.py`/`hotel_tools.py` — `git diff HEAD github/main` on those two files is empty, so no interaction expected; `apps/web` rendering of tool-error text (no marker consumer found there).
