# First outside user group and success metric (proposal)

Status: PROPOSAL for the owner. The final choice is the owner's. Market research has NOT been done;
this page contains no market statistics and no competitor claims.

## What the repo tells us (facts only)

- The web app is bilingual: `apps/web/messages/en.json` and `apps/web/messages/vi.json` both exist.
- Accounts already exist. The web app has `apps/web/src/app/auth/{login,sign-up,callback,confirm}`,
  and the API stores `user_id` on users, trips, bookings, conversations, saved places, agent runs
  and feedback events. There is no sharing between users. Stage 1 deploys the app for the owner
  only (sign-ups off), so outside users need that restriction lifted for the test (#351).
- Flights and hotel availability are synthetic, generated from seed data; FX is a static snapshot
  (`AGENTS.md`). Nobody can book real inventory.
- Trips, expenses, bookings, journals and the AI chat co-pilot are real, persisted features
  (`docs/PRODUCT.md`, `AGENTS.md`).
- `docs/PRODUCT.md` describes the user as one traveler planning a trip on desktop or mobile web.

## Proposed target group (assumption A1)

Vietnamese-speaking and English-speaking friends-and-family travelers, about 5 to 10 people the
owner knows personally, each planning one real upcoming trip.

Why this group, from repo facts only: the UI already works in both languages, the inventory is
synthetic so the test can only measure planning and tracking, not booking, and a small known
group is the cheapest first test.

Known weakness: friends and family tend to use an app out of politeness, so their return rate
can reflect goodwill, not value. The owner may add 2 or 3 invitees who are not close friends, or
choose a stranger group (open question 1).

## What users do instead today (not researched)

Not researched. This page does not know what the proposed group uses today to plan a trip
(for example notes apps, spreadsheets, chat threads, other planning apps, or a travel agent), and
it names no competitor or substitute because that would be invented. Until the owner or a short
round of interviews answers this, treat the value of the app against current alternatives as unknown.

## Question to answer

Will a person who is not the builder use the app to plan a real trip, and come back to it?

## Proposed success metric (assumption A2)

Per invited user, a user passes when both hold:

1. They created at least one trip (a row in `trips` with their `user_id`).
2. They used the app on at least two distinct calendar days (UTC), within 14 days of their first
   session, where "used" means at least one agent run (a row in `agent_runs` with their `user_id`).

Saved places and expenses are not counted: saving a place takes almost no effort and would inflate
the pass rate. "Calendar day" is the UTC date of `agent_runs.created_at`, so two people measuring
the same invitee get the same answer.

Group target (threshold to be set by the owner, not by this page): the share of invitees who
pass. This measures return use of planning, not bookings, because bookings are synthetic.

## Where the metric data comes from

- Trips: `trips` rows carry `user_id` and `created_at`.
- Active days: `agent_runs` rows carry `user_id` and `created_at` (the dashboard already lists
  them), so distinct days per user can be counted with a query. No new tracking is needed for the
  metric above.
- Written feedback: `feedback_event` rows carry `user_id`.
- Related tickets: #345 adds `instance_id` to `agent_runs`; #350 adds a cost-per-turn report.
- Not checked: whether a visit without a chat turn should count. This page counts chat turns only,
  because no page-view tracking was found in `apps/web/src` or `apps/api/app` (not exhaustively searched).

## Assumptions

- A1: friends-and-family can give honest feedback.
- A2: using the app on a second day after creating a trip is a usable proxy for value.
- A3: invitees have a real trip coming up within the test window.
- A4: the group's current alternatives are unknown and unresearched; nothing here assumes the app beats them.

## Open questions for the owner

1. Is the first group friends-and-family, or a stranger group (for example a Vietnamese
   travel community)? This needs real research that has not been done.
2. What threshold counts as success for the group?
3. Accounts exist already. Should the test stay invite-only (sign-ups off, testers added by invitation, #351)?
4. Is counting chat turns as "used the app" acceptable, or should page visits be tracked too?
5. Is synthetic inventory acceptable to outside users? The UI now labels flight and hotel results as simulated data (#342), so this is about whether that label is enough.
6. What do the invitees use today instead of this app (current alternatives or substitutes)? Not
   researched; see "What users do instead today".
