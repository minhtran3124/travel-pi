---
slug: flight-fare-no-fabrication
status: shipped
owner: Minh Tran
created: 2026-07-20
---

# The agent must never state a fare it did not retrieve

## 1. Motivation

The agent searched one leg (`DAD → TYO`, 2026-09-01) and told the traveller
"**from $136** round-trip total if you take the cheapest one each way" — `$68 × 2`. No return leg
was searched; the figure came from no tool, and then fed the "$1,200–$2,200" budget ballpark.

The tool could not have done better: `SearchFlightsArgs` is strictly one-way
(`app/tools/flight_tools.py:59-115`) even though `GET /flights/search` already supports
`return_date` and returns `return_count` / `return_results` (`app/schemas/flight.py:79-132`).
The capability exists and was never wired to the agent.

MIN-67 / GitHub #98. Scope decided in `ESCALATIONS.md` E001 (option A).

## 2. Non-goals

- Giving the `budget` sub-agent flight tools. It currently cannot see fares at all
  (`registry.py:56`); widening its toolset is a separate design question.
- Multi-city / open-jaw itineraries. Out-and-back only.
- Changing the deterministic flight generation (seeded from MD5 — must not change).
- The weather defect (MIN-66) — separate slug, already in PR #101.

## 3. Success Criteria

1. The agent can retrieve a real return-leg fare instead of deriving one.
2. The text the model reads states the fare is one-way (or round-trip) and names the currency.
3. A prompt rule forbids stating any price not returned by a tool — including derived arithmetic,
   which today's "never invent" wording does not cover.
4. Existing MCP clients are unaffected: `return_date` is optional and omitting it behaves exactly
   as before.

## 4. Tasks

### Task 1.1 — Wire `return_date` through the flight tool (wave 1)

- **Files:** apps/api/app/tools/flight_tools.py, apps/api/tests/tools/test_flight_tools.py
- **Action:** Add an optional `return_date` to `SearchFlightsArgs`, resolved through the same
  `resolve_travel_date` path as `departure_date` (match the existing pattern exactly). Pass it to
  the service, which already accepts it at the REST layer — check whether
  `flight_service.search_flights` needs the parameter threaded too, and thread it if so. Omitting
  `return_date` must leave the current one-way behavior byte-identical. The field description must
  tell the model to search the return leg rather than doubling the outbound fare.
- **Verify:** `cd apps/api && DATABASE_URL=sqlite:///./travel.db ../../.venv/bin/python -m pytest tests/tools/test_flight_tools.py tests/api/flight -q`
- **Done:** A round-trip search returns both legs' real fares; a one-way search is unchanged.

### Task 1.2 — Label the fare in the text the model reads (wave 1)

- **Files:** apps/api/app/tools/flight_tools.py (summary builder only), apps/api/tests/tools/test_panel_result.py
- **Action:** The summary at `flight_tools.py:175-182` hardcodes `$` and never says "one-way", so
  the model has no cue what the number covers — a direct contributor to the defect. Include the
  currency from the result and state one-way vs round-trip. Keep it terse; the string is read by
  an LLM on every call.
- **Verify:** `cd apps/api && DATABASE_URL=sqlite:///./travel.db ../../.venv/bin/python -m pytest tests/tools -q`
- **Done:** Summary names currency and leg coverage.

> Tasks 1.1 and 1.2 touch the same file and therefore must NOT run as parallel subagents
> (`rules/wave-parallelism.md` guardrail 1). Same wave, executed sequentially by one agent.

### Task 2.1 — Forbid derived prices in the planner prompt (wave 2)

- **Files:** apps/api/app/prompts/planner/v10.md, apps/api/app/prompts/active.yaml
- **Action:** `planner/v9.md:76` already says "Never invent flights, hotels, or prices — ground
  every concrete option in a tool result." That bans invention but not *derivation*: doubling a
  real one-way fare is grounded in a tool result and still wrong. Extend that existing rule rather
  than adding a competing one — a price stated to the traveller must be one a tool returned, never
  computed from one. Copy v9 → v10 (never edit a shipped version) and bump `active.yaml`.
  **Note:** PR #101 also creates `planner/v10.md`; if that merges first, rebase onto it and author
  v11 instead of colliding.
- **Verify:** `cd apps/api && DATABASE_URL=sqlite:///./travel.db ../../.venv/bin/python -m pytest tests/api/prompts tests/prompts tests/agents -q`
- **Done:** Rule present; active.yaml resolves; prompt-version tests green.

### Task 3.1 — Regression coverage (wave 3)

- **Files:** apps/api/tests/tools/test_flight_roundtrip.py
- **Action:** Pin the MIN-67 behavior at the deterministic seam: a round-trip search returns real
  return-leg data (not the outbound doubled), and a one-way search's summary is labelled one-way.
  Do not assert on model prose. Also extend the eval rubric — `no_hallucination_metric()` in
  `eval/metrics_geval.py:56-68` says "invents… prices" but not "computes from a partial tool
  result"; widen that criteria text.
- **Verify:** `cd apps/api && DATABASE_URL=sqlite:///./travel.db ../../.venv/bin/python -m pytest tests/tools/test_flight_roundtrip.py -q`
- **Done:** Test fails against pre-fix behavior, passes after.

### Task 3.2 — Full-suite gate (wave 3)

- **Files:** (no source files — verification only)
- **Action:** Run the ENTIRE suite with `.env` moved aside, not just the per-wave subsets. On
  MIN-66 the per-wave subsets all passed while `tests/unit/` and `tests/prompts/` were broken;
  that gap is why this task exists as an explicit step.
- **Verify:** `cd apps/api && mv .env /tmp/env.bak; DATABASE_URL=sqlite:///./travel.db ../../.venv/bin/python -m pytest -q; mv /tmp/env.bak .env`
- **Done:** Full suite green.

## 5. Risks

- **Public-contract gate.** `search_flights` is MCP-exported; the commit will trip
  `risk-corroboration.sh`. Authorize with `RISK_WARN_CATEGORIES="public-contract"` and keep the
  high-risk lane declared. Change is additive-optional (E001 option A).
- **Prompt-version collision with PR #101.** Both slugs bump the planner. Whichever merges second
  must rebase and take the next version number — do not edit the other's file.
- **Deterministic flight generation must not change.** The MD5-seeded generator is a documented
  invariant; `return_date` must only select existing generated inventory, never alter seeding.
- **Model may still not search the return leg.** Wiring the capability does not force its use;
  the prompt rule (2.1) and the one-way labelling (1.2) are what make the omission visible.

## 6. Status Log

- 2026-07-20 — Intake: high-risk (public-contract hard gate), confidence high.
- 2026-07-20 — E001 decided by Minh Tran: option A (wire `return_date`).
- 2026-07-20 — Plan written; branch `fix/flight-fare-no-fabrication` off `v3`.

- 2026-09-03 — status corrected to `shipped`. Verified by artifact on `main`, not by the log:
  this plan's deliverables are present in the shipped code. It had been left `active`, which made
  `hooks/lib/lane.sh` resolve it as the plan under work for unrelated commits.
