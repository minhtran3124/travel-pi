# gh-200-duplicate-warning-polish — Summary

Lane: normal
Confidence: medium
Reason: no hard gate in items 1–4 (tool + service internals + tests, no route/schema change); 2 flags → normal. Item 5 (soften strict `_as_date` on stored rows) would trip the `weakening-validation` gate, which intake classifies high-risk, so it is scoped OUT by default (see Alternatives). Confidence medium: every item has a safe documented default from the issue, but item 2's marker shape is an implementation choice.
Flags: existing-behavior, weak-proof
Affects: app/services/booking_service.py (book_hotel duplicate block, message + check order), app/tools/_idempotency.py (duplicate_warned_this_turn), app/tools/flight_tools.py + hotel_tools.py (override guard call sites), app/exceptions.py (DUPLICATE_WARNING_MARKER shape if the booking id is embedded), tests/tools/test_booking_duplicate_tools.py, new FakeLLM subgraph test under tests/agents/
Input-type: maintenance
Route: using-git-worktrees (../travel-pi-gh-200, fix/gh-200-duplicate-warning-polish) → xia2 Standard (local-only, no external surface) → writing-plans (4 items, >2 files) → subagent-driven-development. Run BEFORE gh-199 (gh-199 quotes the hotel message this slice corrects; both edit `booking_service.py`).
Escalate: no (item 5 excluded; user may opt it back in, which moves the lane to high-risk)

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

/feature-intake for https://github.com/minhtran3124/travel-pi/issues/200

Issue #200 — "booking: polish the duplicate-intent warning (message accuracy, per-booking override guard, runtime test)", verbatim:

> Follow-up to #194 / PR #197 — start after #197 merges. These are small advisories left open by the #197 review; details are in `specs/gh-194-duplicate-booking-warning/SUMMARY.md` (Advisory Findings).
>
> ## Items
>
> 1. **Hotel warning misdescribes the existing booking (CR-2).** The `DuplicateBookingError` message in `book_hotel` (`app/services/booking_service.py`, hotel `if check_duplicate` block) uses the new request's `rooms`, and its check-in/check-out text, while naming the existing booking. Example: an existing 1-room booking plus a new 3-room request gives "…you already have booking X … (3 room(s))". Build the message from `existing.details` instead.
>
> 2. **Override guard matches on tool name only (CR-5a).** `duplicate_warned_this_turn` (`app/tools/_idempotency.py`) refuses `allow_duplicate=true` whenever any `book_flight` / `book_hotel` duplicate warning from the same tool sits after the latest HumanMessage. This includes a warning about a *different* booking in the same turn. Example: "book flights A and B, B again is fine" → A is warned, then B's override is refused. It fails safe, but the traveller has to repeat themselves. Compare the warned booking (for example, include the existing booking id in the marker) with the current request.
>
> 3. **Tests hand-build the warning ToolMessage (CR-5b).** `tests/tools/test_booking_duplicate_tools.py` constructs the error ToolMessage manually. If the real `ToolNode(handle_tool_errors=_tool_error_to_message)` output format changes (`app/agents/subagents/_base.py`), the guard silently stops working. Add a FakeLLM test through the booking subgraph covering warning → REVISE → `allow_duplicate=true`, asserting that exactly 1 row exists.
>
> 4. **Duplicate check runs before availability (CR-7).** When the hotel is sold out and the traveller already holds an identical booking, the duplicate prompt fires first. The sold-out error only appears after the traveller confirms. Consider running `is_available` first.
>
> 5. **Strict `_as_date` on stored dates (CR-4, low).** The duplicate loop parses stored `details.check_in` / `check_out` with a strict `strptime`. No writer of malformed rows was found, but skipping an unparseable row would be safer than failing the booking.
>
> Lane is likely tiny/normal: tool + service internals only, no contract change.

## What changed

Intake only — no implementation yet. Precondition checked 2026-09-15: PR #197 merged (`ef9aec1`); gh-198 (PR #203) also merged, so `book_hotel`'s duplicate block now runs under the per-owner advisory lock — item 4's reordering must keep `is_available` and the duplicate loop inside the same locked section.

### Rationale

Items 1–4 change wording, guard precision, check order and test depth without touching a route, schema, migration or auth path, so no manifest gate fires; the two flags (existing behaviour changes, and the proof gap item 3 closes) put it in `normal`. Item 5 is the one item that replaces a raise with a skip on stored data; the manifest keeps `weakening-validation` as high-risk at intake even though the diff hook is warn-mode, and the issue itself rates it "low / consider", so it is excluded rather than dragging four small fixes into the high-risk lane.

### Alternatives considered

- Include item 5 (skip unparseable stored rows) — moves the lane to `high-risk` for a defensive read path with no known malformed writer; excluded by default, user may opt in.
- Item 2 alternative: compare the full duplicate-key args (flight number + date + passengers) instead of the existing booking id — heavier marker parsing; default is the issue's suggestion (embed `existing.id` in the marker and compare with the current request's matched booking).
- Split into 4 tiny PRs — more ceremony than one normal-lane plan with 2 waves.

### Deviations

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| intake — hotel duplicate message uses request fields, check runs before `is_available` (item 1 + 4 premise) | `grep -n 'request.rooms} room\|if check_duplicate\|is_available' apps/api/app/services/booking_service.py` | 0 | `if check_duplicate` at 512 precedes `is_available` at 531; message interpolates `request.rooms` | |
| intake — guard keys on tool name only (item 2 premise) | `grep -n 'def duplicate_warned_this_turn' apps/api/app/tools/_idempotency.py` | 0 | signature `(tool_name, messages)`; no booking id | |

### Not auto-verified

- Existing agent tool suite green on main before the branch starts — reached traceability (gh-194 SUMMARY records 350 passed at `4fca57a`); not re-run at intake.

### Rollback

- `git revert <sha>` per commit; no migration involved.

### Harness-Delta

- none
