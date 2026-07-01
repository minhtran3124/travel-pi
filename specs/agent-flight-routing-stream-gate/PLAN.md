---
slug: agent-flight-routing-stream-gate
status: proposed
owner: Minh Tran
created: 2026-07-01
---

# Flight-search routing + silent-stream gate fix

Fixes an empty chat bubble on `"tìm chuyến bay từ Đà Nẵng ra Hà Nội…"` for
anonymous (free) users. Root cause in `SUMMARY.md`. Two independent BE fixes.

## 1. Motivation

1. Supervisor misroutes flight **search** → `booking` (premium-only) → free user
   tier-gated to `END`.
2. The tier-gate's `BOOKING_UPGRADE_MSG` (a supervisor-node message) is never
   streamed, because `stream_agent_events` only emits tokens for SUBAGENT nodes →
   blank bubble.

## 2. Non-goals

- No tier-policy change (`booking` stays premium; flight *search* stays free via planner).
- No SSE taxonomy change (reuse the existing `token` event).
- No FE change.

## 3. Success criteria

- A free user asking to **search** flights routes to `planner` and gets results.
- Any turn that legitimately ends at the supervisor (tier-gate / unknown intent)
  or `plan_node` (cancelled/approved) streams its message — never a blank bubble.
- Full suite green.

## 4. Tasks

### Task 1.1 — Stream terminal supervisor/plan messages

```xml
<task id="1.1" wave="1">
  <files>apps/api/app/streaming/mapper.py, apps/api/tests/api/agent/test_stream_events.py</files>
  <action>In stream_agent_events, the `updates` branch currently surfaces only tool_calls and ToolMessages. Add: for the cross-cutting terminal nodes {"supervisor", "plan"} (main graph, not in SUBAGENTS), surface a content-bearing AIMessage with no tool_calls as an `events.token(content)` and set emitted_token=True. Gate on the update's node-name key (iterate data.items()) so sub-agent content — which already streams via `messages` mode — is never double-emitted. Define a module constant e.g. `_TERMINAL_TEXT_NODES = frozenset({"supervisor", "plan"})`. Add a test feeding a scripted astream `((), "updates", {"supervisor": {"messages": [AIMessage(BOOKING_UPGRADE_MSG)]}})` and assert a `token` event carrying BOOKING_UPGRADE_MSG is emitted before `done`.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_stream_events.py -q</verify>
  <done>Gated/unknown-intent/plan-cancel turns emit a token; no duplicate tokens for sub-agent replies; stream tests pass.</done>
</task>
```

### Task 1.2 — Sharpen supervisor routing (search → planner)

```xml
<task id="1.2" wave="1">
  <files>apps/api/app/prompts/supervisor/v4.md, apps/api/app/prompts/active.yaml</files>
  <action>Create supervisor/v4.md from v3, tightening the planner/booking boundary: route any flight/hotel *search or find* ("tìm chuyến bay", "find/search flights", "look for a hotel") to `planner` (it owns search_flights/search_hotels and is free-tier). Reserve `booking` for explicit reserve/confirm/book/quote intent only. Update the planner bullet to say "finding/searching + choosing flights/hotels" and add routing examples: `"tìm chuyến bay từ Đà Nẵng ra Hà Nội sáng mai" → planner (flight search)` and `"Book/confirm the 7am flight" → booking`. Bump active.yaml `supervisor: 4`. Prompt-only + config; no code.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_supervisor.py -q && ../../.venv/bin/python -c "import yaml,pathlib; a=yaml.safe_load(pathlib.Path('app/prompts/active.yaml').read_text()); assert a['supervisor']==4; from app.prompts.registry import registry; t=registry.get('supervisor').lower(); assert 'search' in t and 'planner' in t"</verify>
  <done>active supervisor version is 4, v4 loads via registry and routes flight search to planner; supervisor node tests still pass.</done>
</task>
```

## 5. Risks

- **Routing is LLM-driven** — FakeLLM unit tests script the intent, so they can't
  prove the prompt fix. Real proof is the manual re-test in §Status Log (phase-level
  UAT), not a `<verify>` row. Keep both fixes so a residual misroute still shows the
  upgrade message instead of a blank.
- **Double-emit regression** — if the node-name gate is too broad it could re-emit
  sub-agent text. Mitigated by restricting to `{"supervisor", "plan"}` and the
  1.1 test.

## 6. Status Log

- 2026-07-01 — Plan drafted. Both tasks wave 1 (disjoint files, parallel).
  Manual UAT after execution: rerun `"tìm chuyến bay từ Đà Nẵng ra Hà Nội vào
  sáng mai cho tôi"` as an anonymous user in FAST mode → expect flight results (not
  a blank bubble); and an explicit `"đặt vé…"` → expect the streamed upgrade message.
