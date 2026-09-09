<!--
  Canonical SUMMARY.md shape (templates/SUMMARY.template.md). Header block is machine-read:
  hooks/risk-corroboration.sh greps `Lane:`; the trust-metrics ledger reads Lane/Confidence/Flags.
-->

# gh-147-dated-hotel-availability-routing — Summary

Lane: normal
Confidence: high
Reason: no manifest hard gate (no auth/authz/schema/route/provider/high-blast path — the fix surface is a tool-binding table, a supervisor/concierge prompt, and possibly an eval golden). 3 flags fired: existing behavior (changes which tools a sub-agent may call, or which specialist a whole class of request routes to), multi-domain (supervisor + concierge + planner tool registry + eval dataset), weak proof (eval-run evidence only, one nondeterministic golden). Confidence was `low` at intake (>1 materially different fix directions); raised to `high` after the direction was decided by the user on 2026-09-09 — E002/A (concierge owns dated + dateless hotel search).
Flags: existing behavior, multi-domain, weak proof
Affects: apps/api/app/tools/registry.py (TOOLS_BY_DOMAIN — concierge hotel binding), apps/api/app/prompts/concierge/* (+ active.yaml, CHANGELOG), apps/api/tests/tools/test_tool_registry.py (MIN-51 guard), apps/api/eval/baselines/main.json (re-run). Goldens in apps/api/eval/datasets/hotels.json are NOT edited under direction A.
Input-type: change request (bug #147, found by the review-b7 eval baseline)
Route: normal — using-git-worktrees (in-place branch `fix/gh-147-dated-hotel-availability-routing` off `main`) → xia2 (Standard) → writing-plans (>2 files: registry.py + concierge v12 + active.yaml + CHANGELOG + registry test + prompt pin test) → subagent-driven-development.
Escalate: raised and RESOLVED — E001 (ambiguous direction: the issue's expected behavior, concierge calling `search_hotels`, is unreachable in the current architecture). Decided 2026-09-09 by the user, then changed the same day: E002 supersedes E001 — option **A**, bind both `search_hotels` and `browse_hotels` to the concierge, no booking power. No pending escalation remains.

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> cho gh issue nay https://github.com/minhtran3124/travel-pi/issues/147

Issue #147 (verbatim): "Found by the review-b7 full eval run (2026-09-07). Golden `hotels-multi_turn-en-01`: turn 1 \"I'm looking for a hotel in Da Nang\", turn 2 \"Check-in September 10 2026, check-out September 14 2026, 2 adults, 1 child\" (future dates). The agent called `browse_hotels` (date-less) instead of `search_hotels` and replied \"I can help narrow hotels, but I can't check real room availability\" — the dated search tool exists and the DB oracle computes 24/24 available, min 140.0. Expected: `search_hotels` with the given dates. Spec: specs/review-b7-eval-baseline-ci/TRIAGE.md."

## What changed

The concierge can now answer a hotel question with **or** without dates. `TOOLS_BY_DOMAIN` binds
`search_hotels` (dated availability) to the `concierge` domain alongside the dateless
`browse_hotels`; `book_hotel` stays out, so booking remains the only HITL-gated, money-holding
route, and the registry guard was strengthened from "no `book_hotel`" to "no destructive tool at
all". Because the model now holds two overlapping tools, the choice rule is stated in both places
it reads independently: concierge **v12**'s rewritten `## Hotels` section (no dates → `browse_hotels`,
and never ask for dates/rooms/guests to browse; dates already given → `search_hotels` with exactly
those values) and `browse_hotels`'s own description, which used to send every dated search to the
booking flow. The v11 sentence "you do not quote date-specific availability" is gone — it described
a toolset the concierge no longer has.

Commits: `ac4c085` (registry binding + guard), `2789a73` (`browse_hotels` description),
`505ed2b` (review fix: pin the positive clause too), `d489a71` (concierge v12 + `active.yaml` +
CHANGELOG + pin), `6d1ac3c` (dated-turn graph tests).

### Reviews

- **Wave 1** — 4/4 verdicts pass/approved. Independently confirmed: blast radius exact, the
  `search_hotels` docstring byte-identical to base (2102 == 2102 bytes), concierge = 16 tools with
  an empty destructive set, `ALL_TOOLS` unchanged. One Minor fixed in `505ed2b`.
- **Wave 2** — spec pass on both tasks; quality approved on 2.2, `needs_fixes` on 2.1 for one
  **Important** finding, deliberately deferred (see "Open, deferred by decision" below).

### Impact analysis (2026-09-09, read-only)

A makes the code agree with what is already shipped: supervisor v11 already routes hotel
*availability* lookups to the concierge (an unbacked promise today), and the eval dataset
already pins `concierge` + `search_hotels` on **three** goldens — `hotels-multi_turn-en-01`
(#147), `hotels-multi_turn-vi-01`, `hotels-happy-en-02` — **all three failing** in
`eval/baselines/main.json`. A fixes all three with no oracle edit.

Nothing breaks silently. Safety surfaces are untouched: `search_hotels` is
`readOnly=True / destructive=False`, takes no `user_id`/`trip_id`, and was already reachable
free-tier via the planner; `ALL_TOOLS` / `TOOL_METADATA` / the MCP manifest do not change; the
booking-only HITL interrupt and `test_planner_never_binds_destructive_tools` are unaffected;
the FE already maps both tool names to the `hotels` panel. What must change: one line in
`registry.py`, the MIN-51 guard `test_hotel_tool_split` (asserts `search_hotels not in
concierge` — it will fail by design), and concierge v11 §Hotels, which explicitly forbids
asking for dates and forbids quoting availability → v12 + `active.yaml` + CHANGELOG.

**The one real risk is a repeat of a defect already observed once.**
`specs/min-51-hotel-search-intent/PLAN.md` records that the concierge WAS bound to
`search_hotels` and failed live review: it interrogated the traveller for
check-in/out/rooms/guests before showing anything, because `search_hotels` has six required
args and its docstring orders the model to collect every one. `browse_hotels` exists to stop
that. Binding both hands the choice back to the LLM, putting the four currently-passing
dateless goldens (`hotels-happy-vi-01`, `hotels-happy-en-01`, `errors-happy-vi-01`,
`errors-multi_turn-vi-01`) at risk. Mitigation ships with the binding, not after: concierge
v12 states the rule mechanically (no dates in the conversation → `browse_hotels`, never ask
for dates/rooms/guests to browse; dates already volunteered → `search_hotels`), pinned by a
prompt-content test, and eval re-runs the hotels + errors capabilities before the fix is
claimed.

### Intake findings (2026-09-09, read-only)

The agent's behavior in the failing trace is **not** a prompt-obedience miss — it is the only
behavior the current wiring allows:

- `apps/api/app/tools/registry.py` binds `HOTEL_SEARCH_TOOLS = [browse_hotels]` (dateless) to
  **concierge**, and `HOTEL_AVAILABILITY_TOOLS` (`search_hotels`, dated) to **planner**;
  `booking` gets the full `HOTEL_TOOLS`. The concierge therefore **cannot** call `search_hotels`.
- The golden pins `expected_flow: "concierge"` **and** `expected_tools: ["search_hotels"]`
  (`apps/api/eval/datasets/hotels.json`) — a combination that no wiring in `main` can satisfy.
- `apps/api/app/prompts/supervisor/v11.md` (lines 17, 33–34, 43) routes hotel lookups —
  explicitly naming **availability** — to concierge, and says "a bare hotel question goes to
  **concierge**". So the supervisor prompt promises a capability the concierge's toolset does
  not have; the reply "I can't check real room availability" is the concierge being truthful
  about its own tools.
- The concierge prompt (`v11.md` lines 77–87) tells it to call `browse_hotels` and to never
  claim availability — consistent with its toolset, inconsistent with the golden.

Root cause is therefore a **capability/routing contract mismatch**, not a single wrong line.
Which side is wrong is the decision in E001.

### Rationale

Lane `normal`: no hard gate fires on any candidate surface, but the change alters existing
LLM-decided behavior across more than one agent and touches the eval oracle, so tiny is not
available. Confidence `low` because the issue's stated expectation is unreachable as written —
choosing between "widen the concierge" and "re-route dated hotel requests" is a product/
architecture decision (it decides whether the concierge is an info-only agent), not a
classification the orchestrator should make silently.

### Alternatives considered

- Declaring `high` confidence and picking the smallest diff (add `search_hotels` to the
  concierge domain) — rejected: it erases the deliberate info/booking tool split documented in
  the `browse_hotels` docstring, and does so without the human who owns that split.
- Declaring the golden simply wrong (expected_tools → `browse_hotels`) — rejected as a silent
  intake call: it would make a real capability gap disappear by editing the oracle, and the
  issue author explicitly stated the opposite expectation.

### Deviations

- **Rule 1 (plan-authoring bug, controller-resolved).** Task 1.2's Action gave verbatim docstring
  text ending "…stays with the booking flow", while the same Action and SC-5 asserted the
  description must NOT contain "the booking flow" — mutually unsatisfiable. The implementer stopped
  and escalated instead of rewording silently. Resolved by narrowing the assertion to what it
  actually meant: the banned string is now `for a real reservation with exact dates` (the v11 clause
  that routed dated searches to booking), which the reviewer independently confirmed is present at
  base, so the test genuinely fails on base and is not a tautology. `PLAN.md` Task 1.2 and SC-5 were
  patched to match before the implementer continued.
- **Wave-1 review Minor, fixed in `505ed2b`.** The `browse_hotels` description test rested on a
  single negative assert; added a positive assert on the new "As soon as they give check-in and
  check-out" clause.

### Open, deferred by decision (wave-2 review, Important)

`search_hotels`'s docstring — shared with the planner and booking agents, and deliberately out of
scope — tells the model to "collect every one from the traveller and **never guess or assume**"
`rooms`/`adults`/`children`, and to restate-and-confirm any value that "only appeared earlier in the
conversation". Concierge v12 says the opposite for values the traveller already gave. The target
golden `hotels-multi_turn-en-01` never states `rooms`, so a model obeying the docstring may ask
instead of searching, and the golden fails for a reason the prompt fix cannot reach.

Not acted on: the user chose to **measure first** (wave 3) rather than edit a surface two other
agents read. If the eval shows the model asking instead of calling, the reword lands with evidence
and its own eval coverage for `flight_search`. Recorded here so a pass is not mistaken for this
risk being absent.

### Eval acceptance (wave 3, 2026-09-09, k=3, premium + authenticated)

Targeted judged runs inside `api-api-1` after `touch app/main.py`. The three at-risk dateless
goldens carry `suite: smoke`, which `--suite full` skips, so a second pair of smoke runs covers
them — a plan gap caught during execution (SC-10 corrected).

| Golden | Before (`eval/baselines/main.json`) | After | Tools called | Note |
| --- | --- | --- | --- | --- |
| `hotels-multi_turn-en-01` (#147) | **FAIL** | **PASS** | `browse_hotels`, `resolve_date`, `search_hotels` | the reported defect; oracle fact-check green. The trace is cumulative over both turns: `browse_hotels` is turn 1 ("a hotel in Da Nang", no dates) and `search_hotels` is turn 2 once the dates arrive — exactly the v12 rule, not a stray extra call |
| `hotels-multi_turn-vi-01` | **FAIL** | **PASS** | `browse_hotels`, `search_hotels` | same two-turn shape: dateless browse on turn 1, dated search on turn 2 |
| `hotels-happy-en-02` | **FAIL** | FAIL — `reply_language` only | `search_hotels` (single turn) | `flow_match`, `tools_expected`, `oracle_fact_check`, `non_empty_reply` all pass; the reply came back `vi` for an `en` turn = **#148**, unrelated to this change |
| `hotels-happy-vi-01` | pass | **PASS** | `browse_hotels` | dateless — no regression |
| `hotels-happy-en-01` | pass | **PASS** | `browse_hotels` | dateless — no regression |
| `errors-happy-vi-01` | pass | **PASS** | `browse_hotels` | dateless — no regression |
| `errors-multi_turn-vi-01` | pass | **PASS** | — | dateless, city correction |
| `errors-ambiguous-en-01` | fail | FAIL — `non_empty_reply` | — | pre-existing HITL empty-draft gap = **#153** |
| `hotels-happy-vi-02`, `hotels-ambiguous-vi-01`, `hotels-ambiguous-en-01` | pass | **PASS** | | |

### Correctness-review follow-up and the eval churn it caused (2026-09-09)

The branch correctness review found a real gap the new capability exposed:
`HotelService.check_availability` returns **every** hotel matching city + filters, flagging each
with `available`, and the model-visible summary counted them all and named "cheapest $X" without
checking whether that room could be had. Harmless while the concierge could not quote dated
availability (booking caught it at `book_hotel`); not harmless now.

Fixing it took three attempts, and the eval is what caught the two bad ones:

| Run | Change under test | `hotels` full | What it taught |
| --- | --- | --- | --- |
| `gh147-hotels.json` | wave 1–2 as shipped | 5/6 | `hotels-multi_turn-en-01` (#147) passes; only `reply_language` red (#148) |
| `gh147-hotels-v2.json` | summary rewritten to "N of M have a room free" + a v12 rule to shortlist only available ones | **3/6** | the model narrated its own 4-hotel shortlist as the search result — "4 hotels available at $560" against 24 from $140 — and the oracle read it as a false claim |
| `gh147-hotels-v3.json` | counts dropped from the summary, v12 rule kept | 4/6 | better, but any availability sentence in the prompt still made the model narrate availability counts |
| `gh147-hotels-v4.json` | **identical code and prompt to v3** — the intended prompt revert silently did not apply (a failed `cd` in the edit command; caught by the post-review re-check) | **5/6** | `hotels-multi_turn-en-01` **and** `hotels-happy-en-02` both pass |

What actually moved the score was the **tool summary**, not the prompt. v2's "N of M hotels have a
room free … present only the available ones" gave the model counts to repeat, and it repeated them
about its own shortlist. v3 removed those counts and kept the short prompt sentence; **v4 ran on
byte-identical code and prompt and scored 5/6 instead of 4/6**, so that difference is run-to-run
variance, not a fix. The shipped state keeps both halves: the short v12 sentence (pinned by
`test_concierge_prompt_never_shortlists_a_sold_out_hotel`) and the deterministic guard in the tool
output, whose summary is byte-identical to wave 2's whenever every hotel is available.

This correction exists because the re-check caught the record claiming a revert that never
happened: the commit meant to remove the v12 sentence deleted only its pin test, because a `cd`
in the edit command failed and took the prompt edit with it. The prompt sentence was present for
v3 **and** v4 — which is what makes them a clean variance comparison.

**Final state (v4 runs):** `hotels` full 5/6, `hotels` smoke 2/2, `errors` full 5/6. The one red
is `hotels-multi_turn-vi-01` on `oracle_fact_check`, and only on `available_count` (oracle 3,
claimed 2) — price, nights, hotel count, flow, tools and language all match. Across the four runs
a different single golden goes red each time on this same extractor, so treat `oracle_fact_check`
on the hotel goldens as **flaky at k=3**, not as a signal about this diff. Both #147 goldens have
passed; `hotels-multi_turn-en-01` passed in the first and last run.

Capability roll-up: `hotels` full 5/6 (83.3%), `errors` full 5/6 (83.3%), both smoke suites 2/2.
Neither remaining failure is caused by this change.

**The MIN-51 regression did not return.** Every dateless golden still calls `browse_hotels`, and no
run shows the concierge asking for dates, rooms or guests in order to browse — the failure this
branch was most exposed to. **Wave 4 (the code-gate fallback) is therefore `skipped — not
triggered`**; `_base.py` is untouched.

**The deferred wave-2 Important finding did not bite either.** `hotels-multi_turn-en-01` never
states `rooms`, yet the model called `search_hotels` rather than stopping to ask, so the
`search_hotels` docstring's "never guess or assume / restate and confirm" clause did not block the
search on this golden. It stays unedited and the risk stays recorded, not closed.

### Browser UAT (2026-09-09, signed-in `e2e-test`, Docker api :8000)

Driven with Playwright against the running travel-pi web app; spec + screenshots in
`uat/` (`uat-hotel-dates.spec.ts`, run recipe in its header). Both turns of the reported
conversation, in one thread:

| Turn | Input | Result | Screenshot |
| --- | --- | --- | --- |
| 1 | "I'm looking for a hotel in Da Nang" (no dates) | "Here are a few good Da Nang hotel picks" + the **catalog** panel: `→ · 0 nights · 1 room · 24 results · cheapest $35`. **No date interrogation** — the assistant did not ask for check-in/check-out to browse. | `uat/1-no-dates-browse.png` |
| 2 | "Check-in March 10 2027, check-out March 14 2027, 2 adults, 1 child" | "for **10 Mar 2027 to 14 Mar 2027** with **2 adults and 1 child**, I found **24 hotels in Da Nang**" + the **dated** panel: `2027-03-10 → 2027-03-14 · 4 nights · 1 room · 24 results · cheapest $140`, every row badged **available**. The sentence issue #147 reported ("I can't check real room availability") is asserted absent. | `uat/2-dated-availability.png`, `uat/3-dated-panel.png` |

The panel numbers match the DB oracle for that stay (24 hotels, 24 available, min $140), which is
the same fact the eval's `oracle_fact_check` grades. The spec asserts the dated panel's exact
stay (`2027-03-10`, `2027-03-14`, `4 nights`) rather than a bare year, so a trip card on the page
behind the drawer cannot satisfy it.

Environment note: `:3000` was another project's app on this machine — travel-pi's dev server was
on `:3001`, and `playwright.config.ts` hardcodes the base URL, so the run needed a temporary
config edit (reverted; `apps/web` is clean).

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| concierge holds both hotel search tools, no `book_hotel` | `cd apps/api && ../../.venv/bin/python -c "from app.tools.registry import get_tools_for;n={t.name for t in get_tools_for('concierge')};assert {'search_hotels','browse_hotels'}<=n;assert 'book_hotel' not in n"` | 0 | concierge = 16 tools | SC-1 |
| registry guard tests | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_tool_registry.py -q` | 0 | 54 passed | SC-2 |
| no destructive tool reachable from concierge | `cd apps/api && ../../.venv/bin/python -c "from app.tools.registry import TOOL_METADATA,get_tools_for;assert not {t.name for t in get_tools_for('concierge') if TOOL_METADATA[t.name]['destructive']}"` | 0 | destructive set empty | SC-3 |
| MCP/public tool surface unchanged | `cd apps/api && ../../.venv/bin/python -c "from app.tools.registry import ALL_TOOLS;assert len({t.name for t in ALL_TOOLS})==len(ALL_TOOLS);assert {'search_hotels','browse_hotels','book_hotel'}<={t.name for t in ALL_TOOLS}"` | 0 | 35 tools, no dupes; reviewer byte-compared the `search_hotels` docstring against base | SC-4 |
| tool descriptions: browse re-pointed, search untouched | `cd apps/api && ../../.venv/bin/python -c "from app.tools.hotel_tools import browse_hotels as b,search_hotels as s;bd=' '.join(b.description.split());sd=' '.join(s.description.split());assert 'no dates' in bd and 'search_hotels' in bd;assert 'for a real reservation with exact dates' not in bd;assert 'collect every one from the traveller and never guess' in sd"` | 0 | assertion narrowed mid-task, see Deviations | SC-5 |
| concierge v12 active and states the choice rule | `cd apps/api && ../../.venv/bin/python -c "from app.prompts.registry import registry;assert registry.active_version('concierge')==12;t=' '.join(registry.get('concierge').split());assert 'never ask for dates, rooms or guests in order to browse' in t;assert 'already given you check-in and check-out' in t"` | 0 | `diff v11.md v12.md` = 4 hunks, all inside `## Hotels` | SC-6 |
| prompt suite | `cd apps/api && ../../.venv/bin/python -m pytest tests/prompts -q` | 0 | 24 passed | SC-7 |
| dated concierge turn searches, no plan-approval interrupt | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_hotel_search_intent.py -q` | 0 | 5 passed | SC-8 |
| hotel tool behaviour unregressed | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_hotel_tools.py tests/tools/test_booking_tools.py tests/tools/test_hotel_tools_language.py -q` | 0 | 35 passed | SC-9 |
| plan contract | `python3 .claude/scripts/check_plan_contract.py specs/gh-147-dated-hotel-availability-routing/PLAN.md` | 0 | passed | |

| targeted eval acceptance recorded per golden | `cd apps/api && ../../.venv/bin/python -c "import json,glob;ids=set(c['golden_id'] for f in glob.glob('eval/reports/gh147-*.json') for c in json.load(open(f))['per_case']);assert {'hotels-multi_turn-en-01','hotels-multi_turn-vi-01','hotels-happy-en-02','hotels-happy-vi-01','hotels-happy-en-01','errors-happy-vi-01','errors-multi_turn-vi-01'}<=ids"` | 0 | 4 reports cover the 3 dated targets + the 4 dateless guards | SC-10 |

The full BE suite and `make eval-check` run at delivery, not here.

### Not auto-verified

- **The eval reports are gitignored.** `apps/api/eval/reports/` is excluded by `.gitignore`
  (derived artifacts; only `eval/baselines/` is tracked), so the four `gh147-*.json` files behind
  the wave-3 table exist only in this working copy. The per-golden table above was transcribed
  from them, not hand-written — but SC-10 reaches **traceability** tier for anyone else: they must
  re-run the two `--suite full` and two `--suite smoke` commands (paid, k=3) to re-derive it.
- **Prompt compliance is probabilistic.** The four runs were launched with `--repeat 3` and cover
  16 distinct goldens, but each report records one boolean per golden, not per-repeat outcomes — so
  the aggregation behind a PASS is **not** re-derivable from the artifact. Treat the table as
  **provenance** tier (re-derived from the report files) rather than truth tier, and the underlying
  behaviour as evidence, not a guarantee. A future model or prompt change can re-open the MIN-51 failure; the
  code-gate fallback (PLAN Task 4.1) stays specified and unbuilt for that case.
- **`hotels-happy-en-02` is still red** on `reply_language` (#148) and `errors-ambiguous-en-01` on
  `non_empty_reply` (#153). Both were red before this branch; neither was re-tested against a fix,
  and neither is claimed fixed here.
- **The committed baseline was not refreshed.** `eval/baselines/main.json` still records the
  pre-fix failures for these goldens; it is refreshed only by the full judged `make eval-check`
  run at delivery.
- **The UAT ran against local Docker + a signed-in `e2e-test` account**, one pass, not k=3 — it
  is a demonstration that the path works end to end in the browser, not a statistical claim.

### Rollback

- `git revert <sha>` (intake commit only — documentation, no code change).

### Harness-Delta

- backlog → `compound`: two goldens in a row (#156, #147) encode an expectation that the
  shipped architecture cannot satisfy, and both surfaced only at intake. Worth a durable note:
  an eval golden pinning both `expected_flow` and `expected_tools` must be checked against
  `TOOLS_BY_DOMAIN` when it is written, or it fails forever for a reason no prompt fix reaches.
