# First outside user group and success metric (proposal)

Status: PROPOSAL for the owner. The final choice is the owner's. Market research has NOT been done;
this page contains no market statistics and no competitor claims.

## What the repo tells us (facts only)

- The web app is bilingual: `apps/web/messages/en.json` and `apps/web/messages/vi.json` both exist.
- Stage 1 is single-user. The nav has a "Sign in" entry (`Account.signIn`), but there is no
  multi-user or sharing surface (see `docs/PRODUCT.md` surfaces list).
- Flights and hotel availability are synthetic, generated from seed data; FX is a static snapshot
  (`AGENTS.md`). Nobody can book real inventory.
- Trips, expenses, bookings, journals and the AI chat co-pilot are real, persisted features
  (`docs/PRODUCT.md`, `AGENTS.md`).
- `docs/PRODUCT.md` describes the user as one traveler planning a trip on desktop or mobile web.

## Proposed target group (assumption A1)

Vietnamese-speaking and English-speaking friends-and-family travelers, about 5 to 10 people the
owner knows personally, each planning one real upcoming trip.

Why this group, from repo facts only: the UI already works in both languages, the inventory is
synthetic so the group must value planning and tracking over booking, and a small known group
fits a single-user stage.

## What users do instead today (not researched)

Not researched. This page does not know what the proposed group uses today to plan a trip
(for example notes apps, spreadsheets, chat threads, other planning apps, or a travel agent), and
it names no competitor or substitute because that would be invented. Until the owner or a short
round of interviews answers this, treat the value of the app against current alternatives as unknown.

## Question to answer

Will a person who is not the builder use the app to plan a real trip, and come back to it?

## Proposed success metric (assumption A2)

Per invited user: they create a trip and add at least one itinerary item, expense or saved place,
and they return on a second day within 14 days of their first session.

Group target (threshold to be set by the owner, not by this page): the share of invitees who meet
the per-user rule. Suggested read: the metric measures retention of planning behaviour, not
bookings, because bookings are synthetic.

## Assumptions

- A1: friends-and-family can give honest feedback.
- A2: "return on a second day" is a usable proxy for value.
- A3: invitees have a real trip coming up within the test window.
- A4: the group's current alternatives are unknown and unresearched; nothing here assumes the app beats them.

## Open questions for the owner

1. Is the first group friends-and-family, or a stranger group (for example a Vietnamese
   travel community)? This needs real research that has not been done.
2. What threshold counts as success for the group?
3. Does the test need accounts for each user, given stage 1 is single-user?
4. Which events can already be measured today, and which need new tracking?
5. Is synthetic inventory acceptable to outside users, or must it be labelled in the UI?
6. What do the invitees use today instead of this app (current alternatives or substitutes)? Not
   researched; see "What users do instead today".
