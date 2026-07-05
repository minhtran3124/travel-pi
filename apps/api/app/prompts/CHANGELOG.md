# Prompt Changelog

Versions are selected per name in `active.yaml`; old versions are kept for
rollback / A-B. Newest first.

## v-min-53 — proactive personalization (name / gender / travel-group)

MIN-53: agent softly, optionally learns who the traveller is and who they travel
with, to personalize address and suggestions. Stored in the existing prefs store
under reserved keys (`name`, `gender`, `travel_group`) — no schema. Injected each
turn via `TravelAgentState.profile` (`app/agents/nodes.py` load_context_node).

- **memory_extraction v3** — capture the three reserved personalization keys when
  the traveller volunteers them; never infer gender/name/group.
- **concierge v8 / planner v5** — added "Personalize before suggesting": one light,
  optional, skippable question about trip company before giving recommendations;
  never block on it; never ask for gender directly.

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
