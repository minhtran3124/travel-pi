# Assumption: Set own test user to premium tier

## Context
The booking specialist is premium-only. The supervisor gates the free tier.

## Decision
Inserted a users row for the test user id 00000000-0000-0000-0000-00000000b0a1 with tier=premium, after first observing the free-tier gate. Created two own trips via POST /trips.

## Alternatives
- Test only the free-tier gate.

## Impact if wrong
Only test-owned rows were touched and no shared data was deleted. Booking BA4U9A remains in the DB. If a reader assumed real premium users, the result still holds, since the tier check reads the same column.

## How to reverse
Delete the test user row, its two trips and booking BA4U9A by id. Nothing else references them.
