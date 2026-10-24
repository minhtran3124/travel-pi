# Assumption: Flight search routes to planner, not booking

## Context
The task said the booking specialist should search, then book.

## Decision
Treated flight search going to the planner, and the booking specialist handling book-after-approval, as the intended split. Booking also re-searches with search_flights when the draft lacks details.

## Alternatives
- Flag the routing as a bug.

## Impact if wrong
No effect on pass or fail. If the product wants booking to own search, the supervisor routing and the tool groups need a change.

## How to reverse
Nothing to undo. This only affects how the result is read. Revisit the supervisor intent rules if the split is wrong.
