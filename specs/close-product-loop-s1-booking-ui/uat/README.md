# Browser UAT — S1 booking slice

Run 2026-09-08 against `feat/close-product-loop-s1-booking-ui`, with the Next dev server on `:3001`
and the API on `:8000` (Docker, dev Postgres). Driven by [`run-uat.mjs`](run-uat.mjs) —
playwright-core under Node 24, because the Playwright MCP server is broken in this environment.

```bash
export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH"
cd apps/web && node ../../specs/close-product-loop-s1-booking-ui/uat/run-uat.mjs
```

The product shape under test: `/flights` and `/hotels` are **browse-only**, and every booking goes
through the chatbot, which stamps the active trip onto the booking.

| # | Case | Result |
|---|---|---|
| 1 | Flights and Hotels reachable from the app nav | Both present |
| 2 | `/flights` searches and shows results, with **no** booking control | 0 Book buttons; assistant hint shown |
| 3 | `/hotels` the same | 0 Book buttons; assistant hint shown |
| 4 | Asking the assistant to book, from the trip's own page | Request accepted, plan proposed |
| 5 | The assistant asks before spending money | Approval gate shown |
| 6 | After approving | **Blocked — see below** |
| 7 | The trip's Bookings tab | Empty, because nothing was booked |
| 8 | The trip's Budget tab | Booked total $0, for the same reason |

### 1 — Flights and Hotels in the nav

![Flights and Hotels in the app nav](01-nav-flights-hotels.png)

### 2 — `/flights` is browse-only

![Flight results with no Book control](02-flights-browse-only.png)

### 3 — `/hotels` is browse-only

![Hotel results with no Book control](03-hotels-browse-only.png)

### 4 — Asking the assistant to book

![The booking request sent to the assistant](04-chat-booking-asked.png)

### 5 — The assistant asks first

![The approval gate before booking](05-chat-booking-approval-gate.png)

### 6 — After approval, the booking does not happen

![The assistant asks for a valid email it can never receive](06-chat-booking-done.png)

### 7 and 8 — The trip stays empty

![Bookings tab, empty](07-trip-bookings-after-chat.png)

![Budget tab, booked total zero](08-trip-budget-after-chat.png)

## The blocker this UAT found

**Booking through the chatbot cannot currently complete, for any user.**

The assistant searched, proposed the cheapest fare, asked for approval, and then stopped with:

> I can confirm the booking as soon as you send a valid email address for UAT Tester. The airline
> needs a real email with an @ sign.

The email *was* supplied — `uat-<stamp>@example.com`. The approval card shows what the assistant
actually received: `email [REDACTED_EMAIL]`.

Three facts meet here, and only the third is new:

1. `pii_guardrail_node` (`apps/api/app/agents/guardrails.py:98-112`) is the graph's entry node and
   replaces **every** email in the user's message with `[REDACTED_EMAIL]` before any model call.
2. `passenger_email` and `guest_email` are **required** on the booking tools
   (`flight_tools.py:297`, `hotel_tools.py:158`), and nothing in `TravelAgentState` carries the
   account's email — state has `user_id` and a `profile` string of name/gender/travel-group
   (`agents/state.py:83,93`).
3. The web pages no longer book, so chat is the only path left.

Points 1 and 2 predate this branch and have always been in tension; point 3 is what turns that
tension into a dead end. Nothing on this branch caused it, and nothing on this branch can be blamed
for it, but the branch's stated direction does not work until it is resolved.

The obvious fix is to supply the email the same way `user_id` and `trip_id` are supplied: injected
server-side from the account, never model-supplied and therefore never redacted. That is a product
decision about using someone's account email as the booking contact, so it is written down here
rather than made unilaterally.

## What was verified instead

That the trip actually gets stamped onto a chat booking is covered at the tool level by
`apps/api/tests/tools/test_booking_trip_id.py`, which invokes both booking tools the way the graph
does — with and without a trip in state — and asserts the stamped `trip_id`. The browser cannot
demonstrate it end to end until the email blocker above is resolved.

## Environment notes

- The chat booking case needs a premium account; the booking sub-agent is premium-only. The UAT
  account was temporarily set to premium with `scripts/set_tier.py` and **set back to free
  afterwards** — the dev database is shared, so it was left as found.
- An earlier run of this UAT found the dev Postgres had never had the migration applied: every
  booking failed with a generic message while the API log said `column bookings.trip_id does not
  exist`. **The migration has to run on deploy.** No test on this branch could have caught it —
  both the SQLite and Docker Postgres suites build their schema from the migrations against a fresh
  database, so only a long-lived one can lag.
