---
slug: min-51-hotel-search-intent
status: proposed
owner: Minh Tran
created: 2026-07-04
linear: MIN-51
---

# MIN-51 — Hotel search shouldn't force the booking flow

## 1. Motivation

A pure hotel-info query ("khách sạn ở Đà Nẵng giá dưới 1tr") is classified as a
booking intent and routed to the `booking` sub-agent, which always passes through
the HITL plan-approval interrupt (`supervisor.py:82`) and demands booking details.
Per confirmed **Approach A** (`SUMMARY.md`), the non-destructive `search_hotels`
tool moves to the retrieval agent (`concierge`) so hotel *info/search* is answered
directly with a gentle "muốn đặt phòng không?" soft prompt, while the destructive
`book_hotel` stays on `booking` and only an explicit booking intent triggers the
HITL flow. This matches the existing architecture (concierge = retrieval,
booking = transactions).

## 2. Non-goals

- Approach B (moving the plan-approval interrupt to tool-level HITL). Not chosen.
- Stripping `search_hotels` from `booking` (booking keeps it — its quote-then-book
  flow in `prompts/booking/v4.md` needs `search_hotels` to quote and resolve a
  `hotel_id`) or from `planner`. Only concierge *gains* the tool.
- Changing the `book_hotel` `confirm=True` guard, DB schema, or any HTTP/router
  contract (`routers/hotels.py`, `services/*` untouched).
- Building a real-LLM routing eval harness (residual — see Risks).

## 3. Success Criteria

- `get_tools_for("concierge")` includes `search_hotels`; still excludes `book_hotel`.
- `get_tools_for("booking")` still includes `book_hotel`.
- Graph run with supervisor intent `concierge` completes with **no** `__interrupt__`.
- Graph run with supervisor intent `booking` still pauses with a `plan_approval`
  `__interrupt__`.
- The concierge subgraph can invoke `search_hotels` and surface a
  `kind="hotels"` side-panel artifact.
- Active prompts become `supervisor: 5`, `concierge: 7`; concierge prompt contains
  the soft booking prompt and a "concierge does not book" guardrail; supervisor
  prompt routes hotel-info→concierge vs explicit-booking→booking with the ticket's
  two example phrases.
- Free tier: hotel search via concierge works; an explicit book still returns
  `BOOKING_UPGRADE_MSG` (unchanged tier-gate path, `supervisor.py:75`).
- `tests/agents/` and `tests/tools/test_tool_registry.py` are green.

## 4. Tasks

### Task 1.1 — Split hotel tools and rebind concierge

```xml
<task id="1.1" wave="1">
  <files>app/tools/hotel_tools.py, app/tools/registry.py</files>
  <action>In hotel_tools.py add HOTEL_SEARCH_TOOLS = [search_hotels] and HOTEL_BOOKING_TOOLS = [book_hotel] just above the existing HOTEL_TOOLS; redefine HOTEL_TOOLS = HOTEL_SEARCH_TOOLS + HOTEL_BOOKING_TOOLS (keeps ALL_TOOLS/TOOL_METADATA and planner/booking bindings unchanged). In registry.py import HOTEL_SEARCH_TOOLS and change the concierge entry to PLACE_TOOLS + WEATHER_TOOLS + ROUTING_TOOLS + TIP_TOOLS + HOTEL_SEARCH_TOOLS. Leave booking = FLIGHT_TOOLS + HOTEL_TOOLS and planner unchanged. Rationale: concierge gains non-destructive search only; destructive book_hotel stays off concierge.</action>
  <verify>cd apps/api && ../../.venv/bin/python -c "from app.tools.registry import get_tools_for as g; c={t.name for t in g('concierge')}; b={t.name for t in g('booking')}; assert 'search_hotels' in c and 'book_hotel' not in c; assert 'book_hotel' in b; print('ok')"</verify>
  <done>concierge tool group has search_hotels and not book_hotel; booking still has book_hotel; import clean.</done>
</task>
```

### Task 2.1 — Supervisor + concierge prompt edits (new versions, activate)

```xml
<task id="2.1" wave="2">
  <files>app/prompts/supervisor/v5.md, app/prompts/concierge/v7.md, app/prompts/active.yaml</files>
  <action>Copy supervisor/v4.md → v5.md. Edit the "Routing Rules"/"Routing Examples" so a PURE hotel info/search lookup (price, location, amenities, reviews, "hotels in X under N", no add-to-trip and no explicit book) routes to concierge; hotel search that builds/edits an itinerary ("find a hotel and add it to my trip") stays planner; explicit reserve/confirm/book/quote stays booking. Add examples: "khách sạn ở Đà Nẵng giá dưới 1tr" → concierge; "tôi muốn đặt phòng khách sạn X" → booking. Copy concierge/v6.md → v7.md; add a "Hotels" section: concierge may call search_hotels to answer hotel info/price/availability questions (apply the top 4–5 shortlist rule + Hotels panel), MUST first collect check-in/check-out, rooms, adults and children (mirror booking/v4 step 1) and never guess dates; concierge does NOT book — after presenting hotels, gently offer to help book ("Muốn mình hỗ trợ đặt phòng luôn không?" / "Want me to help you book one?") and note booking happens via the booking flow; never fabricate hotels. In active.yaml set supervisor: 5 and concierge: 7.</action>
  <verify>cd apps/api && ../../.venv/bin/python -c "from app.prompts.registry import registry as r; s=r.get('supervisor'); c=r.get('concierge'); assert 'concierge' in s and 'Đà Nẵng' in s; assert 'search_hotels' in c and 'đặt phòng' in c.lower(); print('ok')"</verify>
  <done>v5.md/v7.md exist, are the active versions, and carry the new routing rule + soft-prompt/no-book guidance.</done>
</task>
```

### Task 3.1 — Tool-registry unit assertions for the split

```xml
<task id="3.1" wave="3">
  <files>tests/tools/test_tool_registry.py</files>
  <action>Add test_hotel_tool_split: assert 'search_hotels' in the concierge group and 'book_hotel' not in it; assert 'book_hotel' in the booking group; assert search_hotels still present in ALL_TOOLS and TOOL_METADATA['search_hotels']['destructive'] is False. Pure in-memory; no DB/LLM.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_tool_registry.py -q</verify>
  <done>New split assertions pass; existing registry tests still green.</done>
</task>
```

### Task 3.2 — Graph + subgraph intent/behavior tests

```xml
<task id="3.2" wave="3">
  <files>tests/agents/test_hotel_search_intent.py</files>
  <action>New FakeLLM-only file. (a) Mirror test_hitl_plan.py _build/_invoke: intent_target="concierge" → assert result has no __interrupt__ and current_flow=="concierge". (b) intent_target="booking" → assert result["__interrupt__"] payload type=="plan_approval". (c) Mirror test_concierge_dedup.py using the agent_db fixture: build_subagent("concierge_hotel_test", get_tools_for("concierge"), lambda _: fake, registry.get("concierge")) where fake is FakeLLM(responses=[AIMessage(content="", tool_calls=[{"name":"search_hotels","args":{"city":"Da Nang","check_in":<today+7>,"check_out":<today+9>,"rooms":1,"adults":2,"children":0},"id":"h1"}]), "Here are some hotels — muốn đặt phòng không?"]); invoke and assert a ToolMessage from search_hotels exists and its .artifact["kind"]=="hotels". Compute dates dynamically from datetime.now(timezone.utc) so the future-date guard passes. Use FakeLLM only — no real LLM/embeddings, so the .env OPENAI_API_KEY 403 does not apply.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_hotel_search_intent.py -q</verify>
  <done>Concierge hotel-search path does not interrupt, booking path interrupts, and concierge surfaces a hotels artifact.</done>
</task>
```

## 5. Risks

- **Premium-gate interaction (intended):** concierge is not in `PREMIUM_ONLY_SUBAGENTS`,
  so hotel *search* becomes free-tier — this is the desired outcome. Booking stays
  premium; the supervisor tier gate (`supervisor.py:75`, `BOOKING_UPGRADE_MSG`) only
  checks the resolved `target`, so a free user routed to `concierge` searches fine
  and a free user routed to `booking` still gets the upgrade message. No supervisor
  code change; `test_tier_gating.py` continues to cover this.
- **Prompt change is non-deterministic (residual, cannot fully close):** the supervisor
  routing decision that sends "khách sạn…" to concierge is produced by the LLM from
  the v5 prompt. FakeLLM `structured_responses` bypass the prompt, so no <60s
  deterministic test proves the real router honors the new rule. Mitigation: manual /
  real-LLM acceptance check recorded in the Status Log before shipping.
- **search_hotels artifact/panel from concierge:** `search_hotels` returns
  `content_and_artifact`; the panel is built by `panel_result` inside the tool
  (flow-agnostic), so the artifact should surface identically from concierge. Task 3.2(c)
  asserts `artifact["kind"]=="hotels"` to catch any per-flow panel-mapping gap.
- **Booking keeps search_hotels (deviation from literal "move"):** removing it would
  break booking's quote-then-book prompt flow and hotel_id resolution. Documented
  decision; concierge only *gains* the tool.

## 6. Status Log

- 2026-07-04 — Plan drafted (proposed). Approach A locked in SUMMARY.md.
- _TODO on execute_ — W1 rebind, W2 prompts v5/v7, W3 tests green.
- _TODO on execute_ — Manual real-LLM acceptance: verify "khách sạn ở Đà Nẵng giá
  dưới 1tr" → concierge (no interrupt) and "tôi muốn đặt phòng khách sạn X" →
  booking (interrupt). Run broad suite with `apps/api/.env` moved aside.
