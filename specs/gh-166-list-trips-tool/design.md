# gh-166 — `list_trips` agent tool — Design

Status: approved (user, 2026-09-09; re-approved after 2 independent review rounds)
Lane: high-risk · Confidence: high (`SUMMARY.md`)
Decisions: `ESCALATIONS.md` E001-A, E002-A (superseded), E003-B

## Problem

Asked "how many trips i have?", the agent answers from the single active trip and states it as
the complete set ("You have 1 trip" when the user has 2). It has no tool that can list a user's
trips: `TravelAgentState.trip_id` is one nullable id, `load_context` renders exactly that one id
into `trip_context` as `Active trip: <title> (city: <city>).`, and every trip tool is scoped to
that injected id. `TripService.list_trips()` exists and is served as `GET /trips`, but is not
registered in `app/tools/registry.py`. The model has partial context, no way to fetch the rest,
and no instruction saying the context is partial — so it fills the gap.

## Scope

In scope: a read-only `list_trips` agent tool, a two-part prompt guard, tests, and eval goldens.

Out of scope, by decision:

- **Trip switching / `select_trip`** (E001-A). No mid-turn rebinding of `TravelAgentState.trip_id`.
  "Tell me about my Da Nang trip" is answered by naming the trips and saying which is open;
  pulling a non-active trip's details stays open on #166.
- **MCP exposure** (E003-B). See "MCP surface" below.
- **`TripRepo.list_trips` performance.** It runs `select(models.TripItem)` with no filter — every
  itinerary item of every trip in the database, grouped in Python. Pre-existing; noted, not fixed
  here (`rules/behavior.md` §3).

## Approaches considered

| # | Approach | Verdict |
| --- | --- | --- |
| 1 | Widen `load_context` to inject all trips into `trip_context`; no new tool | Rejected — burns context every turn, still cannot reach a non-active trip's detail, no agent-native parity |
| 2 | Prompt guard only ("never state a trip count") | Rejected alone — stops the confident wrong answer but leaves the question unanswerable. Kept as *part* of 3 |
| 3 | Read-only `list_trips` tool + prompt guard + goldens | **Chosen** — matches E001-A and the issue's suggested fix |

## Components

### 1. The tool — `app/tools/trip_tools.py`

Mirrors `get_trip_summary`: `user_id` via `InjectedState("user_id")`, `session_scope()`,
`AppError → tool_error`, `log_tool_call`. **No explicit `args_schema=`** — one that omits an
injected param breaks `ToolNode` injection; model-facing descriptions go inline via
`Annotated[..., Field(description=...)]` (`docs/solutions/agent/explicit-args-schema-breaks-tool-injection.md`,
and the module docstring already states this).

Signature: `list_trips(user_id: InjectedState | None = None, trip_id: InjectedState | None = None)`
— **both** injected params carry an explicit `= None` default. LangGraph tolerates a missing
`InjectedState` key only when the param has a default (gh-125), and the error table below
presumes `user_id` can arrive as `None`; neither is a required positional.
`trip_id` is read only to mark which entry is the open one — it is never required, so unlike the
other trip tools this one does **not** return `_no_active_trip()` when it is absent: having no
trip open is a normal state for the question "how many trips do I have". `user_id is None` raises
`ToolException`, consistent with the rest of the module.

Returns a compact projection per trip, newest first — **not** `dump(Trip)`:

```
{"trips": [{"title", "city", "start_date", "end_date", "travelers", "items", "is_active"}],
 "count": <int>}
```

- **No `id` field.** E001-A means nothing consumes a trip id, and planner v13 forbids mentioning
  one to the traveller — omitting it removes the hazard rather than guarding it. A future
  `select_trip` would add it back deliberately.
- `items` is the item count, not the items. `TripRepo.list_trips` returns every trip with its full
  item list attached; returning that verbatim would flood the context.
- `is_active` = `trip.id == trip_id`, so the model can say "you have 2 trips; the Phu Quoc one is
  open right now" without seeing an id.
- `count` is returned explicitly so the model reports a number it was given rather than one it
  counted.

### 2. Registration — `app/tools/registry.py`

Append to `TRIP_TOOLS` (in `trip_tools.py`). Planner and journal pick it up automatically; the
`budget` domain filters `TRIP_TOOLS` by an explicit name allowlist, so it is excluded with no
edit. `TOOL_METADATA` derives `readOnly=True` automatically (the name is absent from `_WRITE`).

### 3. MCP surface — `app/mcp/server.py` (E003-B)

`list_trips` is excluded by a **new name check added alongside** the existing
`if meta["destructive"]: continue` metadata check, with a comment pointing at E003. There is no
name list to append to today: destructive tools are skipped on metadata, and `create_trip` is
skipped implicitly by its `tool_call_id` param — this adds the first by-name exclusion.

Why: `build_mcp_server` registers `tool.func`, and FastMCP derives the input schema from the raw
signature — the `InjectedState` annotation is invisible to it, so `user_id` is served as an
ordinary optional string that the caller supplies. The MCP surface is unauthenticated (standalone
`python -m app.mcp.server`, not mounted in `main.py`; `specs/review-a-security-hardening` E004
excluded destructive tools for exactly this reason). Existing read tools share the flaw but also
require guessing a trip UUID; `list_trips` would need only a `user_id`, turning UUID-guessing into
a one-argument inventory dump. Follow-up issue for the class fix (stop serving caller-supplied
`user_id` over MCP at all) is out of scope here.

**`/agent/manifest` is a second surface and is deliberately left exposed.** `SUMMARY.md` flags
`public-contract` for both; E003-B decided only MCP, so the inheritance is stated rather than
assumed. `ALL_TOOLS` also feeds `GET /agent/manifest` (`app/routers/agent.py:739`), which
publishes each tool's *name*, the first line of its description, and its
`readOnly`/`destructive` metadata — a description of the surface, with no execution path and no
`user_id` argument to supply. `list_trips` appearing there is intended.

### 4. Prompt guard — split by which agents hold the tool

Concierge does **not** get `list_trips`. Telling it to call the tool would promise a capability its
toolset cannot execute (`docs/solutions/agent/concierge-hotel-tool-choice.md`). So:

- **Negative half — shared, all sub-agents.** In `system_with_summary` (`app/agents/state.py`), the
  `Current trip context:` label states that this is the single trip currently open, not the
  traveller's list of trips. It is a label change at the point the misleading data is rendered, so
  no prompt file or version bump is involved and every sub-agent sees it.
- **Positive half — only where the tool is bound.** `planner` v14 and `journal` v3 add a rule with
  **two** triggers, because the issue reports two failures:
  1. *Counting* — to answer how many trips / list my trips, call `list_trips`; never count from
     the trip context.
  2. *Naming* — when the traveller refers to a trip that is not the open one ("how about my Da
     Nang chill trip?"), call `list_trips` before proposing anything. If it is already there,
     treat it as an existing trip and talk about it — never offer to draft it as a new idea.
     This is what makes SC-5 reachable without `select_trip`: the agent still cannot pull that
     trip's itinerary (E001-A), but it must stop pretending the trip does not exist. Say which
     trip is open and offer to switch as a next step.
  `app/prompts/active.yaml` is bumped for both — `active.yaml` is a pointer, and editing a `.md`
  without bumping it is a silent no-op
  (`docs/solutions/agent/supervisor-active-yaml-is-a-pointer.md`).

### 5. Routing — deliberately not changed up front

Supervisor v11 has no example for "how many trips do I have". It is not bumped speculatively: the
eval golden is run first — `python -m eval --suite full --capability journal`, which is
deterministic and unpaid — and a supervisor example is added **only if** the run shows the turn
routed to an agent without the tool. Recorded as a conditional task in `PLAN.md`.

## Data flow

```
user: "how many trips i have?"
  → supervisor routes (planner | journal)
  → sub-agent sees "Current trip context: … (one open trip, not the list)"
  → calls list_trips  ── InjectedState user_id, trip_id ──▶ TripService(s, user_id).list_trips()
                                                             └─ repo filters user_id + deleted_at
  ← {"count": 2, "trips": [{title, city, dates, travelers, items, is_active}, …]}
  → reply states the real count and names the trips
```

Ownership boundary is unchanged: `TripService` is constructed with the injected `user_id` and the
repository filters on it, so the tool can only ever return the caller's own trips.

## Error behavior

| Condition | Behavior |
| --- | --- |
| `user_id` missing | `ToolException` — matches every other tool in the module |
| No trips | `{"count": 0, "trips": []}` — a valid answer, not an error |
| No active trip | Normal result; every `is_active` is `False`. Explicitly **not** `_no_active_trip()` |
| `AppError` from the service | `tool_error(e)` — unchanged self-correction path |

## Tests

Unit (`tests/tools/`): multiple trips return the right `count` and order — fixtures set
**distinct explicit `created_at` values**, since "newest first" is `created_at DESC` and rows
created in one transaction can tie; `is_active` marks the
injected `trip_id` and nothing else when `trip_id` is `None`; zero trips; `user_id=None` raises;
another user's trips are never returned; the payload carries no trip `id` and no full item list.

Registry (`tests/tools/test_tool_registry.py`): `list_trips` is bound to planner and journal, not
to budget or concierge; `readOnly` is `True`.

MCP (`tests/mcp/test_mcp_server.py`): `list_trips` is **absent** from `list_tools()` while
`get_trip_summary` is still present.

**Eval — `eval/datasets/journal.json`** (`capability: journal`; that file already mixes
`expected_flow` values, so the capability is the topic label, not the flow). One golden added, one
existing golden updated — *not* two new ones:

- **Added** — `journal-happy-<lang>-NN`, "how many trips do I have?" · `expected_tools:
  ["list_trips"]` · `suite: "full"` · `language: "en"` · `metrics: ["flow_match",
  "tools_expected", "reply_language"]`. Every entry in this file carries an explicit `language`
  field and `reply_language` depends on it.
- **Updated** — `journal-ambiguous-vi-01` ("Cho tôi xem lịch trình chuyến đi Đà Lạt của tôi") is
  the naming case already: it gains `expected_tools: ["list_trips"]`. Adding a second, English
  near-twin would put two correlated cases into the one capability the baseline already lists as
  below threshold. Its existing note stays: this golden is flagged failing in baseline
  (minhtran3124/travel-pi#150), and **this change does not claim to fix #150** — calling
  `list_trips` is now the correct first move, but the traveller asked for an *itinerary*, which
  E001-A still cannot deliver for a non-open trip. The `tools_expected` check becomes meaningful;
  the judged reply may well stay red.

**These goldens prove routing and tool selection, not the number.** The runner hardcodes
`user_id = "eval"` (`eval/adapters/langgraph_runner.py`) and nothing seeds trips for it — this is
the same gap `eval/adapters/db_oracle.py` records as the reason no golden declares a `trip_budget`
oracle_check. A run today returns `count: 0`. Building a seeded-trip eval fixture is a separate
piece of work and is **not** in this scope; each golden carries a `notes` line saying so, matching
the existing trip-less notes in that file. The ≥2-trip assertion (SC-1's answer, not just its
mechanism) is covered by the unit tests above, which control their own data.

`expected_flow` is filled in from the observed route (see §5) rather than guessed. Observing it
does **not** need `make eval-check` (the paid judged suite): `flow_match` and `tools_expected` are
deterministic, so `python -m eval --suite full --capability journal` is enough.

**Baseline impact — the gate reads pass *rate*, not case count.** `evalkit/baseline.py` silently
skips a `golden_id` present in only one report, so a new case cannot trip the gate by counting.
What moves is the **`journal` capability's `pass_rate`**, recomputed over the run — and
`eval/baselines/main.json` already lists `journal` in `capabilities_below_threshold`. That is
where a regression would show up (rule 1, `delta < -tolerance`). Keeping the change to +1 new
golden and reusing the existing naming case is deliberate for this reason. A plan task owns
refreshing the baseline in the same change or accepting the delta explicitly; it is not free.

Task `<verify>` is scoped to the **directories** `tests/tools/` and `tests/mcp/`, never to the
single new test file — a file-scoped verify hides the regressions the change itself causes
(`docs/solutions/` verify-scope learning).

## Success criteria

- SC-1 A user with 2 trips asking "how many trips i have?" gets 2, with both names.
- SC-2 The reply never contains a trip id.
- SC-3 `list_trips` is not served over MCP; the other read tools still are.
- SC-4 A trip belonging to another user is never returned, on any path.
- SC-5 Naming a non-active existing trip is not treated as a brand-new idea: the agent calls
  `list_trips`, acknowledges the trip exists, and does not offer to draft it from scratch.
  Pulling that trip's itinerary detail remains out of scope (E001-A).
