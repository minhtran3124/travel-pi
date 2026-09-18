---
type: concept
title: Agent state, runtime context and reply language
description: The TravelAgentState channels and their reducers, the per-run AgentContext (tier, authentication, reflection and memory toggles, allowed specialists, timezone), how context blocks are folded into one leading system message, trip-facts and current-date grounding, and the single supervisor-detected language that every reply and code-authored system message follows.
tags: [langgraph, state, reducers, agent-context, tier, language, i18n, trip-facts, date-grounding, system-prompt]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-18T04:47:06.927Z
sources:
  - id: openwiki-source-a5f185a5567d6ef95e596338
    resource: repo://apps/api/app/agents/context.py
  - id: openwiki-source-d9abef0ac60d43db26d4721d
    resource: repo://apps/api/app/agents/copy.py
  - id: openwiki-source-aab651981316f0a542a5e4dd
    resource: repo://apps/api/app/agents/state.py
  - id: openwiki-source-6bf7699cddc35845704fa65b
    resource: repo://apps/api/app/agents/supervisor.py
  - id: openwiki-source-04db353a082c76c88c1af099
    resource: repo://apps/api/app/core/languages.py
  - id: openwiki-source-40fb538510ad8b559a8e282e
    resource: repo://apps/api/app/routers/agent.py
  - id: openwiki-source-63555712784df6359cb469ff
    resource: repo://apps/api/tests/agents/test_state_language.py
  - id: openwiki-source-b14f9a68689da71ef2ed0435
    resource: repo://apps/api/tests/agents/test_state.py
  - id: openwiki-source-7650c6fe71fc598b57f298cb
    resource: repo://apps/api/tests/agents/test_system_copy.py
  - id: openwiki-source-21c69d8e7c0f5228bc22afb0
    resource: repo://apps/api/tests/agents/test_tier_gating.py
  - id: openwiki-source-dafb2532f21f93e955ee24a1
    resource: repo://apps/api/tests/agents/test_trip_facts.py
  - id: openwiki-source-a50b62cfcd86c99f1415437e
    resource: repo://apps/api/tests/architecture/test_language_literals.py
generated: { by: "claude-code", at: "2026-09-18T04:47:06.927Z" }
---

# Agent state, runtime context and reply language

Two data structures travel through every graph run. `TravelAgentState` (`apps/api/app/agents/state.py`) is the **checkpointed** working state, serialized after every node and restored on the next turn of the same thread. `AgentContext` (`app/agents/context.py`) is the **per-run, read-only** LangGraph context channel carrying capabilities resolved by the router for this request. Nodes read both; only state is persisted.

## State channels and reducers

`TravelAgentState` extends `MessagesState`, so `messages` uses the `add_messages` reducer (append, or replace in place when a message id repeats, which the PII guardrail relies on). The other channels:

| Channel | Meaning | Reducer |
|---|---|---|
| `user_id`, `trip_id`, `account_email` | Identity for the turn; `trip_id` is the active trip, `account_email` is offered for bookings but never asked for | plain overwrite |
| `current_flow` | The specialist (or `synthesize`) the supervisor routed to; reflection's REVISE target | overwrite |
| `language` | Dominant conversation language code | overwrite |
| `summary` | Rolling summary of compressed older turns | overwrite |
| `revisions` | Reflection counter bounding the revise loop | overwrite |
| `trip_context`, `instructions`, `profile`, `preferences` | Context blocks loaded per turn, injected at model-call time rather than into `messages` | overwrite |
| `plan_approved` | HITL approval signal read by memory extraction | overwrite |
| `trip_facts` | Slot memory for the thread (destination, dates, counts, budget) | `merge_trip_facts` |
| `awaiting_user` | The turn is blocked on the traveller | `last_write_wins` |
| `tasks`, `task_results` | The supervisor's ordered decomposition and the parallel workers' results | `_replace_tasks`, `_append_results` |

Three reducer decisions are load-bearing:

- **`merge_trip_facts` overlays only non-`None` keys.** `None` means "no information this turn", never "delete", so a fact stated three turns ago survives a later turn that says nothing about it. The supervisor therefore emits only resolved slots (see [Agent graph and supervisor routing](graph-and-supervisor.md)). `tests/agents/test_trip_facts.py` pins the overlay, the non-deletion and the survival across turns.
- **`awaiting_user` is last-write-wins, not a sticky `or`.** Parallel synthesis workers may write it simultaneously, and `load_context`'s per-turn `False` reset must actually apply; a sticky reducer would either crash on conflicting writes or make a clarification permanent.
- **`task_results` appends, but an explicit empty list resets**, which is how `load_context` clears the previous turn's results before new workers append; `tasks` is simply replaced per turn.

`trip_id` has **no reducer**, which is why the router omits the key from the turn input when the client sends none: an explicit `None` would clobber a trip selected mid-conversation (see [Conversation memory and persistence](memory-and-persistence.md)).

## The per-run `AgentContext`

`AgentContext` is a frozen dataclass with defaults equal to the pre-context behaviour: `tier` (default free), `authenticated` (default `False`, so a path that forgets to resolve identity is treated as anonymous and cannot create trips), `allow_reflection`, `allow_memory_write`, `allow_episodic`, `response_style`, `allowed_subagents` (`None` means all), `max_revisions` (1) and `timezone` (`None` keeps UTC).

`resolve_agent_context` maps a tier to a context: the **free tier excludes the premium-only specialists** (`booking`) from `allowed_subagents`, premium leaves it `None`. An unknown or missing tier string coerces to the default rather than raising. The agent router resolves the tier server-side from the users table (never from the request body; anonymous callers are always free), reads the reflection toggle from the `reflection` agent-config row, and then replaces `timezone` with the client-supplied IANA zone after validating it, falling back to `AGENT_TIMEZONE` on a missing or invalid value. Consumers: the supervisor's tier gate and follow-on filtering, the reflection node's `allow_reflection`/`max_revisions`, the specialists' episodic-tool filter, the memory extractor's `allow_memory_write`, and every date grounding. `tests/agents/test_tier_gating.py` covers that free booking intents degrade to an upgrade message without tasks while premium booking emits a booking task, and that a free-tier secondary step naming a premium-only agent is dropped.

## One leading system message

Providers that reject multiple or non-consecutive system messages, and the `add_messages` reducer that would append context *after* the human turn, both push the same design: context is carried in state fields and folded into a **single leading `SystemMessage`** at each model call by `system_with_summary`. The order is priority order: profile, signed-in account email, standing instructions, current trip context (with wording that says it is the one open trip, not a list), the conversation summary, known trip facts as bullets (with an instruction not to re-ask for them and to ask only for a missing required field), then preferences. The three memory-derived blocks are wrapped in `<traveller_memory>` tags behind a one-time preamble; see [Guardrails](guardrails-pii-and-hitl.md). With every field empty the base message is returned unchanged, so tests can assert identity.

Specialists then apply, in order, `with_reply_language`, `ground_current_date` and `with_task_note` (see [Specialist sub-agents and the tool registry](specialists-and-tools.md)). The task note is folded into the same system message rather than appended as a second one, and is skipped when the task query equals the last user message, so a single-intent turn adds nothing and the cached prefix holds. The date note is appended **last** because it changes daily and the cacheable prefix must not shift per request.

## Current-date grounding

`ground_current_date` computes today's date per request in the context timezone (invalid zones fall back to UTC and say so in the note) because the graph is built once and would otherwise serve a date frozen at boot. The note establishes the only correct value of "today", forbids passing a tool an earlier date, routes relative or partial dates to the `resolve_date` tool instead of in-model arithmetic, forbids re-confirming a date that tool already returned, and requires asking when the traveller gave no date but a date-bound tool (flight or hotel search, booking, dated trip creation) is about to be called. An undated day-by-day itinerary suggestion is explicitly exempt and is answered as Day 1, Day 2, Day 3. `tests/agents/test_state.py` pins the timezone handling, the last-block position, and both halves of the ask rule. The supervisor grounds the date outermost for the same caching reason.

## One language, detected once

The supervisor's structured output returns `language`, the traveller's dominant conversation language, seeded with the already-established value so a lone interjection does not flip it; an explicit request to reply in a language wins immediately and stays sticky. The supervisor writes it to `state["language"]` **before** any terminal branch, so even a code-authored reply on an unknown-intent or tier-gated turn is served in this turn's language (`tests/agents/test_supervisor_language.py`).

From there, `with_reply_language` pins every model reply to that code, including tool results, trip data and place names, which never change it. This deterministic guard matters most on the clarification path, which ends the turn before reflection can catch a language slip. The synthesize node, side-panel localization and follow-up suggestion keys read the same field, so there is exactly one detection per turn.

Supported codes live in `app/core/languages.py` (`en`, `vi`, default `en`, `normalize()` for unknown input); an architecture test forbids inline `"en"`/`"vi"` literals in the agent modules, and the tuple is parity-tested against the frontend's locale list (see [Internationalization and theming](../frontend/i18n-and-theming.md)).

**Code-authored replies** (`unknown_intent`, `booking_upgrade`, `booking_cancelled`, `agent_error_fallback`) go through `system_reply(key, language)` in `app/agents/copy.py`: English sources are the only stored variants, the target-language text is produced once by the shared LLM translator with a persona note (the assistant refers to itself as "Tin", not "I") and cached in the content-translation store under a key that includes a digest of the source, so editing a constant invalidates its cached translations. Any failure serves English rather than raising. `tests/agents/test_system_copy.py` covers the cache-once and failure-fallback behaviour.
