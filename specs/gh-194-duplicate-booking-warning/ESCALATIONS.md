# gh-194-duplicate-booking-warning — Escalations

Default: **deny-on-no-response**. No recorded decision → work stays blocked.
(Enforced: `hooks/commit-quality-gate.sh` denies commits touching this slug while any `decision:` is `pending`.)

---

## E001

- raised_by: orchestrator (feature-intake)
- date: 2026-09-14
- trigger: hard-gate
- question: Should the duplicate guard live in BookingService (changing the REST POST /flights/book + /hotels/book contract) or only in the agent book_* tools?
- context: brainstorming/planning are blocked; the choice decides whether the REST API, the web booking pages, and FE error handling change.
- options:
  - A) Service-level (issue proposal): REST returns a new 409 `possible_duplicate` (overridable by an `allow_duplicate` body field), tools relay it; FE `/flights` + `/hotels` pages must handle it. Covers all paths; public-contract change.
  - B) Tool-level only: the check runs in `flight_tools.book_flight` / `hotel_tools.book_hotel` before the service call; REST unchanged. Smaller blast radius; web pages can still double-book.
  - C) Service method with an opt-in flag (`check_duplicate=True` passed only by the tools): shared logic, REST behaviour unchanged for now, REST adoption becomes a later slice.
- default_if_no_response: BLOCK
- decision: C — service method with opt-in check_duplicate flag, passed only by the agent tools; REST unchanged
- decided_by: Minh Tran (user)
- decided_at: 2026-09-14

## E002

- raised_by: orchestrator (feature-intake)
- date: 2026-09-14
- trigger: ambiguous-direction
- question: What counts as "the same" booking, and which statuses count?
- context: defines the duplicate query and the tests.
- options:
  - A) Proposed default: flight = same user + same `reference_id` (flight row is date-specific) + same `passengers`; hotel = same user + same hotel + same check_in/check_out (ignoring rooms/guests); only non-cancelled statuses count.
  - B) Looser: same user + same flight/hotel + same dates, ignoring passenger/room counts (warns on any overlap, e.g. booking 1 more seat).
  - C) Hotel overlap: any overlapping date range at the same hotel counts (not just exact dates).
- default_if_no_response: BLOCK
- decision: A — proposed default (flight: user+reference_id+passengers; hotel: user+hotel+exact check_in/check_out; cancelled excluded)
- decided_by: Minh Tran (user)
- decided_at: 2026-09-14

## E003

- raised_by: orchestrator (feature-intake)
- date: 2026-09-14
- trigger: ambiguous-direction
- question: How is the warning surfaced — tool-result text only, or also in the HITL booking plan draft?
- context: decides whether the HITL/plan path (graph state) is touched in addition to the tools + SYSTEM_COPY.
- options:
  - A) Tool result only: the tool returns a structured "possible duplicate" message (English source, localized through the reply-language path) and the model asks; an `allow_duplicate=True` retry proceeds. Minimal.
  - B) A + shown in the HITL plan draft before the traveller approves (extra state plumbing, earlier warning).
- default_if_no_response: BLOCK
- decision: A — tool result only; model asks, allow_duplicate=True retry proceeds
- decided_by: Minh Tran (user)
- decided_at: 2026-09-14
