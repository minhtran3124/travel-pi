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

The agent's duplicate-booking warning is now accurate and precise. The hotel warning quotes the existing booking's dates, rooms and party instead of the new request's. A sold-out hotel reports sold-out before any duplicate prompt. The warning marker carries the existing booking's id, so a same-turn `allow_duplicate=true` is refused only for the booking that was actually warned; a warning about a different booking no longer blocks it, and a legacy or malformed marker still refuses every override. A FakeLLM graph test drives warning → REVISE → refusal → new turn → booking through the real ToolNode. Item 5 (softening strict `_as_date`) was left out as scoped at intake. No route, schema or migration changed.

### Rationale

Items 1–4 change wording, guard precision, check order and test depth without touching a route, schema, migration or auth path, so no manifest gate fires; the two flags (existing behaviour changes, and the proof gap item 3 closes) put it in `normal`. Item 5 is the one item that replaces a raise with a skip on stored data; the manifest keeps `weakening-validation` as high-risk at intake even though the diff hook is warn-mode, and the issue itself rates it "low / consider", so it is excluded rather than dragging four small fixes into the high-risk lane.

### Alternatives considered

- Include item 5 (skip unparseable stored rows) — moves the lane to `high-risk` for a defensive read path with no known malformed writer; excluded by default, user may opt in.
- Item 2 alternative: compare the full duplicate-key args (flight number + date + passengers) instead of the existing booking id — heavier marker parsing; default is the issue's suggestion (embed `existing.id` in the marker and compare with the current request's matched booking).
- Split into 4 tiny PRs — more ceremony than one normal-lane plan with 2 waves.

### Intent Findings

<!-- intent-review (plan-blind, verbatim issue #200) over 63621d1..e50f8b3: items 1–4 faithful and proven by SC-1..SC-12. -->

- **Gap (deferred, recorded) — item 5 not implemented.** Intent: "5. **Strict `_as_date` on stored dates (CR-4, low).** … skipping an unparseable row would be safer than failing the booking." Scoped out at intake (it replaces a raise with a skip on stored data, which the manifest classifies `weakening-validation` → high-risk); the intake report named the exclusion and the user replied "ok" (2026-09-15). The PR references #200 without closing it, so item 5 stays open on the issue.
- **Drift (behaviourally equivalent for the issue's example) — advisory.** Intent: "Compare the warned booking (for example, include the existing booking id in the marker) with the current request." The tools compare the warned ids with *every* active booking matching the request (`DuplicateBookingError.matches`), not only the newest; the issue's example ("book flights A and B, B again is fine") books (SC-6). Stricter in one edge case, in the issue's fail-safe direction (added by correctness-review C1).
- **Excess (small) — report-only.** Intent: "Build the message from `existing.details` instead." The hotel warning also states the existing booking's adults and children. Flagged to the user when the plan was written; no objection.

### Deviations

- Rule 1 — Marker regex `[^\]\s]+` did not match malformed markers (`[possible-duplicate:]`), so the turn guard honoured the override (fail-open against the Global Constraint "an unparseable marker never honours an override"). Regex widened to `[^\]]*` and an empty/whitespace id now maps to the wildcard; 3 tests added. `apps/api/app/exceptions.py`, `apps/api/app/tools/_idempotency.py`, `apps/api/tests/tools/test_duplicate_warning_guard.py`. Commit `0d98c88` (controller, from task 1.2 review finding).
- Rule 1 — Correctness-review C1 (score 75): the same-turn override guard compared only the one booking the service named (the newest match), so a newer matching booking committed after the warning let an unconfirmed duplicate through. `DuplicateBookingError` now carries every matching booking (`matches`, default `(existing,)`); the service collects all matches before raising; both book tools refuse when any match was warned this turn. `apps/api/app/exceptions.py`, `apps/api/app/services/booking_service.py`, `apps/api/app/tools/flight_tools.py`, `apps/api/app/tools/hotel_tools.py`, tests in `tests/services/test_booking_duplicate.py` (`-k all_matches`) and `tests/tools/test_booking_duplicate_tools.py` (`-k newer_match`). Commit `e50f8b3`.
- Rule 3 — Task 1.2 reworded a docstring that raised a `SyntaxWarning` (W605). `apps/api/app/tools/_idempotency.py`. Commit `5b2c1b7`.

### Advisory Findings

<!-- Below-threshold / design-intent / unmodified-line findings from per-task review and correctness-review. Non-blocking; surfaced for the human. -->

- **C1 (correctness; enclosing-function, guard-completeness, prior-art) — FIXED in `e50f8b3`, score 75.** See Deviations. Independent re-review over `7a88b7b..e50f8b3`: closed (trigger traced — X warned, newer Z via REST → refused before insert, row count unchanged; no-override, nothing-warned, different-target, wildcard and REST paths unchanged).
- **R1 (C1 re-review, P3, unreachable today).** `DuplicateBookingError(existing=b, matches=[])` stores `matches=()`, so the tool guard's `any(...)` is False even for the `*` wildcard. Nothing constructs that today: both service raises sit behind `if matches:` and every other constructor omits `matches`. Suggested hardening: `tuple(matches) if matches else (existing,)` in `app/exceptions.py`.
- **R2 (C1 re-review, P3, residual of C1).** If the warned booking X is cancelled mid-turn and a newer matching Z is committed concurrently, the re-run's matches are `[Z]` (cancelled rows are excluded), `Z ∉ warned`, and the override books next to Z without the traveller seeing Z. Needs a cancellation plus a concurrent commit in one turn. Closing it means refusing whenever a match was not warned, which changes the per-booking policy issue #200 item 2 asks for; recorded for a human decision.
- **C2 (correctness, guard-completeness) — closed, score 0 on re-score.** Claim: moving `is_available` above the per-owner lock lets two concurrent same-owner hotel bookings overbook (`booking_service.py:527-547`). The first scorer gave 75 on the premise that availability re-reads committed rows under the lock. That premise is false: `hotel_service.available_rooms` is an MD5-seeded deterministic function of hotel id and dates and reads no booking rows (`hotel_service.py:73-86`), so a concurrent insert cannot change its answer. A focused re-score that read that file scored 0. Both scores are recorded here.
- **C3 (correctness, stack-defects + call-site-impact) — design intent, not a defect.** Once any warning is flagged this turn, `allow_duplicate=true` for a *different* booking that was never shown is honoured (`flight_tools.py:494-519`, `hotel_tools.py:604-642`). This is what issue #200 item 2 asks for: "book flights A and B, B again is fine" → A is warned, then B's override is refused … the traveller has to repeat themselves." It also equals the pre-existing no-warning path (`allow_duplicate=true` with nothing warned skips the check).
- **A1 (correctness, unmodified-line, score 0 by rule).** `_idempotency.py` turn-boundary scan uses `(_last_human_index(...) or -1) + 1`; with the HumanMessage at index 0 the scan starts at it instead of after it. Harmless (not a ToolMessage). Suggest an explicit `is None` check.
- **M2.1-a (task 2.1 review).** Tool compares the single booking the service raised for; two active matches with an exact `created_at` tie have no deterministic order (`repositories/booking.py:182` orders by `created_at DESC` only). Suggest `id` as a secondary order key. See also C1.
- **M2.1-b (task 2.1 review).** Different-booking retry tests run on SQLite; no test proves the per-owner advisory lock is still held on the retry (code reading says it is: same session inside one `session_scope`, no rollback before raise). Suggest a Postgres/test-docker case.
- **M2.2-a (task 2.2 review).** The graph test does not pin the second turn's shape (`len(booked) == 3`, `main._cursor == 6`). It still decides SC-9.
- **M1.2-a residual (task 1.2 review).** A marker cut off before its closing `]` does not match the regex (same exposure as the pre-gh-200 substring check).
- **M1.1-c (task 1.1 review).** Ruff-format churn on an untouched test. Accepted.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| unit — hotel duplicate message quotes the existing booking (1 room, not the request's 3) | `cd apps/api && ../../.venv/bin/python -m pytest tests/services/test_booking_duplicate.py -q -k existing_details` | 0 | 1 passed @ 7a88b7b | SC-1 |
| unit — sold-out hotel reports sold-out before the duplicate prompt; duplicates still raise | `cd apps/api && ../../.venv/bin/python -m pytest tests/services/test_booking_duplicate.py -q -k "sold_out or duplicate_raises"` | 0 | 3 passed @ 7a88b7b | SC-2 |
| unit — id-bearing marker, legacy + malformed forms, no double tag | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools -q -k "duplicate_warning_guard and marker"` | 0 | 5 passed @ 7a88b7b | SC-3 |
| unit — id-aware turn guard, wildcard for legacy/malformed, bool wrapper | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools -q -k "duplicate_warning_guard and not marker"` | 0 | 9 passed @ 7a88b7b | SC-4 |
| unit — same booking refused same turn; new message / no context honours override (flight + hotel) | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_booking_duplicate_tools.py -q -k "same_turn or new_message or no_context"` | 0 | 8 passed @ 7a88b7b | SC-5 |
| unit — warning about a different booking no longer blocks the override (flight + hotel) | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_booking_duplicate_tools.py -q -k different_booking` | 0 | 2 passed @ 7a88b7b | SC-6 |
| unit — legacy bare marker refuses any override | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_booking_duplicate_tools.py -q -k legacy_marker` | 0 | 2 passed @ 7a88b7b | SC-7 |
| graph — real ToolNode warning → REVISE override refused, 1 row | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents -q -k "booking_duplicate_override and same_turn"` | 0 | 1 passed @ 7a88b7b | SC-8 |
| graph — new traveller turn honours the override, 2 rows | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents -q -k "booking_duplicate_override and new_turn"` | 0 | 1 passed @ 7a88b7b | SC-9 |
| regression — service dup + owner lock, idempotency, booking turn, reflection guard, REST booking | `cd apps/api && ../../.venv/bin/python -m pytest tests/services/test_booking_duplicate.py tests/services/test_booking_owner_lock.py tests/tools/test_booking_idempotency_key.py tests/tools/test_booking_idempotency_tools.py tests/agents/test_booking_turn_no_revise.py tests/agents/test_reflection_booking_guard.py tests/api/booking -q` | 0 | 120 passed @ 7a88b7b | SC-10 |
| unit — service carries every matching booking on the duplicate error (flight + hotel) | `cd apps/api && ../../.venv/bin/python -m pytest tests/services/test_booking_duplicate.py -q -k all_matches` | 0 | 2 passed @ e50f8b3 (correctness-review C1) | |
| unit — same-turn override refused when a newer match appears after the warning (flight + hotel) | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_booking_duplicate_tools.py -q -k newer_match` | 0 | 2 passed @ e50f8b3 (correctness-review C1) | |
| lint | `cd apps/api && ../../.venv/bin/ruff check app tests/services/test_booking_duplicate.py tests/tools/test_duplicate_warning_guard.py tests/tools/test_booking_duplicate_tools.py tests/agents/test_booking_duplicate_override.py` | 0 | All checks passed @ 7a88b7b | SC-11 |
| format | `cd apps/api && ../../.venv/bin/ruff format --check app/exceptions.py app/tools/_idempotency.py app/tools/flight_tools.py app/tools/hotel_tools.py app/services/booking_service.py tests/services/test_booking_duplicate.py tests/tools/test_duplicate_warning_guard.py tests/tools/test_booking_duplicate_tools.py tests/agents/test_booking_duplicate_override.py` | 0 | 9 files already formatted @ 7a88b7b | SC-12 |

### Not auto-verified

- Existing agent tool suite green on main before the branch starts — reached traceability (gh-194 SUMMARY records 350 passed at `4fca57a`); not re-run at intake.
- Broad regression `cd apps/api && ../../.venv/bin/python -m pytest tests/tools tests/agents tests/services -q` — reached truth (run by the controller at `7a88b7b`: 916 passed, 6 skipped, ~74 s; after the C1 fix, `tests/tools tests/agents tests/services tests/api/booking` at `e50f8b3`: 989 passed, 6 skipped, ~98 s); kept out of the Verify table because it exceeds the 60 s per-row limit of `verify_summary.py --check`.

### Rollback

- `git revert <sha>` per commit; no migration involved.

### Harness-Delta

- none
