# Assumption: Idempotency key from item identity

## Context
Duplicate parallel add_itinerary_item calls created duplicate rows.

## Decision
Key is a sha256 over trip, day, kind, lower-cased title and start_time, passed to the existing idempotency_key support in TripService.add_item.

## Alternatives
A semantic-duplicate check in TripService, which would also change REST behaviour; or a prompt-only fix.

## Impact if wrong
A traveller who deliberately adds the same title at the same time on the same day twice gets the original row back. REST behaviour is unchanged. If wrong, legitimate repeats are silently merged.

## How to reverse
Stop passing the key from the tool. Rows already created keep their stored key and are harmless.
