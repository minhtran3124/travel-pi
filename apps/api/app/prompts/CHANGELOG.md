# Prompt Changelog

Versions are selected per name in `active.yaml`; old versions are kept for
rollback / A-B. Newest first.

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
