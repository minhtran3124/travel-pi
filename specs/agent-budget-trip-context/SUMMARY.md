# agent-budget-trip-context — Summary

Lane: normal
Confidence: medium
Reason: 3 flags (existing behavior, multi-domain, weak proof); no manifest hard gate — new agent tools are auto-exposed over MCP (registry-driven), so re-run risk-corroboration on the diff and escalate to high-risk if it trips public-contract.
Flags: existing-behavior, multi-domain, weak-proof
Affects: app/tools/registry.py (budget domain binding), app/tools/trip_tools.py, app/prompts/budget (new version), MCP tool surface (additive)
Input-type: change request
Route: using-git-worktrees → writing-plans (>3 steps, >2 files) → subagent-driven-development
Escalate: no (medium confidence on a normal lane; default direction documented below — user confirms before planning)

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

thinking and planning for use case
```
user: asking about trip budget
bot: answer with call tool for trip budget
user: pls set simple budget for trip
bot: I can do that, but I'm still missing one detail: how many days is your trip?
```

i think bot can fetch the trip meaning it knows for total days of trip, is that correct? If not, we should provide ability for chatbot can get/fetch this info and make the simple budget?

## What changed

(intake only — nothing implemented yet)

### Findings at intake (why the bot asks for days)

- The **budget** sub-agent is bound to `EXPENSE_TOOLS + get_trip_budget` only
  (`app/tools/registry.py:59`). `get_trip_budget` returns caps/spent/remaining — **no dates, no day count**.
- `get_trip_summary` (returns `start_date`, `end_date`, day-indexed items) is bound to **planner** and
  **journal** only. So the budget agent literally cannot see how long the trip is.
- There is **no agent tool that sets a budget**. `TripService.set_trip_budget` exists but is exposed only
  as `POST /trips/{id}/budget` (REST). "Pls set simple budget" is therefore un-actionable for the agent;
  the model improvises (asks for days to compute a per-day figure itself), which also collides with the
  budget prompt guardrail "Don't estimate totals".
- `estimate_trip` (`POST /trips/estimate`, pure calc from nights × travelers × rates) exists but is also
  **not** an agent tool.
- Trip has `start_date`/`end_date` (nullable) and `travelers`; day count is derivable when dates are set.

### Rationale

Default direction (medium confidence — confirm before planning):
1. Bind `get_trip_summary` into the **budget** domain so trip dates/travelers are readable.
2. Add a `set_trip_budget` agent tool (write, wraps `TripService.set_trip_budget`, `_WRITE` annotation).
3. Add an `estimate_trip_budget` agent tool wrapping the existing pure `estimate_trip`, so "simple budget"
   = nights (from trip dates) × travelers × default rates → propose per-category caps → set on confirm.
4. Budget prompt v3: "load the trip first; only ask for days when the trip has no dates".
5. Eval golden for the 2-turn flow above.

### Alternatives considered

- Only (1) — stops the wrong question but "set budget" still cannot be fulfilled.
- Route "set budget" to planner (already has TRIP_TOOLS) — still lacks a set-caps tool; splits the budget domain.
- "Simple budget" = single total cap — `TripBudgetSet` has no total field; would need a schema change (data-model flag).

### Deviations

- Rule 1 — Task 1.2: `tests/api/prompts/test_prompt_registry_helpers.py::test_versions_returns_sorted_ints` pinned `registry.versions("budget") == [1, 2]` and broke on the v3 bump; Files set extended by controller, assertion changed to sorted ints with `[1, 2]` prefix. Commit `9714e88`.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| intake evidence | `grep -n '"budget"' apps/api/app/tools/registry.py` | 0 | budget domain = EXPENSE_TOOLS + get_trip_budget only | |
| intake evidence | `grep -rn "set_trip_budget\|estimate_trip" apps/api/app/tools/` | 1 | no agent tool wraps either service method | |

### Not auto-verified

- The chat transcript's exact cause (model improvising per-day math) — reached traceability; not re-run because no live agent thread was replayed.

### Rollback

- n/a (no code change yet)

### Harness-Delta

- none
