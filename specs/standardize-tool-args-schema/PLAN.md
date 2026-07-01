---
slug: standardize-tool-args-schema
status: shipped
owner: Minh Tran
created: 2026-07-01
---

# Standardize `args_schema` across all agent tools (MIN-46)

> **For Claude:** REQUIRED SUB-SKILL: execute via `subagent-driven-development` (fresh subagent per task, two-stage review between tasks). Isolate the branch with `using-git-worktrees` first — this plan is `high-risk` lane.

**Goal:** Give every LangChain `@tool` in `apps/api/app/tools/` an explicit Pydantic `args_schema` with `Field(..., description=...)` on every param and `Literal`/`Enum` for finite-value params, so the agent model stops guessing/inventing tool arguments.

**Architecture:** Co-locate one `args_schema` class per tool at the top of its own domain module (LangChain idiom; keeps schema beside its tool; disjoint files → parallel waves). Each schema class extends `AppBaseModel` (`app/schemas/base.py`) and its fields mirror the function signature **exactly** (same names, required/optional, defaults). Reuse existing domain enums (`ExpenseCategory`, `TipCategory`, `TripItemKind`, `TripItemStatus`) instead of redefining `Literal`s. Validation is left to LangChain's `ToolNode` (built-in `args_schema` validation before invoke) — no redundant explicit `model_validate`.

**Tech Stack:** FastAPI · LangChain/LangGraph `>=1.0,<2.0` · Pydantic v2 · pytest.

---

## 1. Motivation

Linear **MIN-46**. All 21 tools across 10 domain files currently declare `@tool` on plain type hints (`str`, `int`) with no `args_schema`. Free-form `str` params that actually have a finite valid set (`sort`, `category`, `status`, `kind`, `source`) let the model hallucinate invalid values. Adding explicit schemas with descriptions + enums tightens the model-facing tool-calling contract.

## 2. Non-goals

- **No new tools** (out of scope per ticket; coordinate with MIN-42 so new tools ship with schemas).
- **No business-logic changes** inside `_run`/`_arun`/tool bodies.
- **No explicit `args_schema.model_validate(...)`** — LangChain's `ToolNode` already validates tool-call args against `args_schema` before invoking; an extra call would be dead code. (Intentional deviation from the ticket checklist — recorded in `SUMMARY.md`.)
- **No function-signature tightening for MCP** — `app/mcp/server.py` (FastMCP) derives its external schema from the raw function signature, not from `args_schema`, so the MCP-exposed schema stays as-is. The gap is documented; a follow-up ticket can tighten signatures if an external MCP client needs it. (Decision: option A.)
- **No registry change** — `registry.py` collects `BaseTool` instances unchanged; passing `args_schema=` to `@tool` needs no wiring.

## 3. Success Criteria

- Every tool in `app.tools.registry.ALL_TOOLS` has a **hand-authored** `args_schema` — one whose class `__module__` starts with `app.tools` (enforced by a new guard test). Note: LangChain auto-derives an `args_schema` from the signature when none is given, so `is not None` is *not* a sufficient check.
- Each `args_schema` mirrors its function's model-facing params exactly — same names, same required/optional, same defaults; **injected** params (`InjectedState`, `InjectedStore`) are **excluded** from the schema and the tool still receives them at call time.
- Finite-value params render as JSON-schema enums (via `Literal` or a reused `str`-Enum).
- Every field has `Field(..., description=...)`; docstrings updated to match.
- `cd apps/api && make test` green; `ruff check app scripts` clean.

## 4. Tasks

> **Shared conventions for every task below** (the executor applies these to each tool file):
> - Define schema class(es) at the **top of the tool module**, after imports, named `<ToolName>Args` (PascalCase of the tool, e.g. `SearchFlightsArgs`). Extend `AppBaseModel`.
> - Wire it: `@tool(args_schema=<Name>Args)`, preserving any existing `response_format="content_and_artifact"`.
> - **Field parity rule:** the schema's fields must match the function params 1:1 (names/required/optional/defaults). A mismatch makes LangChain raise at tool-build time — the `import app.tools.registry` step in each verify catches it.
> - Use `Field(..., description="…")` for required, `Field(default, description="…")` for optional. Pull descriptions from the existing docstring.
> - Reuse existing `str`-Enums where they exist (verify each is `class X(str, Enum)`); otherwise use `typing.Literal[...]`. Note: domain enums live in `app/enums.py` (e.g. `from app.enums import ExpenseCategory`), not under `app/schemas/`.
> - Update the tool docstring so the param descriptions match the schema (remove now-redundant "valid values" prose only where the enum makes it obvious; do not touch behavior prose).
> - Do **not** add `args_schema.model_validate` and do **not** change tool-body logic.

### Task 1.1 — flight_tools (exemplar: content_and_artifact + Literal sort + date guard)

Exemplar for the fan-out. Full code:

```python
# top of app/tools/flight_tools.py, after imports
from typing import Literal
from pydantic import Field
from app.schemas.base import AppBaseModel

FlightSort = Literal[
    "departure_asc", "departure_desc",
    "price_asc", "price_desc",
    "duration_asc", "duration_desc",
]

class SearchFlightsArgs(AppBaseModel):
    origin: str = Field(..., description="3-letter IATA origin airport code, e.g. 'HAN'.")
    destination: str = Field(..., description="3-letter IATA destination airport code, e.g. 'SGN'.")
    departure_date: str = Field(..., description="Departure date, ISO format YYYY-MM-DD. Must not be in the past.")
    airline: str | None = Field(None, description="Optional 2-letter IATA airline code to filter by.")
    max_price: float | None = Field(None, description="Optional maximum ticket price filter.")
    max_stops: int | None = Field(None, description="Optional maximum number of stops.")
    sort: FlightSort = Field("departure_asc", description="Result ordering.")
```

```xml
<task id="1.1" wave="1">
  <files>apps/api/app/tools/flight_tools.py, apps/api/tests/tools/test_flight_tools.py</files>
  <action>Add SearchFlightsArgs (code above) and set @tool(args_schema=SearchFlightsArgs, response_format="content_and_artifact") on search_flights. Keep the existing date-format/past-date ToolException guards untouched. Create test_flight_tools.py: (a) assert search_flights.args_schema is SearchFlightsArgs and .args_schema is not None; (b) assert the six sort values appear in search_flights.get_input_schema().model_json_schema(); (c) a valid ToolCall invoke still returns (content, artifact) — reuse the ToolCall invoke pattern from tests/tools/test_booking_tools.py; (d) an invalid sort (e.g. "cheapest") raises a validation error on invoke.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_flight_tools.py -q</verify>
  <done>search_flights carries SearchFlightsArgs; enum + parity + invalid-value tests pass.</done>
</task>
```

### Task 1.2 — memory_tools (edge case: exclude InjectedState / InjectedStore)

Critical edge case: `user_id` and `store` are injected (`Annotated[..., InjectedState/InjectedStore]`) and MUST NOT appear in `args_schema`, but the tool must still receive them at call time. Model-facing params only: `key`, `text` (save), `query` (get/recall).

```xml
<task id="1.2" wave="1">
  <files>apps/api/app/tools/memory_tools.py, apps/api/tests/tools/test_memory_tools.py</files>
  <action>Add SaveUserPreferenceArgs(key: str [req], text: str [req]), GetUserPreferencesArgs(query: str | None = None), RecallPastTripsArgs(query: str [req]) — each extending AppBaseModel with Field descriptions. Do NOT include user_id or store. Wire @tool(args_schema=...) on the three tools; leave the Annotated[..., InjectedState(...)] / InjectedStore params in the function signature unchanged. Create test_memory_tools.py asserting: each tool's args_schema is set; the JSON schema does NOT contain 'user_id' or 'store'; and the tools still expose user_id/store as injected args (e.g. via save_user_preference.get_input_schema — injected args excluded from model schema). If a full invoke needs a store fixture, assert schema shape only rather than executing, to keep <60s.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_memory_tools.py -q</verify>
  <done>Three memory tools carry schemas excluding injected params; tools still build and inject correctly.</done>
</task>
```

### Task 1.3 — expense_tools (exemplar: reuse existing str-Enum)

Reuse `ExpenseCategory` (verify it is `class ExpenseCategory(str, Enum)` in `app/schemas`); do not redefine as Literal. `currency` stays `str` (normalized upstream by `ExpenseCreate`).

```xml
<task id="1.3" wave="1">
  <files>apps/api/app/tools/expense_tools.py, apps/api/tests/tools/test_expense_tools.py</files>
  <action>Add AddExpenseArgs(trip_id: str [req], category: ExpenseCategory [req], amount: float [req, gt=0 via Field], currency: str [req], description: str | None = None), ListExpensesArgs(trip_id: str [req]), ExpenseSummaryArgs(trip_id: str [req]). Import ExpenseCategory from its schema module (verify it subclasses str, Enum; if not, use Literal of its values). Wire the three @tool decorators. Create test_expense_tools.py asserting each args_schema is set, the category enum values appear in the add_expense JSON schema, and amount has a >0 constraint.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_expense_tools.py -q</verify>
  <done>Three expense tools carry schemas; category reuses ExpenseCategory enum; amount>0 enforced.</done>
</task>
```

### Task 2.1 — hotel_tools (search_hotels + book_hotel confirm guard)

```xml
<task id="2.1" wave="2">
  <files>apps/api/app/tools/hotel_tools.py, apps/api/tests/tools/test_hotel_tools.py, apps/api/tests/tools/test_booking_tools.py</files>
  <action>Add SearchHotelsArgs(city, check_in, check_out: str [req]; rooms, adults, children: int [req]; min_stars: int | None = None [Field ge=1, le=5]; max_price: float | None = None; amenities: list[str] | None = None) and BookHotelArgs(hotel_id, check_in, check_out, guest_name, guest_email, guest_phone: str [req]; rooms: int = 1; adults: int = 2; children: int = 0; notes: str | None = None; confirm: bool = False). Field descriptions from docstrings; note in confirm's description that it must be true to execute the booking. Keep response_format on search_hotels and the confirm/date guards in the bodies untouched. Create test_hotel_tools.py asserting both args_schema set, required vs optional/defaults correct (confirm defaults False), and a valid search invoke still returns (content, artifact).</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_hotel_tools.py -q</verify>
  <done>Both hotel tools carry schemas with correct required/default/confirm semantics.</done>
</task>
```

### Task 2.2 — trip_tools (reuse TripItemKind / TripItemStatus + source Literal)

```xml
<task id="2.2" wave="2">
  <files>apps/api/app/tools/trip_tools.py, apps/api/tests/tools/test_trip_tools.py</files>
  <action>Add GetTripSummaryArgs / GetTripBudgetArgs / ListTripPlacesArgs (each trip_id: str [req]); AddPlaceToTripArgs(trip_id, place_id: str [req]; source: Literal["catalog","saved"] = "catalog"); AddItineraryItemArgs(trip_id: str [req]; day: int [req]; title: str [req]; kind: TripItemKind = TripItemKind.place-default; status: TripItemStatus = pending-default; notes: str | None = None; start_time: str | None = None). Reuse TripItemKind/TripItemStatus enums from the trip schema (verify str,Enum). The add_itinerary_item docstring is stale on kind values — update it to match the enum. Wire all five decorators. Extend the existing tests/tools/test_trip_tools.py with assertions: every trip tool has args_schema; kind/status/source enum values appear in the JSON schema; an invalid kind raises on invoke.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_trip_tools.py -q</verify>
  <done>Five trip tools carry schemas reusing the item enums; stale docstring fixed.</done>
</task>
```

### Task 2.3 — place_tools (source Literal + bounded price_level/min_rating)

```xml
<task id="2.3" wave="2">
  <files>apps/api/app/tools/place_tools.py, apps/api/tests/tools/test_place_tools.py</files>
  <action>Add SearchPlacesArgs(city, category: str | None = None; min_rating: float | None = None [Field ge=0, le=5]; price_level: int | None = None [Field ge=1, le=4]), NearbyPlacesArgs(place_id: str [req]; radius_km: float = 5.0; category: str | None = None), ResolvePlaceArgs(place_id: str [req]; source: Literal["catalog","saved"] = "catalog"), ParseNlQueryArgs(query: str [req]), ListPlaceCategoriesArgs() (empty schema — no fields). Wire all five decorators (list_place_categories takes args_schema=ListPlaceCategoriesArgs even though empty, for consistency). Extend tests/tools/test_place_tools.py: assert every place tool has args_schema; price_level bounds 1..4 enforced; source enum present.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_place_tools.py -q</verify>
  <done>Five place tools carry schemas; price_level/min_rating bounded; source enum'd.</done>
</task>
```

### Task 2.4 — tip_tools (reuse TipCategory)

```xml
<task id="2.4" wave="2">
  <files>apps/api/app/tools/tip_tools.py, apps/api/tests/tools/test_tip_tools.py</files>
  <action>Add GetLocalTipsArgs(city: str | None = None; country: str | None = None; category: TipCategory | None = None; essential_only: bool = False), reusing TipCategory (verify str,Enum; else Literal of its 10 values). Field descriptions; note in the class or field docs that at least one of city/country is required (the body already raises ToolException — do not duplicate as a validator). Wire the decorator. Extend tests/tools/test_tip_tools.py asserting args_schema set, TipCategory values in JSON schema, and the existing city-or-country ToolException still fires.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_tip_tools.py -q</verify>
  <done>get_local_tips carries schema reusing TipCategory; city-or-country guard intact.</done>
</task>
```

### Task 3.1 — routing_tools (async + content_and_artifact)

```xml
<task id="3.1" wave="3">
  <files>apps/api/app/tools/routing_tools.py, apps/api/tests/tools/test_routing_tools.py</files>
  <action>Add GetRouteArgs(origin_place_id: str [req], destination_place_id: str [req]) and GetCityRouteArgs(origin_city: str [req], destination_city: str [req]) with Field descriptions (mention place ids accept PLC-XXXX codes). Wire @tool(args_schema=..., response_format="content_and_artifact") on both async tools. Extend tests/tools/test_routing_tools.py asserting both args_schema set and a valid ainvoke ToolCall still returns (content, artifact) — reuse the async ToolCall ainvoke pattern already in that file.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_routing_tools.py -q</verify>
  <done>Both async routing tools carry schemas; async invoke path still returns artifact.</done>
</task>
```

### Task 3.2 — weather_tools (async)

```xml
<task id="3.2" wave="3">
  <files>apps/api/app/tools/weather_tools.py, apps/api/tests/tools/test_weather_tools.py</files>
  <action>Add GetWeatherArgs(city: str [req]; days: int | None = None), GetPackingArgs(city: str [req]; days: int | None = None), GetAirQualityArgs(city: str [req]). Field descriptions (days = forecast horizon). Wire the three async decorators, preserving response_format on get_weather and get_air_quality. Create test_weather_tools.py asserting each args_schema is set and required/optional shape is correct (schema-only assertions to avoid hitting the live Open-Meteo client; keep <60s).</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_weather_tools.py -q</verify>
  <done>Three weather tools carry schemas; no network hit in tests.</done>
</task>
```

### Task 3.3 — rag_tools (simple)

```xml
<task id="3.3" wave="3">
  <files>apps/api/app/tools/rag_tools.py, apps/api/tests/tools/test_rag_tools.py</files>
  <action>Add SearchDestinationKnowledgeArgs(query: str [req]; city: str | None = None) with Field descriptions. Wire the decorator. Create test_rag_tools.py asserting args_schema is set and query is required / city optional in the JSON schema.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_rag_tools.py -q</verify>
  <done>search_destination_knowledge carries a schema; required/optional correct.</done>
</task>
```

### Task 4.1 — registry guard + full-suite gate

Enforcement task — must run last (needs every tool schema in place).

```xml
<task id="4.1" wave="4">
  <files>apps/api/tests/tools/test_tool_registry.py</files>
  <action>Add a parametrized guard test over app.tools.registry.ALL_TOOLS asserting every tool has a HAND-AUTHORED args_schema — assert `tool.args_schema.__module__.startswith("app.tools")` (LangChain auto-derives a non-None schema from the signature when none is supplied, so `is not None` would pass for un-migrated tools — verified during wave 1). This regression guard blocks future tools shipping without an explicit schema — coordinates with MIN-42. Do not modify registry.py. Then run the full tool suite + ruff as the wave gate.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/tools -q && ruff check app scripts</verify>
  <done>Guard test fails if any ALL_TOOLS entry lacks args_schema; full tools suite green; ruff clean.</done>
</task>
```

## 5. Risks

| Risk | Mitigation |
|---|---|
| **Injected params leak into schema or break injection** (memory_tools) — highest risk. | Task 1.2 is a wave-1 exemplar; assert `user_id`/`store` absent from model schema AND still injected. Prove the pattern before fan-out. |
| **`args_schema` field/param mismatch** → LangChain raises at build time. | Field-parity rule; every verify imports the module (build-time error surfaces immediately). |
| **Reused enum is not `str`-based** → LLM sees ints/opaque members. | Each enum-reuse task verifies `issubclass(X, str)`; fall back to `Literal` of the string values. |
| **content_and_artifact + args_schema interaction** (flight/hotel/routing/weather). | Wave-1 flight exemplar covers it; verify invoke still returns `(content, artifact)`. |
| **weakening-validation commit hook** trips on relocated `raise`/`assert` lines. | We do not move guards, but if it fires, commit with `RISK_WARN_CATEGORIES="weakening-validation"` (per project memory). |
| **`test_booking_tools.py` overlap** (flight+hotel shared it). | Avoided — new dedicated `test_flight_tools.py` / `test_hotel_tools.py`; existing booking test untouched → waves stay file-disjoint. |
| **MCP schema stays loose** (decision A). | Documented gap in SUMMARY; optional follow-up ticket to tighten signatures. |

## 6. Status Log

- 2026-07-01 — Plan drafted from MIN-46 + tool catalog (26 tools / 10 files). Decisions: co-locate schemas · args_schema-only (MCP gap documented) · rely on built-in validation. Status: proposed.
- 2026-07-01 — Branch `feat/min-46-tool-args-schema`; status active (commit `3779c9f`).
- 2026-07-01 — **Wave 1 complete** (flight 1.1, memory 1.2, expense 1.3) — commit `40f1b01`, 14 tests pass, ruff clean. Findings folded back into plan: (a) LangChain always auto-derives a non-None `args_schema`, so Task 4.1 guard now checks `__module__` starts with `app.tools`; (b) domain enums live in `app/enums.py`; (c) memory tools previously produced an un-JSON-able auto-derived schema (`BaseStore`), now fixed by explicit schema.
- 2026-07-01 — **Wave 2 complete** (hotel 2.1, trip 2.2, place 2.3, tip 2.4) — commit `aaac7f7`, 41 tool tests pass. Fix `7f32711`: `min_stars le=5` bound broke a pre-existing hotel no-match test (used `min_stars=6`); swapped to `max_price=1`. One pre-existing trip test updated to expect `ValidationError` (enum now validated by ToolNode).
- 2026-07-01 — **Wave 3 complete** (routing 3.1, weather 3.2, rag 3.3) — commit `0ed312f`. All 26 tools now carry an explicit/described schema.
- 2026-07-01 — **Task 4.1 guard** — commit `f2c3c2d`.
- 2026-07-01 — **Injection regression fixed** — commit `278c0fc`. Wave-1 Risk #1 materialised: an explicit `args_schema` that omits `InjectedState`/`InjectedStore` args breaks ToolNode injection (`recall_past_trips() missing user_id/store`) — caught by `tests/agents/test_planner_episodic`, NOT by the schema-only unit tests. Reverted the 3 memory tools to auto-derived schema + inline `Annotated[..., Field(description=...)]`; guard now exempts injection-bearing tools when every model-facing field is described. Verified **zero regression** vs base `87067c2` (identical 5 pre-existing env failures). Status: shipped.
- 2026-07-01 — shipped via `feat/min-46-tool-args-schema` (PR #49 → `v3`).
