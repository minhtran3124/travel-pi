# Research Brief — MIN-42 Implement MCP tool (book/cancel over MCP)

> Depth: **Standard**. xia2's `PROJECT.md` is the un-specialized harness template (describes
> the harness-skills meta-repo, not this FastAPI backend) — signals below were derived from the
> repo's own `CLAUDE.md` + `.claude/rules/` instead. Recommend `/bootstrap-xia2` to calibrate it.

## Bottom Line

| Field | Value |
|---|---|
| **Recommendation** | **Reuse existing** — clone the `book_hotel` tool pattern; add 3 thin wrappers + registry entries + tests. No new code paths, no `app/mcp/` change. |
| **Why this is the lightest credible path** | Every backing service method (`book_flight`, `cancel`, `get`) already exists and is tested; MCP exposure is fully registry-driven (`build_mcp_server()` iterates `ALL_TOOLS`), so registry membership alone serves the tools with correct destructive hints. |
| **Confidence** | 95% |
| **Next step** | `/writing-plans` → PLAN.md (3–4 tasks, 2 waves). Nothing blocks. |

---

## Repo Snapshot

| Field | Detected |
|---|---|
| Repo type | Monorepo (pnpm + Turborepo); BE = FastAPI in `apps/api/` |
| Primary language + runtime | Python 3.10+ (Docker tests 3.12; local 3.14) |
| Frameworks / platforms | FastAPI, SQLAlchemy 2.0, Pydantic v2, LangGraph, MCP python SDK (`ToolAnnotations`) |
| Relevant packages | `langchain_core.tools` (`@tool`, `ToolException`), MCP server SDK |
| Detectable versions | from `apps/api/requirements.txt` (not version-bumped — no new dep) |
| Important constraints | Layering routers→services→repositories; ORM only in repositories; tools/MCP are thin adapters — **no business logic**. `datetime.now(timezone.utc)`. |

---

## Feature Understanding and Assumptions

- **Requested feature:** Expose `book_flight`, `cancel_flight`, `cancel_hotel` as agent tools so they are callable over MCP by external clients, alongside existing search/book tools.
- **What success appears to mean:** The 3 tools are discoverable + callable over MCP with `destructiveHint=True` and "Cannot be undone." in the description; valid input books/cancels the right `Booking`; invalid input (unknown id, missing `confirm`, wrong booking type) raises a graceful `ToolException`; `make test` passes.
- **Assumptions from the request:** Cancel is destructive + guarded by `confirm=True`; two separate cancel tools (not one generic), each guarding on `booking.type`.
- **Assumptions still needing confirmation:** None material — the Linear issue pre-resolved the two design forks.

---

## Evidence Ledger

| Label | Evidence |
|---|---|
| `Local` | `book_hotel` is the exact template: `@tool(args_schema=BookHotelArgs)` + `confirm` guard + `session_scope()` + `BookingService(s).book_hotel(request)` + `except AppError/ValueError → ToolException` (`app/tools/hotel_tools.py:325-381`). |
| `Local` | `BookingService.book_flight(request, idempotency_key=None) -> Booking` (`:210`); `.cancel(booking_id) -> Booking` idempotent, takes UUID or 6-char code (`:129`); `.get(booking_id) -> Booking` resolves UUID then confirmation-code (`:96`). `cancel`/`get` are **type-agnostic** — the wrong-type guard must live in the tool. |
| `Local` | `booking.type` is `BookingType` str-enum (`"flight"`/`"hotel"`, `app/enums.py:11-15`); guard = `if booking.type != BookingType.FLIGHT: raise ToolException(...)`. |
| `Local` | `FlightBookingRequest` already accepts `flight_id` **XOR** `flight_number`+`origin`+`destination`+`departure_date` (model_validator `_exactly_one_identifier`, `app/schemas/flight.py:223`) + `passenger_name/email/phone`. Shipped by `specs/symmetric-booking-inputs`. |
| `Local` | `registry.py`: `TOOLS_BY_DOMAIN["booking"] = FLIGHT_TOOLS + HOTEL_TOOLS` (`:38`); `_DESTRUCTIVE = {"book_hotel"}`, `_WRITE = {..., "book_hotel"}` (`:49-56`); `ALL_TOOLS` dedups by name; `TOOL_METADATA` derived. |
| `Local` | `app/mcp/server.py build_mcp_server()` iterates `ALL_TOOLS`, appends `" Cannot be undone."` when `meta["destructive"]` (`:32-33`), skips fns with a `store` param, emits `ToolAnnotations(readOnlyHint, destructiveHint)` (`:42-46`). **No change needed.** |
| `Local` | Tests: `tests/tools/test_booking_tools.py` uses real `agent_db` fixture (no FakeLLM), invokes `book_hotel.invoke({...})`, asserts `pytest.raises(ToolException, match="confirm=true")`. `tests/mcp/test_mcp_server.py::test_destructive_tool_annotations` asserts `"Cannot be undone." in book.description` + `annotations.destructiveHint is True`. |
| `Local` | MIN-46 (`specs/standardize-tool-args-schema`, **related** to MIN-42 in Linear) sets the standard: every tool ships an explicit `args_schema=` Pydantic model with `Field(description=...)`. New tools must follow this from the start. |
| `Inference` | The known `explicit-args-schema-breaks-langgraph-injection` bug does **not** bite: these 3 tools take no `InjectedState`/`InjectedStore`, matching `book_hotel`. |

---

## Local Findings

- **Reuse target:** `book_hotel` (`app/tools/hotel_tools.py:325-381`) is a line-for-line template for `book_flight` and both cancels.
- **Extension points:** `registry.py` `_WRITE`/`_DESTRUCTIVE` sets + domain groups; MCP surface is automatic.
- **Conventions to preserve:** args model subclasses `AppBaseModel` with `confirm: bool = Field(False, ...)`; error mapping `AppError`→`ToolException` then `ValueError`→`ToolException`; helpers from `app.tools._base` (`session_scope`, `dump`, `log_tool_call`, `panel_result`).
- **Reusable:** all backing service methods; the MCP mapper; the test fixtures (`agent_db`, `tests/tools/conftest.py`).
- **Missing locally:** the 3 tool functions + their args models; a home for the cancel tools (issue proposes a new `app/tools/booking_tools.py`, but note booking tools currently live inside domain files — see Risk #1).

---

## Upstream Findings

- **Skipped** — the reuse target is in-repo and authoritative. The MCP `destructiveHint`/`readOnlyHint`/`ToolAnnotations` contract is already implemented per the MCP spec in `server.py`; no upstream pattern would beat cloning `book_hotel`.

## Docs Findings

- **Skipped** — no `server.py` / dependency change, so no version-matched doc lookup is on the critical path. The MCP annotation semantics are already encoded locally.

---

## Recommendation

- **Primary:** Reuse `book_hotel` → 3 thin wrapper tools, each with an explicit `args_schema` (MIN-46 standard), a `confirm=True` guard, `session_scope()`, and `AppError/ValueError → ToolException` mapping. Cancel tools additionally `BookingService.get()` then guard `booking.type` before `.cancel()`. Register all 3 in `_WRITE` + `_DESTRUCTIVE` and the correct domain groups. Add tool + MCP tests mirroring the existing ones.
- **Why lightest:** zero new business logic, zero `app/mcp/` change, zero new deps, zero schema/migration — the diff is adapters + registration + tests.
- **Why next-best lost:** a single generic `cancel_booking` tool was explicitly ruled out in the issue in favor of two type-specific tools for an explicit MCP surface.
- **What would flip it:** if `BookingService.cancel`/`get` did not already exist or were not type-agnostic — but they do and are (`:129`, `:96`).

---

## Risks, Unknowns, and Follow-Up Questions

- **Risk #1 — file placement (low):** The issue proposes a new `app/tools/booking_tools.py` for the cancels, but existing booking tools live inside domain files (`hotel_tools.py`). A new module is fine and cleaner for the cross-type cancels, but the group must be wired into `TOOLS_BY_DOMAIN["booking"]` so `ALL_TOOLS` picks it up — an easy miss that would silently drop the tools from MCP. Verify with the MCP test.
- **Risk #2 — args_schema + LangGraph (mitigated):** follow `book_hotel` exactly; do not add injected params. Run `ruff --select F821` before tests (per `ruff-on-edit-strips-unused-imports`).
- **Risk #3 — public-contract corroboration hook:** additive MCP surface may trip `risk-corroboration.sh`; authorize at commit with `RISK_WARN_CATEGORIES="public-contract"` if it fires (per `public-contract-hard-gate`).
- **Risk #4 — stale `travel.db`:** no schema change here, so unaffected — but if the suite errors on setup, rebuild `travel.db` (per `stale-travel-db-breaks-suite-on-schema-change`).
- **Follow-up questions:** none needed — the issue pre-resolved both design forks.

---

## Source Pack

- **Local files read:** `app/tools/hotel_tools.py`, `app/tools/flight_tools.py`, `app/tools/registry.py`, `app/tools/_base.py`, `app/services/booking_service.py`, `app/schemas/flight.py`, `app/schemas/booking.py`, `app/enums.py`, `app/mcp/server.py`, `tests/tools/test_booking_tools.py`, `tests/tools/conftest.py`, `tests/mcp/test_mcp_server.py`; specs `symmetric-booking-inputs/`, `standardize-tool-args-schema/`.
- **Upstream / Docs:** none (in-repo pattern authoritative).

---

## Evidence Boundary

> **Confirmed from artifacts:** the 3 backing service methods exist with the cited signatures; `book_hotel` template shape; MCP auto-exposure + "Cannot be undone." append; `FlightBookingRequest` dual-identifier; registry `_WRITE`/`_DESTRUCTIVE` sets; test patterns; `booking.type` enum values.
> **Inferred from patterns:** the args_schema/injection bug won't bite (no injected params in these tools); a new `booking_tools.py` module is acceptable provided it's wired into the booking domain group.
> **Not checked:** live MCP handshake against Claude Desktop / Agent SDK (out of scope — tests assert the annotation surface); exact `FlightBookingRequest` optional-field list beyond `notes`.
