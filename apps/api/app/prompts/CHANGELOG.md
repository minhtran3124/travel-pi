# Prompt Changelog

Versions are selected per name in `active.yaml`; old versions are kept for
rollback / A-B. Newest first.

## gh-155-supervisor-booking-follow-on — booking is never a follow-on; legacy secondary_agent retired

- **supervisor v11** — copied v10; removed the "legacy `secondary_agent` field still works" bullet
  and added a bullet under "Multi-step Plan": a booking wish inside a multi-intent message is
  never a follow-on — route `target_agent=booking` when reserving is the main ask, otherwise leave
  the booking out of `plan` entirely.
- **code half** (Task 1.2) — the `secondary_agent` field and its fallback are removed.

`active.yaml`: supervisor → 11.

## agent-tool-round-budget — skip the no-op trip_guard step; planner batches itinerary writes

specs/agent-tool-round-budget: a single agent turn has a bounded number of tool-call rounds,
so a step that adds nothing to the plan and a planner that writes one itinerary item per turn
both burn rounds a full itinerary needs.

- **planner v12** — copied v11, then added one sentence under "How to Work" step 4: when
  several itinerary items are ready at once (e.g. filling out multiple days), call
  `add_itinerary_item` more than once in the same response instead of one item per turn, so a
  full itinerary does not exhaust the turn's tool-call budget. No existing v11 line was removed.
- **`_base.py`** (code half) — `trip_guard` no longer routes to itself when the trip is already
  known; the router goes straight to `tools`, skipping the no-op guard step.

`active.yaml`: planner → 12.

## agent-budget-trip-context — budget agent reads the trip and sets caps

specs/agent-budget-trip-context: "pls set simple budget for trip" made the **budget** agent
ask "how many days is your trip?" — it was bound to `EXPENSE_TOOLS + get_trip_budget` only,
could not read the trip's dates/travelers, and no agent tool set a budget, so the model
improvised per-day arithmetic (breaking its own "Don't estimate totals" guardrail). The
code half binds `get_trip_summary` into the budget domain and adds two tools:
`estimate_trip_budget` (read-only; derives `nights` from the trip's dates, returns
`suggested_caps` per category + `assumptions`, or `{"error": "trip_dates_unknown"}` when
the trip has no dates) and `set_trip_budget` (write; REPLACES all four caps
flights/hotels/activities/buffer).

- **budget v3** — copied v2, then extended "## How to Work": call `get_trip_summary`
  first (dates, travelers, existing caps); for "set / plan a (simple) budget" call
  `estimate_trip_budget` (pass `nights` only if the traveller stated it), present the
  `suggested_caps` with the `assumptions` and ask to confirm or adjust; call
  `set_trip_budget` only after explicit confirmation and say it replaces all caps; ask
  "how many nights / what dates" ONLY on `trip_dates_unknown`. One guardrail added:
  "Never compute per-day or total figures yourself — the estimate tool does it." No v2
  content was removed.
- **supervisor v10** — copied v9; the **budget** bullet now also covers "setting /
  estimating the trip's budget caps" (previously planner v11's "budget caps" wording could
  attract the request), plus one routing example: "Set a simple budget for my trip" →
  **budget**. No other edits.

`active.yaml`: budget → 3, supervisor → 10. Others unchanged.

## multi-intent-single-path — `plan` is independent-parallel-only; single-specialist chains stay single (wave 1)

specs/multi-intent-single-path (decision A): the runtime is parallel-only — `route_tasks`
`Send`s every `len(tasks)>1` to blind `synthesis_worker`s that each see only the last user
message and cannot read a sibling's result. But `SupervisorIntent.plan` still told the model
to plan ordered/dependent/recurring follow-ons, so "plan my weekend: flights, weather, then
itinerary" spawned a blind itinerary worker plus a duplicate planner. Wave 1 fixes the
supervisor side (wave 2 removes the dead sequential `dispatch_next`/`pending_flows` machinery).

- **supervisor v9** — copied v8, then added one routing rule under rule 3 (and one example):
  a CHAIN whose steps all live inside ONE specialist's toolset routes to that single
  specialist with `plan=[]` — the **planner** owns flights (`search_flights`), hotels
  (`search_hotels`), places (`search_places`), weather (`get_weather`), routing, `create_trip`,
  `add_itinerary_item` — so "plan my weekend: flights + hotel + places + weather + itinerary"
  is one planner job, not a fan-out. `plan` is now only for genuinely INDEPENDENT extras a
  single specialist cannot do itself (local tips / travel knowledge → concierge). The
  "## Multi-step Plan" section was reframed from ordered/recurring follow-ons to
  independent-parallel-only; no existing v8 content was removed.
- **supervisor.py** (code half) — the `plan`/`secondary_agent` field descriptions now read
  "independent, parallel, sees only this message, never the primary, never booking"; the task
  list is built from a DEDUPLICATED agent list (primary first, follow-ons in order, skipping any
  agent already queued — no duplicate specialist workers), keeping the `MAX_LEDGER_STEPS` cap;
  and the supervisor **stops writing `pending_flows`** in its Command update (the state field
  stays for wave 2). No graph topology or SSE change.

`active.yaml`: supervisor → 9. Others unchanged.

## booking-tools-owner — agent bookings carry the injected owner (review-A E004)

specs/review-a-security-hardening (E004): `book_flight`, `book_hotel`, `cancel_flight`
and `cancel_hotel` now take `user_id` via `InjectedState("user_id")` (graph state, never
model-supplied) and pass it to the owner-scoped `BookingService`, so agent-made bookings
are stamped with the authenticated traveller and a cancel of a booking owned by someone
else reads as *not found* (#118). No prompt version changed.

- **MCP caveat:** E004 assumed these tools would drop off MCP because injected-arg tools
  are skipped. They are **not** — `app/mcp/server.py` skips only `store` / `tool_call_id`,
  not `InjectedState` (`get_trip_summary` is likewise exposed). The four tools remain on
  the MCP surface (now with a `user_id` param); enforcing E004's removal needs an explicit
  server-side filter. See `.harness-state/sdd/report-3.1.md`.

## supervisor-expense-logging — disambiguate "log an expense" from journal

GH-117 Path A eval: `gpt-4o-mini` routed "Log that I paid 50 USD for lunch today"
to **journal** because of the word "log", even though the content is an expense.
Added an explicit routing example so expense recording always goes to **budget**,
regardless of "log"/"note" wording.

- **supervisor v8** — identical to v7 plus one new few-shot example:
  "Log that I paid 50 USD for lunch today" → **budget** (recording an expense).

`active.yaml`: supervisor → 8.

## ledger-early-exit — signal "blocked on the traveller" instead of draining the plan

specs/min-68-ledger-early-exit (MIN-68 / #99): when a queued multi-step plan hits a
specialist that needs a clarifying answer, the remaining steps used to run anyway and
produce output the traveller never sees. Sub-agents now carry a `needs_clarification`
tool (control-flow, not registry/MCP-exposed) that sets `awaiting_user`, making
`dispatch_next` abandon the rest of the ledger; the next turn re-plans.

- **communication_style v7** — appended a `## Blocked on the Traveller` section telling
  every specialist to call `needs_clarification` once when only the traveller can
  unblock them, and never for tool failures. Everything else unchanged from v6.

`active.yaml`: communication_style → 7. Others unchanged.

## flight-fare-no-fabrication — forbid derived prices, not just invented ones

specs/flight-fare-no-fabrication (MIN-67 / #98): the agent searched one leg and told the
traveller "from $136 round-trip total" by doubling a real $68 one-way fare — grounded in a
tool result, so the prior "never invent" wording didn't catch it. `search_flights` gained an
optional `return_date` (wave 1) so a round trip's real return-leg fare can actually be
retrieved; this is the prompt half.

- **planner v11** — extended the existing "Never invent flights, hotels, or prices"
  Guardrails bullet in place (not a new bullet) to also ban derivation: a stated price must
  be one a tool returned, never computed, doubled, summed, or extrapolated from one; search
  the return leg with `return_date` to price a round trip. Everything else unchanged.

`active.yaml`: planner → 11. Others unchanged.

## weather-trip-date-accuracy — climate vs forecast, and matching the tool's dates to the trip

specs/weather-trip-date-accuracy (MIN-66 / #97): `get_weather`/`get_packing` gained an optional
`date` and now refuse a date beyond the ~2-week forecast horizon instead of silently returning
today's forecast; a new `get_climate` tool exposes monthly normals for dates further out. The
prompt half of the fix teaches the model when to use which and to check the covered-dates line
the weather summary now states, so a trip-date mismatch (the reported bug: a Sep trip answered
with the Jul forecast) is visible instead of silently wrong.

- **concierge v11** — added a third `## Grounding` bullet: check `get_weather`/`get_packing`'s
  stated covered dates against the traveller's dates; call `get_climate` for a date beyond the
  horizon and describe it as typical/average conditions, never a forecast. Extended the
  `## Example — weather` block with a Don't/Do pair showing a climate-normals reply framed
  correctly. Everything else (grounding order, shortlist rule, hotels, visa & local advice) is
  unchanged.
- **planner v10** — added one Guardrails bullet: a weather-fit itinerary must check
  `get_weather`/`get_packing`'s covered dates against the trip's actual dates, and use
  `get_climate` (never as a forecast) for a date beyond the horizon. Planner had no prior
  weather mention; this is additive, no restructuring.

`active.yaml`: concierge → 11, planner → 10. Others unchanged.

## agent-date-resolution Phase 5 — new `date_resolution` prompt (LLM parses, code computes)

specs/agent-date-resolution §4b: the hardcoded weekday/phrase word tables in
`app/core/dates.py` are a treadmill — patching one missed phrase at a time
never converges, and only ever covers the languages we thought to hardcode.
Replaced with a new `date_resolution` prompt family: a small, fast model
reads the traveller's date wording and returns a **structured intent**
(`kind` + kind-specific fields) — never a computed date. All date arithmetic
stays in code (`app/core/dates.py`, wired in a follow-up task), so a misread
phrase is visible and testable in the trace, and a wrong `+7` (the earlier
P0) becomes impossible because the model never does arithmetic at all.

- **date_resolution v1** — new prompt. Covers every intent kind (`absolute`,
  `relative_day`, `weekday`, `week_start`, `weekend`, `offset`, `ambiguous`)
  with few-shot `input -> intent` examples spanning Vietnamese (with and
  without diacritics), English, Japanese, and Spanish. Pins the conventions
  the model maps onto — bare weekday = next occurrence strictly after today;
  "this <weekday>" = current calendar week; "next <weekday>" = next calendar
  week — and is explicit that `ambiguous` is the safe answer for "no date at
  all" or genuinely multiple readings, not for merely unusual phrasing
  ("tuần tới" is ordinary, not ambiguous — the old lexicon's failure mode).

`active.yaml`: date_resolution → 1 (new). Added to `FAST_AGENTS`
(`app/agents/constants.py`) so it resolves to the cheap model, and to
`AGENT_CONFIG_NODES` / `AGENT_DESCRIPTIONS` (`app/data/agent_config.py`) so
it is configurable from the dashboard like every other node. Others
unchanged.

## agent-date-resolution (follow-up) — planner missed by the date rewrite

Code review on `feat/agent-date-resolution` found that the `booking v6` date
rewrite below was never applied to `planner` — and planner is the dominant
path for flight/hotel *searches* (the supervisor routes most searches there,
and `resolve_date` is bound to planner). Planner v6 still told the model to
"resolve relative dates … to a concrete date yourself" and to "get a single
yes/no confirmation before you search", directly contradicting the CURRENT
DATE note (`app/agents/state.py::ground_current_date`) prepended to every
sub-agent prompt.

- **planner v7** — copied v6, then applied the same date rewrite as
  `booking v6` to the two date guardrail bullets: any non-ISO date (relative,
  weekday, partial) MUST go through the `resolve_date` tool — never computed
  in the model's head — and the agent searches/proposes immediately, stating
  the resolved date in its answer instead of asking for a yes/no confirmation
  first. A date question is now asked only when the traveller gave no date
  signal at all or `resolve_date` reports the expression is ambiguous.
  Everything else is untouched: "Never invent flights, hotels, or prices",
  the required-hotel-detail guardrail (rooms/guests/party-size must come from
  the traveller, never defaulted), and the multi-turn stitching behavior
  ("combine details the traveller gave across several turns", don't re-ask
  for something already provided).

`active.yaml`: planner → 7. Others unchanged.

## agent-date-resolution — stop confirming a date before searching

specs/agent-date-resolution: deterministic date resolution (`app/core/dates.py`)
plus a new `resolve_date` agent tool made the LLM's own date arithmetic and the
pre-search "please confirm this date" turn redundant — the agent now resolves
and states the date instead of asking the traveller to pre-approve it.

- **booking v6** — copied v5, then rewrote the date-confirmation part of
  "## How to Work" step 1: any non-ISO date (relative, weekday, partial) must
  go through the `resolve_date` tool — never computed in the model's head —
  and the agent searches/quotes immediately, stating the resolved date in its
  answer instead of asking for a yes/no confirmation first. A date question is
  now asked only when the traveller gave no date signal at all or `resolve_date`
  reports the expression is ambiguous. The non-date "restate + confirm" flow
  (rooms, guests, party size) is unchanged. Booking-approval language —
  "Never confirm a booking without explicit approval. Quoting is safe; booking
  is not." and "Confirm the resolved value once before booking." — is
  untouched: this only removes the pre-*search*/pre-*quote* date confirmation,
  not the pre-*booking* approval gate.

`active.yaml`: booking → 6. Others unchanged.

## travel-knowledge-rag — concierge knowledge-search tool

specs/travel-knowledge-rag: re-introduce RAG over visa + local-tips seed content,
exposed to the concierge as a new `search_travel_knowledge` tool. The concierge
calls it for free-text visa/entry and local-advice questions and grounds on its
results (guidance, not a ruling); falls back to `get_local_tips` for practical
tips when it returns `count: 0` (there is no visa-specific tool).

- **concierge v9** — copied v8, then added a new "## Visa & local advice"
  section (between Hotels and the weather Example) instructing the model to call
  `search_travel_knowledge` for free-text visa/local-advice questions, present
  results as guidance (nationality-dependent, confirm with the official
  authority), and fall back to `get_local_tips` when retrieval is empty.
  Existing sections (grounding, shortlist, personalize, hotels, exclude_names)
  are unchanged, so `test_concierge_prompt_mentions_exclude_names_on_followup`
  still holds.

`active.yaml`: concierge → 9. Others unchanged.

## v-min-54 — chat formatting polish (emoji + tighter bold)

MIN-54: make replies friendlier and cleaner to scan. Prompt half of the issue
(the web spacing/line-height half lives in `apps/web`).

- **communication_style v5** — copied v4, then two edits under "## How to Format":
  (a) sharpened the bold rule so **only the specific value** is bold (a name, number,
  price, date, place), never a whole sentence or a generic word; (b) added a new
  "### Emoji" subsection — tasteful, contextual travel emoji (🏨 ✈️ 🌴 💰 📅 …) used
  sparingly, at the start of a line/term, never on every bullet, and skipped entirely
  in warnings / disclaimers / tool-failure replies. "## Identity" (name **Tin**) is
  unchanged, so `test_tin_identity` still holds across all five sub-agents.

`active.yaml`: communication_style → 5. Others unchanged.

## v-min-60 — chatbot branding (name: Tin)

MIN-60: give the assistant a name so it can refer to itself in first person
instead of sounding like an anonymous tool.

- **communication_style v4** — added an "## Identity" section: the assistant's
  name is **Tin** (Trợ lý Tìm–Đi–Nghỉ); use it by name once or twice per reply
  when natural, otherwise "mình"; never call itself a generic "trợ lý ảo".
  Prepended to every sub-agent prompt via `_base.py`, so all five sub-agents
  (planner/concierge/journal/booking/budget) pick it up automatically.

`active.yaml`: communication_style → 4. Others unchanged.

## v-min-60-followup — language stickiness + name-capture guard

Two bugs found in a real English conversation (conv `2239214e`): the bot flipped
to Vietnamese on a trip-action turn, and the memory extractor stored the bot's own
name ("Tin") as the traveller's name.

- **communication_style v4** (edited in place, unshipped) — rewrote "## Language":
  reply language is now **sticky** and set by the traveller's most recent *typed*
  message. Tool results, trip data, and Vietnamese place names (Đà Nẵng, Hà Nội)
  no longer switch the language; a too-short message ("look good") keeps the
  language already in use. Fixes the flip-to-Vietnamese on the planner/tool turn.
- **memory_extraction v4** — added a guard: capture `name` only from the
  traveller's own words in a *user* message; **never** capture the assistant's
  name. "Tin" (the assistant's name, any language) is not the traveller's name.

`active.yaml`: memory_extraction → 4. communication_style stays 4 (in-place edit).

## v-min-53 — proactive personalization (name / gender / travel-group)

MIN-53: agent softly, optionally learns who the traveller is and who they travel
with, to personalize address and suggestions. Stored in the existing prefs store
under reserved keys (`name`, `gender`, `travel_group`) — no schema. Injected each
turn via `TravelAgentState.profile` (`app/agents/nodes.py` load_context_node).

- **memory_extraction v3** — capture the three reserved personalization keys when
  the traveller volunteers them; never infer gender/name/group.
- **concierge v8 / planner v5** — added "Personalize before suggesting": one light,
  optional, skippable question about trip company before giving recommendations,
  plus an optional gentle **name** ask for warmer address; never block on either;
  **never ask for gender directly** (gender used only if the traveller volunteers
  it). The gender narrowing was confirmed with the requester on PII grounds.

`active.yaml`: concierge → 8, planner → 5, memory_extraction → 3. Others unchanged.

## v5 — concierge: default to a shortlist

Dumping the full search-results list (e.g. every café in a city) by default was
overwhelming and buried the actually-useful picks; a Vietnamese-language test
conversation surfaced this alongside a separate reflection-loop bug where the
revision prompt (an English `HumanMessage`) got read as "the traveller's latest
message" and silently flipped the reply language mid-turn (fixed in
`app/agents/nodes.py`, not a prompt change).

- **concierge v5** — when the traveller doesn't ask for a specific count or
  "all", present only the top 4–5 (highest-rated first) and offer to show more,
  instead of presenting every returned item.

`active.yaml`: concierge → 5. Others unchanged.

## v4 — hotel-search detail gathering

Stop the agent from silently guessing hotel-search details. Paired with the
`search_hotels` tool making `rooms`, `adults`, and `children` required (no
defaults), so an omitted value can no longer be assumed as 2 adults / 1 room.

- **planner v4** — added a guardrail: collect check-in/check-out, rooms, and
  guests (adults + children) before searching hotels; never guess or use a
  default party size; restate any value that only appeared earlier (with the
  implied nights) and ask the traveller to confirm.
- **booking v4** — expanded the "How to Work" step 1 to enumerate the required
  hotel details (dates, rooms, adults, children) and added a guardrail against
  guessing dates/party size/room count.

`active.yaml`: planner, booking → 4. Others unchanged.

## v3 — apply mizumi-ai patterns (P1 + P2)

Reviewed the mizumi-ai hotel-concierge prompt set and adapted its transferable
patterns (review: `specs/travel-agent/PROMPT_REVIEW.md`). Channel/tone-specific
bits (WhatsApp no-markdown, Forbes-luxury vocabulary, guest-name personalization)
were deliberately **not** adopted — travel-pi is web-markdown and casual-warm.

- **communication_style v3** — promoted language handling to a dedicated, high-priority
  `## Language` section with ✅/❌ examples (was a single buried bullet).
- **supervisor v3** — added a `## Routing Examples` few-shot block to disambiguate the
  commonly-confused cases (journal vs booking, concierge vs planner).
- **concierge v3** — added an explicit `## Grounding (in order)` hierarchy
  (retrieved facts → live tools → say-you-don't-know) and a tool-result fidelity rule
  (present all returned items, keep order, don't shorten).
- **booking v3** — added a `## How to Work` flow: verify required details before quoting,
  one-tool-at-a-time, confirm only after explicit approval.

`active.yaml`: communication_style, supervisor, concierge, booking → 3.
planner, journal, budget stay at 2; reflection at 1.

## v2 — structure pass

Rewrote all seven registry prompts into a consistent structure
(`# Role` / `## Responsibilities` / `## How to Work` / `## Guardrails`); deduped
`concierge` against the shared `communication_style`; merged redundant
option/bold bullets in `communication_style`. No behavioural rule dropped.

## v1 — initial prompts

Original prose prompts shipped with the travel-agent foundation
(`specs/travel-agent`). `reflection` was added at v1 when its critic prompt was
moved out of `nodes.py` into the registry.
