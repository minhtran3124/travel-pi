# SUMMARY — search-tool-hardening

**Lane:** normal
**Confidence:** high
**Reason:** Two flags fire — *existing behavior* (search-tool return paths are test-covered) and
*weak proof* (no test for empty-results / error on flights; hotel empty is only lightly covered).
No hard gate: flights & hotels are faked (deterministic MD5 seed), so no real external provider;
no auth/authz, no schema/migration, no data loss. Tool-failure handling already exists
(`ToolException` → `_tool_error_to_message`); the real gap is the ambiguous empty-result signal
(`[]`) the LLM receives from both search tools.
**Flags:** existing-behavior, weak-proof
**Affects:** `apps/api/app/tools/flight_tools.py`, `apps/api/app/tools/hotel_tools.py` (agent search-tool return shape — LLM-facing), and their services (`flight_service.py`, `hotel_service.py`)
**Input-type:** Change request
**Route:** in-place branch off `v3` (`git switch -c`, per repo worktree convention) → `/subagent-driven-development`; notify-and-proceed (no human gate — confidence high, direction clear).
**Escalate:** no (ambiguity resolved at intake — user chose "harden first, panel later")

## Intent

User request (verbatim, `/feature-intake` args + follow-up):

> review the search flight tool, make sure it call tool and get correct response, dont
> hallucination. If tool call does not return response make sure we show for user that can not
> use feature now or something went wrong. If results is empty, dont have any flights, should
> answer for user too.
> btw, thinking to create side panel for search flight tool, improve UI/UX to help user can ez
> view flights without scroll down in chatbot.

Follow-up: **"extend for tool search hotel too"** — the same robustness hardening applies to
`search_hotels` (not `book_hotel`, which is a guarded mutation and out of scope).

Scope decision (asked at intake — bundled request was ambiguous): user chose **"Harden trước,
panel sau"**. This spec covers **only workstream A** (robustness) for the two **search** tools.
The side-panel idea (workstream B) is **deferred to `/brainstorming`** and is an *extension of the
already-active* `specs/agent-side-panel/` (add a `flights` — and optionally `hotels` — artifact
kind to the existing `content_and_artifact` → `panel` SSE → FE registry system), not a greenfield
design.

## Rationale

Investigation (Explore agent + direct read of `flight_tools.py` / `hotel_tools.py`) found the
tool-**failure** path is already sound on both tools: `AppError`/`ValueError` → `ToolException` →
LangGraph `ToolNode(handle_tool_errors=_tool_error_to_message)` tells the LLM the info is
temporarily unavailable and not to retry — which surfaces to the user as "something went wrong /
try again shortly". The precise, well-specified gap is the **empty-result signal**: both
`search_flights()` and `search_hotels()` return a bare `[]` (via `dump(results)`) when filters
eliminate all matches, giving the LLM no explicit "no matches for `{filters}`" cue. Despite the
`never-invent-flights/hotels` guardrail, a bare `[]` is a weak signal → risk of a vague or lightly
hallucinated answer. Fix = return a structured empty-result payload (explicit "no flights/hotels
match these criteria" + the applied filters) so the LLM can answer the user clearly, plus
regression tests for empty + error paths on both tools.

**Chosen empty-result shape (user decision):** wrap in a dict **only when empty** — non-empty
return stays a bare list (no contract change, existing non-empty tests untouched). Empty →
`{"results": [], "message": "<human reason + applied filters>", "reason": "<code>"}`. For hotels,
`reason` distinguishes `unknown_city` (fuzzy match found no city) from `no_match` (filters
eliminated all availability).

Hotel note: `search_hotels` has **two** empty causes — an unrecognised city (fuzzy match →
deliberate `[]`) and filters eliminating all matches. The empty-result message should let the LLM
distinguish "we don't know that city" from "no availability matched your filters".

## Alternatives considered

- *Do nothing — rely on the prompt guardrail alone.* Rejected: prompt-only is the weak-proof
  flag; a bare `[]` gives the model nothing to explain the "why".
- *Bundle the side panel now (A+B as one high-risk feature).* Rejected by user — ship the safe
  robustness win first; design the panel deliberately via `/brainstorming` after.
- *Change the non-empty return shape too (always wrap in an envelope).* Deferred: wider blast on
  the tools' LLM-facing contract for no robustness gain; keep the non-empty path as-is.
- *Also harden `book_hotel`.* Out of scope — it is a guarded mutation, not a search; user asked
  about the search tools.

## Verify

| Check | Command | Exit | Notes |
|-------|---------|------|-------|
| Booking tools suite | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_booking_tools.py -q` | 0 | 10 passed (4 new + 1 updated) |
| Lint | `cd apps/api && ruff check app/tools/flight_tools.py app/tools/hotel_tools.py` | 0 | All checks passed |

## Deviations

- Rule 1 — Updated existing `test_search_hotels_unknown_city_returns_empty` (renamed to
  `..._returns_reason`, now asserts the dict signal) because the empty-result contract changed
  intentionally per this spec. Behavior change is the point of the task, not a regression.
- Rule 2 — Also updated the two search-tool docstrings (LLM-facing) to describe the new empty
  shape so the model interprets the dict correctly. `flight_tools.py`, `hotel_tools.py`.
- Note — `blast-radius-check.sh` warns these files aren't in `specs/web-trip-planner/PLAN.md`;
  that is a *different* active plan. They ARE in `specs/search-tool-hardening/PLAN.md`. False
  positive, not scope creep.

## Rollback

- Revert code: `git revert <sha>` (all reversible; no migration, no schema change).

## Notes

- Deferred workstream **B (search side panel)** → run `/brainstorming` and extend
  `specs/agent-side-panel/` (status: active), reusing its `content_and_artifact` / `panel` SSE /
  FE `panel/registry.ts` pattern. Do **not** design a new panel system.
- Branch/worktree: in-place `git switch -c` off `v3`; stage + commit as **separate** commands
  (PreToolUse hook blocks compound `git add && git commit`). PR base = `v3`, `gh` account
  `minhtran3124`.
