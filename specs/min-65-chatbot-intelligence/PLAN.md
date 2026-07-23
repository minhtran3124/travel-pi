---
slug: min-65-chatbot-intelligence
status: proposed
owner: Minh Tran
created: 2026-07-12
ticket: MIN-65
---

# MIN-65 — Chatbot Intelligence: Memory, Reasoning & Suggestion Quality

## 1. Motivation

See `HLD.md` §1 — the ticket's 3 pillars; the long-term memory foundation is already
shipped, this plan patches exactly the gaps: entity/slot tracking, wider preference
injection, multi-intent routing, a suggestion rule engine + preference re-rank, and
eval-first so the improvement is measurable (ticket AC).

## 2. Non-goals

Per `HLD.md` §6: not adopting Mem0/LangMem/Letta; no LLM free-text suggestions; not
upgrading the reflection rubric (MIN-59); booking never becomes a secondary intent; no
memory for anonymous users; no change to the public `/agent/*` contract.

## 3. Success Criteria

- The user doesn't have to repeat information already given within the same conversation
  (eval `memory_recall` improves vs baseline).
- Preferences are remembered across a new session (the `new_thread_at` case passes).
- ≥80% of replies carry a relevant suggestion (the deterministic layer of
  `suggestion_relevance`).
- Routing eval (`routing.json`) doesn't regress after the supervisor schema grows.
- `make test` green (SQLite) + `make test-docker` green (Postgres parity) at the end.

## 4. Tasks

> Wave = HLD phase: W1-2 = P0 eval-first · W3-5 = P1 memory + P2 reasoning · W6 = P3 suggestions · W7-8 = prompt pass + measurement.
> Every verify runs from the repo root unless noted otherwise; `PY=.venv/bin/python`, BE tests run inside `apps/api/`.

### Task 1.1 — Multi-turn eval harness + new datasets

```xml
<task id="1.1" wave="1">
  <files>apps/api/eval/harness.py, apps/api/eval/loader.py, apps/api/eval/datasets/memory.json, apps/api/eval/datasets/suggestions.json, apps/api/tests/eval/test_harness_multiturn.py</files>
  <action>Extend run_case to support the case shape {"turns": [...], "new_thread_at": int|null} (DESIGN D9): turns share one thread_id on the compiled graph; new_thread_at opens a new thread_id with the same user_id (cross-session, same store); actual_output = the last reply; fully back-compatible with the plain "input" case shape. After the final invoke, call suggestions_for_flow on the final state and attach the result to the test case (a field/metadata for metric 1.2 — currently the old flow-only signature, wave 6 will make it richer). Write eval/datasets/memory.json (≥8 cases: recall of dates/party-size/destination within a thread; ≥2 cross-session preference cases via new_thread_at) and suggestions.json (≥8 cases covering the flows), register both in loader.load_all() with the new shape's validation. Test with the existing FakeLLM graph fixture pattern from tests/agents: a shared thread keeps state, new_thread_at splits the thread while keeping the same user.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_harness_multiturn.py -x -q</verify>
  <done>run_case runs both single and multi-turn/cross-session cases; the 2 new datasets load + validate; tests pass without touching a real LLM</done>
</task>
```

### Task 1.2 — Metrics `memory_recall` + `suggestion_relevance`

```xml
<task id="1.2" wave="1">
  <files>apps/api/eval/metrics_geval.py, apps/api/eval/run_deepeval.py, apps/api/tests/eval/test_metrics_registry.py</files>
  <action>Add a memory_recall GEval factory (rubric per DESIGN D9: reuse facts already given, don't re-ask; asking about a genuinely new field is fine) and suggestion_relevance (GEval over the suggestion keys' EN labels vs context) to GEVAL_METRICS; add a deterministic layer for suggestion_relevance in run_deepeval (suggestions non-empty + key in the catalog — measures the ≥80% AC). Wire the per-case rubric filter through LLMTestCase.metadata as in the MIN-58 calibration. Gotcha in deepeval 4.0.7: the judge-key check is eager — the registry test must run with OPENAI_API_KEY=dummy and never actually execute a metric.</action>
  <verify>cd apps/api && OPENAI_API_KEY=dummy DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/eval/test_metrics_registry.py -x -q</verify>
  <done>2 new metrics registered + filter correctly by metadata; the deterministic layer computes the has-a-suggestion rate; tests pass without needing a real key</done>
</task>
```

### Task 2.1 — Baseline before any behavior changes

```xml
<task id="2.1" wave="2">
  <files>specs/min-65-chatbot-intelligence/BASELINE.md</files>
  <action>Run the new eval against the current code to get a comparison baseline: per project memory (eval-harness-bypasses-db-config-and-context) — run INSIDE the api container, configure agent_config + reload_from_db first, needs a real OPENAI_API_KEY judge. Write BASELINE.md: a score table for memory_recall / suggestion_relevance (+ current routing), the exact command used, the run date. Expect memory_recall to score low (no trip_facts yet) — that's the improvement baseline. If no key is available: write a documented-skip + the command for the user to run, NEVER a silent pass.</action>
  <verify>test -s specs/min-65-chatbot-intelligence/BASELINE.md</verify>
  <done>BASELINE.md has real scores or a documented-skip with the re-run command</done>
</task>
```

### Task 3.1 — State foundation: `trip_facts`, `preferences`, `pending_flows`

```xml
<task id="3.1" wave="3">
  <files>apps/api/app/agents/state.py, apps/api/tests/agents/test_trip_facts.py</files>
  <action>Add to TravelAgentState: trip_facts (Annotated[dict, merge_trip_facts] — reducer per DESIGN D1: a non-None value overwrites, never deletes), preferences: str, pending_flows: list[str]. system_with_summary folds in 2 more blocks in the exact order and wording from DESIGN D1/D2 ("Known trip facts — do NOT ask again…", "Traveller preferences…"); every field empty → returns base unchanged (keeps current behavior for new users). Do not change the call sites (supervisor/_base go through the same function). Test: reducer merge across branches; fold has the right content/order; empty → identity.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_trip_facts.py -x -q</verify>
  <done>3 new fields + reducer + injection block work; the full existing agents test suite stays green (run tests/agents -q if unsure)</done>
</task>
```

### Task 4.1 — Supervisor: slot extraction + secondary intent (prompt v6)

```xml
<task id="4.1" wave="4">
  <files>apps/api/app/agents/supervisor.py, apps/api/app/prompts/supervisor/v6.md, apps/api/app/prompts/active.yaml, apps/api/tests/agents/test_supervisor_slots.py</files>
  <action>Extend SupervisorIntent per DESIGN D3: ExtractedSlots (raw verbatim, all-optional) + secondary_agent (a Literal without booking) + slots. After the LLM call, normalize in code: dates via core.dates.resolve_travel_date with today(ctx.timezone) — on failure, DROP (never guess); a duration needs a start_date; int-cast adults/children/rooms; a simple budget regex; destination/origin stay raw. Extend the Command update with trip_facts=normalized and pending_flows=[secondary] (drop the secondary when the target is booking or duplicates the target). Create a NEW prompts/supervisor/v6.md (copy v5 + the verbatim-or-null slot rule + the secondary rule) and flip active.yaml supervisor: 6 — do NOT edit v5 (critical pattern supervisor-active-yaml-is-a-pointer). Test with FakeLLM: slots resolve/drop correctly, a valid secondary → pending_flows, booking → secondary dropped, old routing unchanged when slots are null.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_supervisor_slots.py -x -q</verify>
  <done>The supervisor's 1 LLM call returns routing + slots; the pure-code normalization has tests; active.yaml points at v6</done>
</task>
```

### Task 4.2 — Preference auto-injection at `load_context`

```xml
<task id="4.2" wave="4">
  <files>apps/api/app/agents/nodes.py, apps/api/tests/agents/test_preferences_injection.py</files>
  <action>load_context_node also reads search_preferences(store, user_id, limit=8) (recency full-read, not a semantic query — DESIGN D2), EXCLUDES PROFILE_KEYS (already has its own profile block), formats the "Traveller preferences…" block → state["preferences"]. Best-effort like profile: store miss / no user_id / error → "". Test: prefs in the store → correct block content, profile keys excluded, empty store → "", a store error doesn't raise.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_preferences_injection.py -x -q</verify>
  <done>Every sub-agent sees preferences via the system message every turn; behavior is unchanged for new users</done>
</task>
```

### Task 5.1 — Multi-intent dispatch node + graph rewire

```xml
<task id="5.1" wave="5">
  <files>apps/api/app/agents/graph.py, apps/api/app/agents/nodes.py, apps/api/tests/agents/test_multi_intent_routing.py</files>
  <action>Add the dispatch_next node (DESIGN D4, pure code, no LLM): pending_flows non-empty → Command(update={current_flow: next, pending_flows: rest}, goto=next); empty → goto reflection. Rewire all 5 sub-agents' static edges: sub-agent → dispatch_next (instead of → reflection). The plan/HITL branch keeps its existing topology. Test with a FakeLLM graph: (a) 2 intents run in order before reflection, the second sub-agent sees the first one's messages; (b) a single intent → straight to reflection (old behavior); (c) reflection's REVISE loop-back through dispatch_next doesn't infinite-loop (queue already empty).</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_multi_intent_routing.py -x -q</verify>
  <done>Multi-intent queries are handled sequentially in one turn, up to 2 sub-agents; single-intent and revise behavior are unchanged</done>
</task>
```

### Task 5.2 — Store hygiene: `updated_at` + canonical keys (extraction v5)

```xml
<task id="5.2" wave="5">
  <files>apps/api/app/memory/store.py, apps/api/app/prompts/memory_extraction/v5.md, apps/api/app/prompts/active.yaml, apps/api/tests/memory/test_store_timestamps.py</files>
  <action>upsert_preference/upsert_instruction/upsert_episode also write updated_at (UTC ISO — use datetime.now(timezone.utc), not utcnow()) into the value dict; back-compat reads for old values missing the field; do NOT change the index config (text stays the embedded field). Create prompts/memory_extraction/v5.md (copy v4 + the canonical-key vocabulary from DESIGN D5 + the reuse-key-on-update rule), flip active.yaml memory_extraction: 5. Test: upsert writes a timestamp, get/search read both old and new records; extend the extractor test with a FakeLLM returning a canonical key.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/memory/test_store_timestamps.py tests/memory/test_extractor.py -x -q</verify>
  <done>Values carry updated_at, back-compat holds; prompt v5 active; key-drift reduced via the canonical vocabulary</done>
</task>
```

### Task 6.1 — Suggestion rule engine + FE i18n keys

```xml
<task id="6.1" wave="6">
  <files>apps/api/app/agents/suggestions.py, apps/api/app/routers/agent.py, apps/api/app/streaming/mapper.py, apps/web/messages/en.json, apps/web/messages/vi.json, apps/api/tests/agents/test_suggestions_engine.py</files>
  <action>Replace the static _FLOW_SUGGESTIONS with the DESIGN D6 rule engine: signature suggestions_for_flow(current_flow, *, trip_facts=None, profile=None, preferences="") returning a list of keys, MAX 3, an ordered specific→generic rule table, final fallback is the current static map (never fewer suggestions than today). Add ~8 catalog keys (book_hotel_next, transport_to_hotel, activities_near_destination, weather_before_trip, packing_tips, family_activities, budget_check, local_tips_destination) + a Chat.followups.<key>.{label,prompt} entry in BOTH en.json and vi.json (FE resolves dynamically, no component change). Non-stream: routers/agent.py passes the final state. Streaming: get trip_facts/profile at drain time via the same sink mechanism as run_memory_extraction_from_stream; if the done-event build point can't reach the final state → fall back to flow-only (safely degrades to MIN-55). Keep suppressing when an interrupt is pending. Test: each rule, the fallback, MAX 3, key always in the catalog.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_suggestions_engine.py -x -q && node -e "const en=require('/Users/minhtran/Documents/minhtran3124/developer/travel-pi/apps/web/messages/en.json'),vi=require('/Users/minhtran/Documents/minhtran3124/developer/travel-pi/apps/web/messages/vi.json');for(const k of ['book_hotel_next','transport_to_hotel','activities_near_destination','weather_before_trip','packing_tips','family_activities','budget_check','local_tips_destination']){if(!en.Chat.followups[k]||!vi.Chat.followups[k])throw new Error(k)};console.log('i18n ok')"</verify>
  <done>Suggestions are state-aware + personalized by profile/prefs; both locales have all keys; the ChatResponse.suggestions contract is unchanged</done>
</task>
```

### Task 6.2 — Preference-aware re-rank in hotel/flight tools

```xml
<task id="6.2" wave="6">
  <files>apps/api/app/tools/_ranking.py, apps/api/app/tools/hotel_tools.py, apps/api/app/tools/flight_tools.py, apps/api/tests/tools/test_preference_ranking.py</files>
  <action>Create tools/_ranking.py: rank_by_preference(items, preferences, ...) -> (ranked, reasons) — a deterministic keyword matcher (fold diacritics via core/text), a STABLE, boost-only sort (never filters any item out) per DESIGN D7: hotel (star/area/type), flight (airline, morning/evening time-of-day via departure hour). Wire into search_hotels/browse_hotels/search_flights: receive preferences via Annotated[str, InjectedState("preferences")] — inline Annotated, ABSOLUTELY do not use @tool(args_schema=) (the explicit-args-schema-breaks-langgraph-injection gotcha); re-rank before building the summary + panel_result; on a match → append "Prioritized based on your preferences: <reasons>" to the summary. Test: correct boost, stable, empty prefs → unchanged order, the injected arg never leaks into the model schema, determinism holds for the same input+prefs.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_preference_ranking.py -x -q</verify>
  <done>Hotel/flight results are ordered by learned preference, the panel + summary stay consistent, deterministic</done>
</task>
```

### Task 7.1 — Prompt quality pass (reasons, intent inference, ask-only-missing)

```xml
<task id="7.1" wave="7">
  <files>apps/api/app/prompts/communication_style/v6.md, apps/api/app/prompts/concierge/v10.md, apps/api/app/prompts/planner/v8.md, apps/api/app/prompts/booking/v7.md, apps/api/app/prompts/active.yaml</files>
  <action>One task, one voice (DESIGN D8): communication_style v6 — every recommendation carries a one-line reason tied to the traveller's facts/preferences, list-answers end with the single most relevant next step; concierge v10 — proactive intent inference (peak season/weather/events), ask-only-missing checked against Known trip facts; planner v8 — ask-only-missing + default-with-confirm for fields the tool signature doesn't require; booking v7 — ask-only-missing, tool args remain a hard gate. All of these: create a NEW file + flip active.yaml, never edit the old version. Language care: do not hardcode a Vietnamese tagline/content into the prompt (the MIN-60 language-mixing gotcha).</action>
  <verify>cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -c "from app.prompts.registry import registry; assert 'reason' in registry.get('communication_style').lower(); [registry.get(n) for n in ('supervisor','concierge','planner','booking','memory_extraction')]; print('prompts ok')"</verify>
  <done>4 new prompt versions active, the registry loads cleanly; the quality guardrail covers all 5 reply paths</done>
</task>
```

### Task 8.1 — Measurement: re-run eval vs baseline + RESULTS

```xml
<task id="8.1" wave="8">
  <files>specs/min-65-chatbot-intelligence/RESULTS.md</files>
  <action>Re-run the full eval (memory, suggestions, routing, and the old MIN-58 datasets) under the same conditions as 2.1 (in the container, real key); write RESULTS.md: a delta table vs BASELINE.md per metric, AC met/not-met (memory_recall improved, suggestion ≥80%, routing not regressed), a short analysis of any failing case. Run the full make test (SQLite) and make test-docker (Postgres parity — remember the docker-py312 gotcha + a stale travel.db after a schema-less change still needs a fresh mktemp DB). No key → documented-skip as in 2.1.</action>
  <verify>test -s specs/min-65-chatbot-intelligence/RESULTS.md && cd apps/api && ../../.venv/bin/python -m pytest tests/agents tests/memory -q</verify>
  <done>RESULTS.md has a real delta vs baseline; the agents+memory suite is green; every ticket AC is explicitly assessed</done>
</task>
```

## 5. Risks

Details in `DESIGN.md` §Risks. Summary: routing degradation from a larger supervisor
schema (mitigation: optional fields + routing eval); a slot normalization date error
(reuse `core/dates`, drop-on-fail); the streaming path can't obtain the final state for
suggestions (flow-only fallback); a crude keyword ranker (boost-only, never filters); the
`risk-corroboration` hook false-positiving on the word `session`/removing an assert
during test refactors (use `RISK_WARN_CATEGORIES` correctly when blocked). New prompts →
dev needs a graph rebuild (`docker exec api-api-1 touch app/main.py`) for manual
verification.

## 6. Status Log

- 2026-07-12 — Plan drafted (HLD.md + DESIGN.md + PLAN.md). Not yet executed.
