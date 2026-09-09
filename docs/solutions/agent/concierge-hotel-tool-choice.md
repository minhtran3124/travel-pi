---
problem_type: decision
module: agent/concierge
tags: langgraph, prompts, concierge, hotels, tool-choice, tool-binding, eval, min-51, gh-147
severity: critical
applicable_when: Writing or reviewing any prompt, routing rule, or eval golden that promises a
  specialist a capability (a tool call, a data lookup) — check it against the toolset that will
  actually execute it before trusting the promise. Also when binding a second, overlapping tool
  to an agent that already holds one that does something similar, or when a `expected_flow` +
  `expected_tools` golden is added or edited.
affects:
  - apps/api/app/tools/registry.py
  - apps/api/app/tools/hotel_tools.py
  - apps/api/app/prompts/concierge/v12.md
  - apps/api/app/prompts/active.yaml
  - apps/api/tests/tools/test_tool_registry.py
  - apps/api/tests/prompts/test_concierge_prompt.py
  - apps/api/eval/datasets/hotels.json
confidence: high
confirmed_at: 2026-09-09
---

## Applicable When

Any time a prompt or supervisor routing rule tells the model a specialist can do something —
"concierge answers hotel availability" — before checking that the specialist's bound toolset can
actually do it. Also applicable when an eval golden is authored: a golden that pins both
`expected_flow` and `expected_tools` is asserting a capability, not just a preference, and that
assertion is checkable in code at write time. And applicable whenever one agent is about to hold
two tools that overlap in purpose (a dateless browse + a dated search, a draft + a send), because
the choice between them then lives entirely in text the model reads.

## Context

GitHub #147 (found by the review-b7 full eval baseline, 2026-09-07). Golden
`hotels-multi_turn-en-01`: "I'm looking for a hotel in Da Nang" → "Check-in September 10 2026,
check-out September 14 2026, 2 adults, 1 child." The concierge called `browse_hotels` (dateless)
and replied "I can help narrow hotels, but I can't check real room availability" — even though
`search_hotels` (the dated tool) existed in the codebase and the DB oracle computed 24/24 rooms
available, min 140.0. Two more goldens (`hotels-multi_turn-vi-01`, `hotels-happy-en-02`) encoded
the same expectation and failed the same way.

This was **not** a prompt-obedience miss. `apps/api/app/tools/registry.py`'s `TOOLS_BY_DOMAIN`
bound `browse_hotels` (dateless) to `concierge` and `search_hotels` (dated) to `planner`/`booking`
only — the concierge could not call the tool the golden expected, full stop. Meanwhile
`app/prompts/supervisor/v11.md` (lines 17, 33–34, 43) already routed hotel **availability**
lookups to the concierge by name, and `app/prompts/concierge/v11.md` (lines 77–90) told the
concierge to never quote date-specific availability — consistent with its own toolset, but
contradicting both the supervisor prompt and the goldens. The agent's truthful denial was the only
behavior three independent surfaces (routing prompt, agent prompt, toolset) could jointly produce.
Nothing in the concierge's prompt could have fixed this — the capability itself did not exist.

## Options Considered

1. **Bind `search_hotels` to concierge alongside `browse_hotels` (chosen, "option A"):** makes the
   code agree with what the supervisor prompt and three eval goldens already assumed; `book_hotel`
   stays out, so booking remains the only HITL-gated, money-holding route.
2. Re-route dated hotel turns to the planner instead ("option B"): needs no registry change, but
   moves the ambiguity into the supervisor prompt (the hottest path in the graph), contradicts
   supervisor v11's own concierge bullet, and requires editing three eval oracles. Rejected by the
   user (escalation E002 superseded an earlier E001 decision the same day).
3. Edit the goldens to expect `browse_hotels` instead: makes a real capability gap disappear by
   moving the oracle rather than closing the gap. Rejected.

## Decision & Rationale

**Bind both tools to the concierge; teach it which one to reach for.** `TOOLS_BY_DOMAIN` now gives
`concierge` both `browse_hotels` and `search_hotels` (16 tools total), and the registry guard was
strengthened from "no `book_hotel`" to "no destructive tool at all," so booking power still cannot
leak in. `search_hotels` was already `readOnly=True / destructive=False`, took no `user_id`/
`trip_id`, and was not `trip_guard`-gated — binding it added no new safety, tier, or HITL surface.

### General principle: corroborate a promised capability against the toolset that executes it

**A prompt or routing rule that promises a capability must be checked against the toolset that
will actually execute it — the promise and the wiring are two separate contracts and either one
can drift alone.** Supervisor v11 promised concierge availability lookups before the concierge
could deliver them; nobody had run that check when the prompt was written. The mechanical,
checkable form of the same principle: **an eval golden that pins both `expected_flow` and
`expected_tools` is asserting a capability claim, and it must be checked against
`TOOLS_BY_DOMAIN` at the moment it is written** — `hotels-multi_turn-en-01` sat in the dataset
pinning `concierge` + `search_hotels`, a combination no wiring on `main` could satisfy, and it
failed every run for a reason no prompt fix could ever reach, because the fix was not in the
prompt layer at all. This is the same failure class GH-156 hit one week earlier
([[planner-search-first-save-later]]) from the opposite direction — there the prompt promised
something outside the *intent*, here the routing prompt promised something outside the
*toolset* — both are a written contract that nobody corroborated against the executing system.

### Second principle: the choice rule belongs in the prompt AND the tool description

Once concierge held two hotel tools, the decision between them is a decision the **model** makes
at tool-selection time, and it reads the prompt and the tool docstring as two independent texts.
Concierge v12's rewritten `## Hotels` section states the mechanical rule (no dates in the
conversation → `browse_hotels`, never ask for dates/rooms/guests in order to browse; the traveller
already gave dates → `search_hotels` with exactly those values), and `browse_hotels`'s own
model-visible description was edited in the same commit to stop sending dated searches to "the
booking flow" — a sentence that used to argue for the old, wrong behavior every time the model
read it. `search_hotels`'s shared docstring was deliberately left alone (see "Still open" below).
LangGraph/LangChain tool-calling guidance names the docstring as the text the model actually reads
to disambiguate overlapping tools, and vague or stale docstrings are the standard cause of the
model picking the wrong one — this matches the in-repo precedent exactly
([[planner-search-first-save-later]]: "prompt text and tool docstrings are read by the model
independently and a fix in only one leaves the other arguing for the old behaviour").

### MIN-51 history and how v12 answers it

The concierge held `search_hotels` once before. `specs/min-51-hotel-search-intent/PLAN.md`
(Status Log, 2026-07-04) records that binding failing live review: the concierge "still asked for
check-in/out/rooms/guests before showing hotels — because its only hotel tool was the availability
`search_hotels`," which has six required args and a docstring ordering the model to collect every
one. `browse_hotels` was created specifically to stop that interrogation. Binding `search_hotels`
back onto the concierge in this fix reopened exactly that risk for four previously-passing
dateless goldens. Concierge v12 answers it by stating the choice rule as a hard branch (dateless →
`browse_hotels`, never interrogate; dated → `search_hotels`) rather than leaving tool selection to
docstring instinct, pinned by a content test.

**Wave 3 evidence it did not recur:** at k=3, every dateless golden still called `browse_hotels`
and no run showed the concierge asking for dates, rooms, or guests to browse —
`hotels-happy-vi-01`, `hotels-happy-en-01`, `errors-happy-vi-01` all **PASS**, unchanged from
baseline. The three targeted dated goldens flipped: `hotels-multi_turn-en-01` (#147) and
`hotels-multi_turn-vi-01` **FAIL → PASS**, both calling `search_hotels`; `hotels-happy-en-02`
stayed red but only on `reply_language` (pre-existing #148, unrelated — `flow_match`,
`tools_expected`, `oracle_fact_check`, `non_empty_reply` all passed). Because the MIN-51 regression
did not return, **wave 4's code-gate fallback was skipped — not triggered**; `_base.py` is
untouched.

## Closed later the same day — the shared description

`search_hotels`' docstring is read by the planner and booking agents as well as the concierge, so
it was left untouched while the branch was measured. It said any value that "only appeared earlier
in the conversation" must be restated and confirmed before searching — which is every multi-turn
hotel conversation, and a round-trip the concierge now pays for. The user authorized the change
after the branch shipped: the anti-hallucination half stays ("never guess or assume a value the
traveller has not given"), the confirmation round-trip becomes "search with what they gave, echo
it back so they can correct you, ask only for what is genuinely missing, ambiguous, or
contradicted later."

The general point: **a tool description shared by several agents is a shared prompt.** Deferring
the edit until there was evidence was right; leaving it forever because it was shared would have
left two agents arguing with each other in the model's context.

Measured after the fact: `hotels` 5/6 and `booking` 6/8 — the latter exactly the committed
baseline's rate, which is the number that mattered, since booking is the agent whose confirmation
rule this description had to stop contradicting. A dateless golden flipped in one run and was
chased down with three control runs at the pre-edit commit: it flips there too, with the same
signature, so it is that golden's own flakiness. The planner's use of the tool was **not**
re-measured.

## What stayed open after the edit

The reason the docstring was left alone at first still holds and is worth carrying: editing a tool
description that three agents read is its own blast radius, and wave 3 showed the old clause did
not actually bite on these goldens — the model called `search_hotels` on a `rooms`-less turn
without stopping to ask. Measuring before editing was the right order.

Two things remain unproven after the edit:

- **All three readers are now measured** — `hotels` 5/6, `booking` 6/8 (baseline rate),
  `flight_search` 6/6, `routing` at or above baseline in three runs. A routing golden that
  mentions a hotel went red and was isolated by reverting only the edited paragraph on the same
  HEAD: red on both sides, and its own notes mark it as derived from a superseded supervisor
  version. Method worth copying: when a shared description changes, re-measure every agent bound
  to the tool, and isolate a suspicious golden by reverting the single paragraph rather than
  arguing from mechanism.
- **The booking prompt still says the opposite for its own path.** `app/prompts/booking/v7.md`
  tells the booking agent to restate a non-date detail that appeared in an earlier turn and get a
  yes/no *before* calling the tool. The tool description now says to search with what the
  traveller gave. The description defers to the agent's own rules for the booking path, so the
  money gate (`book_hotel`'s `confirm=True`, and v7's "never confirm a booking without explicit
  approval") is untouched — but a shared description and a per-agent prompt can drift again, and
  only one of them is pinned by a test.

## Unbuilt fallback

PLAN Task 4.1 specifies a code-gate: filter `search_hotels` out of a date-less turn's tool list at
invoke time, using `build_subagent`'s existing tool-filter mechanism (the same one that drops the
episodic tool). This is deterministic and would remove the model's tool-choice decision entirely,
but it needs a "dates present in this turn" signal that does not currently exist in
`TravelAgentState`, so it stays a documented, unbuilt fallback for the next time the MIN-51
regression actually recurs — do not rebuild it speculatively; build it only against a real
`tools_expected` regression on the dateless goldens.

## Gotcha: eval goldens carry a `suite` field that `--suite full` silently skips

Three of the goldens this decision depends on — `hotels-happy-vi-01`, `hotels-happy-en-01`, and
`errors-happy-vi-01` — carry `suite: smoke`. Running `--suite full` does **not** include them; a
"full" eval run can look complete while silently skipping exactly the regression-guard goldens
this fix needed. Wave 3 caught this during execution (not anticipated in the plan) and ran a
second pair of smoke-suite passes to cover them. When claiming an eval acceptance result, name
which `suite` values were actually run, not just "full."

## Consequences

- Concierge now holds 16 tools with an empty destructive set (`get_tools_for('concierge')`);
  `ALL_TOOLS`/`TOOL_METADATA`/the MCP manifest are byte-identical, so no public surface changed.
- The MIN-51 guard test (`test_hotel_tool_split`, asserting `search_hotels not in concierge`) was
  rewritten to assert the actual invariant instead: no destructive tool reachable from concierge.
- Eval triage: a `tools_expected` regression on any of the four dateless goldens is the signal to
  build the wave-4 code-gate fallback rather than iterating prose a third time.
- Any future tool bound to an agent that already holds an overlapping one needs the same
  treatment: a mechanical choice rule in the prompt, a matching edit to the model-visible
  description of whichever tool is easiest to over-reach for, and a content test pinning both.

## Related

- specs/gh-147-dated-hotel-availability-routing/ (SUMMARY, research-brief, PLAN)
- [[planner-search-first-save-later]] — the sibling failure (GH-156): a setup step promised
  outside the intent that needed it; same "state it in the prompt AND the tool description"
  remedy, same root cause class (a written contract nobody corroborated against reality).
- [[supervisor-active-yaml-is-a-pointer]] — prompt bump convention (copy vN → vN+1, point
  active.yaml, never edit prose in active.yaml); followed for concierge v11 → v12 here.
- [[negative-grep-is-not-absence]] — enumerate the active prompts (concierge, supervisor) when a
  routing contract spans more than one prompt file, rather than trusting a single grep.
