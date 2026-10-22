<!--
  Escalation channel (templates/ESCALATIONS.template.md).
  DENY-ON-NO-RESPONSE: while any `decision:` is `pending`, commits touching this slug are blocked.
-->

# gh-147-dated-hotel-availability-routing — Escalations

Default: **deny-on-no-response**. No recorded decision → work stays blocked.
(Enforced: `hooks/commit-quality-gate.sh` denies commits touching this slug while any `decision:` is `pending`.)

---

## E001

- raised_by: orchestrator (feature-intake)
- date: 2026-09-09
- trigger: ambiguous-direction
- question: When a traveller gives concrete dates and occupancy for a hotel in a
  pure-search conversation, who answers — a widened **concierge** that gains the dated
  `search_hotels` tool, or the **planner** that already owns it, with the supervisor
  re-routing the turn once dates appear?
- context: Issue #147 expects `expected_flow: concierge` **and** `expected_tools: [search_hotels]`,
  but `TOOLS_BY_DOMAIN` binds `search_hotels` to planner/booking only, so the concierge's
  "I can't check real room availability" is truthful about its own toolset. No fix is possible
  without deciding which side of the contract moves. All implementation is blocked on this.
- options:
  - A) **Widen the concierge** — add `HOTEL_AVAILABILITY_TOOLS` (`search_hotels`) to the
    concierge domain and let it answer dated availability without a trip.
    Consequence: smallest diff, golden passes as written, the supervisor prompt (v11) becomes
    truthful. But it erases the deliberate dateless-vs-dated split documented in the
    `browse_hotels` docstring, gives the info agent a booking-adjacent surface, and means two
    agents now own the same tool.
  - B) **Re-route on dates** — keep the concierge dateless; bump the supervisor prompt so a
    hotel request that carries check-in/check-out (or occupancy) goes to the planner, and drop
    the word "availability" from the concierge's routing bullet.
    Consequence: preserves the info/itinerary split and needs no registry change, but is an
    LLM-decided routing rule (weaker proof, prompt-pin test only), touches a hot supervisor
    prompt used by every turn, and the golden must be edited to `expected_flow: planner`
    (an eval-oracle edit + baseline re-run).
  - C) **The golden is wrong** — dateless browsing is the correct answer for a concierge turn;
    fix only the reply so it stops asserting it cannot check availability, and change
    `expected_tools` to `browse_hotels`.
    Consequence: cheapest, but the product keeps refusing to price a fully-specified dated
    stay, which contradicts the issue author's stated expectation. Recorded for completeness.
- default_if_no_response: BLOCK
- decision: **SUPERSEDED by the decision below (2026-09-09, same day).** ~~B — re-route on dates.~~ Keep the concierge dateless. Bump the supervisor prompt so
  a hotel request carrying check-in/check-out (or occupancy) routes to the **planner**, which
  already binds `search_hotels`, and remove "availability" from the concierge routing bullet so
  the prompt stops promising a tool the concierge does not have. The golden
  `hotels-multi_turn-en-01` moves to `expected_flow: planner` (keeping `expected_tools:
  [search_hotels]`), with a baseline re-run. No change to `TOOLS_BY_DOMAIN`.
- decided_by: Minh Tran (user, via intake question)
- decided_at: 2026-09-09


---

## E002 — direction changed to A (bind both hotel tools to concierge)

- raised_by: user (direction change, 2026-09-09)
- date: 2026-09-09
- trigger: system-redefinition (supersedes E001/B)
- decision: **A — the concierge owns hotel SEARCH, dated and dateless.** Bind
  `HOTEL_AVAILABILITY_TOOLS` (`search_hotels`) alongside `HOTEL_SEARCH_TOOLS`
  (`browse_hotels`) to the `concierge` domain. The concierge must **not** gain any
  booking power (`book_hotel` stays out — booking remains the only HITL-gated,
  premium, money-holding domain).
- decided_by: Minh Tran (user)
- decided_at: 2026-09-09
- condition: impact analysis first (delivered below / in SUMMARY "Impact analysis").

### Impact analysis (read-only, 2026-09-09)

**This makes the code agree with two things already shipped:**

1. `app/prompts/supervisor/v11.md` (lines 17, 33–34) already routes hotel lookups —
   naming **availability** explicitly — to the concierge. Today that promise is
   unbacked: the concierge has no dated tool. A closes the contradiction that
   `specs/review-b7-eval-baseline-ci/TRIAGE.md` recorded verbatim ("the prompt
   contradicts itself").
2. The eval dataset already assumes A: **three** goldens pin `expected_flow:
   concierge` + `expected_tools: [search_hotels]` — `hotels-multi_turn-en-01` (#147),
   `hotels-multi_turn-vi-01`, `hotels-happy-en-02`. All three are **failing** in
   `eval/baselines/main.json`. A can fix all three with no golden edit; B would have
   required editing all three oracles.

**What breaks / must change (nothing silently — all of it is in-repo):**

| Surface | Effect |
| --- | --- |
| `app/tools/registry.py` | `concierge` group gains `search_hotels` (15 → 16 tools). One line. |
| `tests/tools/test_tool_registry.py::test_hotel_tool_split` | **FAILS** — asserts `"search_hotels" not in concierge` (MIN-51 guard). Must be rewritten to the new invariant: concierge holds both search tools and **no** `book_hotel`. |
| `app/prompts/concierge/v11.md` §Hotels | Contradicts A in three places (lines 77–90): "do not ask for check-in/check-out, rooms, or guest counts", "not an availability check", "**You do not book, and you do not quote date-specific availability**". Needs a v12 + `active.yaml` + CHANGELOG. |
| `app/prompts/supervisor/v11.md` | No change needed — already says concierge does availability. |
| `tests/agents/test_hotel_search_intent.py` | Still passes (asserts concierge can call `browse_hotels`, and that concierge does not interrupt). Worth extending with a dated-turn case. |
| MCP / `/agent/manifest` | **No change** — `ALL_TOOLS` and `TOOL_METADATA` are unchanged; `search_hotels` was already exposed via planner/booking. No new public tool surface. |
| HITL / money safety | **No regression.** `search_hotels` is `readOnly=True, destructive=False`; it takes no `user_id`/`trip_id` and writes nothing. `book_hotel` stays out of concierge, so `test_planner_never_binds_destructive_tools` and the booking-only interrupt are untouched. Concierge continues not to interrupt — correct, since nothing it can call spends money. |
| Tier gating | **No change.** `search_hotels` was already reachable free-tier through the planner; booking stays the premium domain. |
| Side panel / FE | **No change needed.** `search_hotels` emits the same `kind="hotels"` artifact (`HotelsPanel.from_hotels`, `nights>0`) that the planner already emits today; `AgentActivityTrail.tsx` already maps both tool names to `"hotels"`. Only cosmetic note: a dateless browse and a dated search in one conversation both carry `kind="hotels"`, so they land in the same panel tab (the second replaces the first). |

**The one real risk — and it is a documented, already-observed failure:**

`specs/min-51-hotel-search-intent/PLAN.md` (Status Log, 2026-07-04) records that the
concierge was originally bound to `search_hotels` and it **failed live review**: the
concierge "still asked for check-in/out/rooms/guests before showing hotels — because
its only hotel tool was the availability `search_hotels`". `search_hotels` has six
required arguments with no defaults, and its docstring orders the model to "collect
every one from the traveller and never guess". `browse_hotels` was created precisely
to stop that interrogation. Binding both puts the choice back on the LLM.

Concretely at risk: the four dateless goldens that pass today —
`hotels-happy-vi-01`, `hotels-happy-en-01`, `errors-happy-vi-01`,
`errors-multi_turn-vi-01` (plus `hotels-ambiguous-*`) — all expect `browse_hotels` or
no tool for a turn with no dates. If the model reaches for `search_hotels` and starts
asking for dates, A trades three fixed goldens for up to four broken ones.

**Mitigation (must ship with the binding, not after):** the concierge v12 Hotels
section makes the choice mechanical, not a judgement call —
*no dates in the conversation → `browse_hotels`, and never ask for dates, rooms or
guests to browse; dates already given by the traveller → `search_hotels` with them;
never ask for booking details you were not offered.* Pin that rule with a prompt
content test (the `tests/prompts/` pattern used for planner v13), and re-run the
hotels + errors capabilities in eval before claiming the fix.
