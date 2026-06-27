# Prompt Changelog

Versions are selected per name in `active.yaml`; old versions are kept for
rollback / A-B. Newest first.

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
