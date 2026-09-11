---
slug: gh-193-booking-revise-idempotency
status: active
owner: minhtran3124
created: 2026-09-11
---

# gh-193 — booking REVISE idempotency + reflection write guard

## 1. Motivation

`reflection` routes a REVISE to `state["current_flow"]` (`app/agents/nodes.py:253`). On the booking path the supervisor sets `current_flow="booking"` (`app/agents/supervisor.py:449`) and `plan_node` never overwrites it, so a REVISE re-runs the `booking` sub-agent without the `plan` interrupt. `book_flight` / `book_hotel` call `BookingService.book_*` without the `idempotency_key` the service already replays on (`app/services/booking_service.py:276-291`), so a second `confirm=True` call on the revise pass — or on any re-run of the same turn — creates a second reservation. The fix is plumbing in the tool wrappers plus a cheap guard in reflection; no service, schema, prompt, or graph-topology change. Intent, intake facts and the intake probe live in `SUMMARY.md` and `evidence/probe_tool_config.py`.

## 2. Non-goals

- Duplicate-*intent* detection across turns or threads (GitHub #194).
- Re-gating a REVISE through `plan_node`, or moving the HITL `interrupt()` into the tools.
- Any change to `BookingService`, the `bookings` schema, the REST `Idempotency-Key` path, prompts, or the MCP surface.
- Keying on `tool_call_id` or on `user_id + args` alone (both rejected in `SUMMARY.md` → Alternatives; the latter was reverted in `2c44f99`).

## Global Constraints

- The key is `sha256("|".join([user_id, thread_id, last_human_message_id, tool_name, canonical_args]))` where `canonical_args` is `json.dumps(model_visible_args, sort_keys=True, separators=(",", ":"), default=str)`; model-visible args exclude every injected parameter (`user_id`, `trip_id`, `messages`) and `config`. When `thread_id` or a last `HumanMessage` is unavailable the key is `None` and the service is called exactly as today.
- `tests/tools/test_flight_booking_tool.py::test_book_flight_repeated_call_creates_distinct_bookings` stays green: two identical `book_flight.invoke(args)` calls with no thread/turn context still create two bookings.
- `book_flight.args` / `book_hotel.args` (the model-visible schema) gain no new keys; injected fields are declared in the pydantic `*Args` schema the same way `user_id`/`trip_id` already are (`app/tools/flight_tools.py:322-330`).
- The new `app/tools/_idempotency.py` imports nothing from `app.agents` (other tool modules already import `app.agents.context`; do not add more). The write-tool names used by reflection are string constants in `app/agents/constants.py`, pinned to the tool objects by a test; `nodes.py` binds the name at import (`from app.agents.constants import BOOKING_WRITE_TOOLS`), so tests that need to disable the guard monkeypatch `app.agents.nodes.BOOKING_WRITE_TOOLS`.
- Every task `Verify` and every SC check runs from `apps/api` via `cd apps/api && ../../.venv/bin/python …`, is pipe-free and finishes in under 60 s; the full suite runs only at `finishing-a-development-branch`.
- No `Co-Authored-By`/tooling trailers in commit messages (`CLAUDE.local.md`).

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|------|-------------------------|-----------------------|------------|
| SC-1 | The key helper is deterministic for the same turn+args, differs across thread, turn, tool and args, ignores injected/config inputs, and returns `None` without a thread or a `HumanMessage` | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_booking_idempotency_key.py -q` | exit 0 |
| SC-2 | Two `book_flight` / `book_hotel` calls with the same thread + last `HumanMessage` + args return the same booking id and store one row; a second turn (new `HumanMessage`) stores a new row | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_booking_idempotency_tools.py -q` | exit 0 |
| SC-3 | Identical calls with no thread/turn context still create distinct bookings (pinned behaviour, `2c44f99`) | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_flight_booking_tool.py -q` | exit 0 |
| SC-4 | Reflection ends the turn without calling the judge when this turn holds a successful `book_*` `ToolMessage`; an errored `book_*` or a write from an earlier turn still reaches the judge | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_reflection_booking_guard.py -q` | exit 0 |
| SC-5 | End-to-end booking turn (plan interrupt → approve → booking → reflection) with a judge scripted to say REVISE: (1) with the guard, the judge is never called, the booking assistant runs once, one booking row, no revise note; (2) with the guard disabled, REVISE re-runs booking, the second `book_flight` call replays via the key, still one booking row | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_booking_turn_no_revise.py -q` | exit 0 |
| SC-6 | The model-visible schema of both write tools is unchanged (no `messages`/`config` key) | `cd apps/api && ../../.venv/bin/python -c "from app.tools.flight_tools import book_flight; from app.tools.hotel_tools import book_hotel; assert 'messages' not in book_flight.args and 'config' not in book_flight.args and 'messages' not in book_hotel.args and 'config' not in book_hotel.args"` | exit 0 |
| SC-7 | Lint and format are clean on the touched packages | `cd apps/api && ../../.venv/bin/ruff check app tests` | exit 0 |

## 4. Tasks

### Task 1.1 — Turn-scoped idempotency key helper (wave 1)

- **Files:** apps/api/app/tools/_idempotency.py, apps/api/tests/tools/test_booking_idempotency_key.py
- **Action:** Test-first. Add `turn_idempotency_key(tool_name: str, args: dict, *, user_id: str, config: RunnableConfig | None, messages: list | None) -> str | None` in a new private module next to `_base.py`. Read `thread_id` from `config["configurable"]["thread_id"]`; take the id of the last `HumanMessage` in `messages`; return `None` if either is missing or empty. Drop the injected/config names (`user_id`, `trip_id`, `messages`, `config`) from `args` before canonicalising with `json.dumps(sort_keys=True, separators=(",", ":"), default=str)`; hash the five parts joined by `|` with sha256 and return the hex digest. Tests: same inputs → same key; each of thread, human-message id, tool name, and one arg changed → different key; injected keys present or absent → same key; no `thread_id` → `None`; no `HumanMessage` → `None`; `messages` containing a trailing `SystemMessage` (the revise note) after the `HumanMessage` → same key as without it.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_booking_idempotency_key.py -q`
- **Done:** All helper tests pass; the module imports only stdlib, `langchain_core`, and nothing from `app.agents`
- **Criteria:** SC-1
- **Interfaces:** Consumes the langchain RunnableConfig and the graph messages list (external inputs). Produces `app/tools/_idempotency.py` exposing `turn_idempotency_key` and `INJECTED_ARG_NAMES`.

### Task 1.2 — Reflection ends a turn that already committed a booking (wave 1)

- **Files:** apps/api/app/agents/constants.py, apps/api/app/agents/nodes.py, apps/api/tests/agents/test_reflection_booking_guard.py
- **Action:** Test-first. Add `BOOKING_WRITE_TOOLS = frozenset({"book_flight", "book_hotel"})` to `constants.py` and a helper in `nodes.py` that returns True when any `ToolMessage` *after the last `HumanMessage`* has `name in BOOKING_WRITE_TOOLS` and `status != "error"`. In `make_reflection_node`, directly after the `awaiting_user` guard (`nodes.py:231-233`) and before the context/revision checks, return `Command(goto=END)` with an info log `"[agent] reflection → END (booking committed this turn; not reviewable)"` when the helper is True. Tests, modelled on `tests/agents/test_depth_toggles.py` (`_base_state`, `_runtime`, `FakeLLM(responses=["REVISE"])`): successful `book_flight` `ToolMessage` this turn → `goto == END` and the FakeLLM cursor did not advance; `status="error"` → judge runs; a successful `book_*` `ToolMessage` *before* the last `HumanMessage` → judge runs; a non-booking tool (`search_flights`) this turn → judge runs; and a pin test asserting `BOOKING_WRITE_TOOLS == {book_flight.name, book_hotel.name}`.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_reflection_booking_guard.py -q`
- **Done:** Guard tests pass; `tests/agents/test_depth_toggles.py` still passes (run it in the task, cite in the commit)
- **Criteria:** SC-4
- **Interfaces:** Consumes the graph state messages list (external input). Produces `BOOKING_WRITE_TOOLS` in `app/agents/constants.py` and the guard in `app/agents/nodes.py`.

### Task 2.1 — Wire the key into book_flight and book_hotel (wave 2)

- **Files:** apps/api/app/tools/flight_tools.py, apps/api/app/tools/hotel_tools.py, apps/api/tests/tools/test_booking_idempotency_tools.py
- **Action:** Test-first. In both `BookFlightArgs`/`BookHotelArgs` add `messages: Annotated[list, InjectedState("messages")] = Field(default_factory=list, description="Injected conversation messages from graph state — never supplied by the model.")`, and in both tool signatures add `messages: Annotated[list, InjectedState("messages")] = None` and a bare `config: RunnableConfig` (no `| None`, no default: `langchain_core/tools/base.py` `_get_runnable_config_param` matches the annotation by identity, so a union is never injected and the key would always be `None`; `config` is NOT added to the pydantic schema). The intake probe `specs/gh-193-booking-revise-idempotency/evidence/probe_tool_config.py:24` declares it exactly this way and shows both stay out of `tool.args`. Build the key with `turn_idempotency_key("book_flight" | "book_hotel", <the model-visible args as a dict>, user_id=user_id, config=config, messages=messages)` after the `confirm` guard and pass it as `idempotency_key=` to `BookingService(s).book_flight` / `.book_hotel`. Do not log the key. Tests (`agent_db` fixture, seeded flight/hotel like `tests/tools/test_flight_booking_tool.py`): (a) two `book_flight.invoke({... , "user_id": OWNER, "messages": [HumanMessage(id="h1", ...)]}, config={"configurable": {"thread_id": "t1"}})` calls → same `id`, one row for OWNER; (b) same with a second call whose `messages` ends in a new `HumanMessage(id="h2")` → two rows; (c) same as (a) for `book_hotel`; (d) invoke without `config` → two rows (the pinned behaviour, cross-checked by SC-3); (e) compile the booking sub-agent via `build_booking` with a `FakeLLM` scripted to emit the `book_flight(confirm=True)` tool call then a reply, `invoke` it twice with the same state — the `HumanMessage` MUST carry an explicit id (`HumanMessage(id="h1", content=...)`: with no checkpointer `add_messages` mints a fresh uuid per invoke, and an id-less message would yield two keys) — and the same `thread_id` config → one row.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_booking_idempotency_tools.py tests/tools/test_flight_booking_tool.py tests/tools/test_hotel_tools.py -q`
- **Done:** New tests pass; the two existing tool test files pass unchanged; `book_flight.args` and `book_hotel.args` have no `messages`/`config` key
- **Criteria:** SC-2, SC-3, SC-6
- **Interfaces:** Consumes `turn_idempotency_key` from `app/tools/_idempotency.py` (Task 1.1). Produces the keyed write path in `app/tools/flight_tools.py` and `app/tools/hotel_tools.py`.

### Task 2.2 — End-to-end booking turn does not revise (wave 2)

- **Files:** apps/api/tests/agents/test_booking_turn_no_revise.py
- **Action:** Using the `_build`/`_invoke`/`_drive` pattern from `tests/agents/test_multi_intent_routing.py::test_booking_hitl_detour_untouched_by_dispatch`. The `agent_db` fixture lives in `tests/tools/conftest.py` and is not visible from `tests/agents/`: define a local `agent_db` fixture in this file mirroring `tests/agents/test_plan_everything.py:69`. Case 1 (guard on): supervisor `SupervisorIntent(target_agent="booking")`; main `FakeLLM` responses = [`AIMessage(tool_calls=[book_flight(... seeded flight ..., confirm=True)])`, `"Booked!"`, `AIMessage(tool_calls=[same call])`, `"Booked again"`]; fast `FakeLLM` responses = [`"REVISE"`, `"OK"`]. Run the turn, resume the `plan` interrupt with `{"approved": True}`. Assert: exactly one booking row for the user; the last `AIMessage` is `"Booked!"` and no message contains `"Booked again"`; no `SystemMessage` carrying `REFLECTION_REVISE_NOTE` is persisted; `fast._cursor == 0` (the judge was never called — this is the assertion that pins part B); `main._cursor == 2` (the booking assistant ran once); `state.get("revisions", 0) == 0`. Case 2 (guard off — the literal issue test, proving part A end-to-end): same build, but `monkeypatch.setattr("app.agents.nodes.BOOKING_WRITE_TOOLS", frozenset())` before the turn; assert the turn completes without interrupt after resume, `fast._cursor == 2` (REVISE then OK), `main._cursor == 4` (booking ran twice), exactly one booking row, and the two `book_flight` `ToolMessage`s carry the same booking `id` (the second call replayed via the key).
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_booking_turn_no_revise.py -q`
- **Done:** Both end-to-end cases pass and the file runs in under 20 s
- **Criteria:** SC-5
- **Interfaces:** Consumes the guard from Task 1.2 and the keyed tools from Task 2.1 (via the compiled graph). Produces `tests/agents/test_booking_turn_no_revise.py`.

### Task 3.1 — Lint, targeted regression, record (wave 3)

- **Files:** specs/gh-193-booking-revise-idempotency/SUMMARY.md
- **Action:** Run `ruff check app tests` and `ruff format --check` on the touched files; run the targeted regression set `tests/agents/test_depth_toggles.py tests/agents/test_multi_intent_routing.py tests/agents/test_graph.py tests/tools tests/mcp` (cite the counts in SUMMARY prose, not as a Verify row). Fill `## What changed`, `### Verify` (one row per SC actually run, `Criterion` column mapped), `### Not auto-verified`, `### Rollback` (`git revert` of the task commits) in `SUMMARY.md`.
- **Verify:** `cd apps/api && ../../.venv/bin/ruff check app tests`
- **Done:** `python3 .claude/scripts/verify_summary.py --check gh-193-booking-revise-idempotency` exits 0 from the repo root
- **Criteria:** SC-7
- **Interfaces:** Consumes the results of Tasks 1.1–2.2. Produces the completed `specs/gh-193-booking-revise-idempotency/SUMMARY.md`.

## 5. Risks

- `InjectedState("messages")` on a tool with an explicit `args_schema`: the schema must declare the field or `ToolNode` injection breaks (`docs/solutions/agent/explicit-args-schema-breaks-tool-injection.md`). Mitigated by declaring it in both `*Args` classes exactly like `user_id`.
- `messages` injected into a tool copies the whole conversation into the tool call; it is never logged (`log_tool_call` already lists only flight identifiers) and never returned.
- A `HumanMessage` without an id would yield `None` → no replay. `add_messages` assigns ids on write, and Task 2.2 proves it end-to-end with an id-less `HumanMessage`.
- `risk-corroboration.sh` may flag the word `session` in `session_scope` lines or `hash`/`secret`-like tokens; the lane stays normal — reword, do not weaken the gate.
- Anthropic-configured specialists already crash on REVISE (`SystemMessage` mid-history, pre-existing, noted in PR #192); Task 1.2 reduces exposure on the booking path but does not fix it.

## 6. Status Log

- 2026-09-11 — plan written after intake (`SUMMARY.md`); branch `fix/gh-193-booking-revise-idempotency` at `b96569a`.
- 2026-09-11 — clean baseline in the worktree before any change: `cd apps/api && ../../.venv/bin/python -m pytest -q -x` → 2412 passed, 0 failed (198 s; whole-suite, cited here per the layer-ladder rule, never as a Verify row).
- 2026-09-11 — plan review (1 chunk, 1 pass): 3 issues fixed — bare `config: RunnableConfig` (union is never injected), local `agent_db` fixture for `tests/agents`, explicit `HumanMessage` id in Task 2.1(e); advisories taken: `fast._cursor == 0` pins part B, guard-off case in Task 2.2 proves part A end-to-end, import-direction constraint reworded. `check_plan_contract.py` passes. Status → active.
