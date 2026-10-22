# gh-166-list-trips-tool — Summary

Lane: high-risk
Confidence: high
Reason: adding an agent tool auto-exposes it over MCP (public-contract hard gate, block mode) and the tool returns a user-scoped trip inventory (authorization); 4 risk flags fired.
Flags: public-contract, authorization, existing-behavior, multi-domain
Affects: apps/api/app/tools/registry.py (agent tool surface, inherited by /agent/manifest + MCP server); planner/journal/budget prompts
Input-type: new spec

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

cho issue https://github.com/minhtran3124/travel-pi/issues/166

GitHub issue #166 — "Agent reports only the active trip when asked how many trips the user has (no list_trips tool)":

> ## Symptom
>
> User has **2 trips** saved in the DB (Phu Quoc + Da Nang chill trip). Asking the chatbot:
>
> > how many trips i have?
>
> gets:
>
> > You have **1 trip** saved right now 🌴
> > It's your **Phu Quoc** trip.
>
> The reply is confidently wrong — it reports the *currently active* trip as if it were the user's whole trip list.
>
> ## Root cause
>
> The agent has **no tool that can list a user's trips**. It answers the question from the only trip it can see: the single active `trip_id` in graph state.
>
> - `TravelAgentState.trip_id` is one nullable id (`apps/api/app/agents/state.py:84`), set from `ChatRequest.trip_id` (whatever trip the FE is on) or by `create_trip`.
> - `load_context` turns exactly that one id into the prompt line `Active trip: <title> (city: <city>).` (`apps/api/app/agents/nodes.py:78-92`).
> - Every trip tool (`get_trip_summary`, `get_trip_budget`, `list_trip_places`, …) is scoped to that injected `trip_id` (`apps/api/app/tools/trip_tools.py`).
> - `TripService.list_trips()` exists (`apps/api/app/services/trip_service.py:116`) and is exposed over REST as `GET /trips` (`apps/api/app/routers/trips.py:91`) — but it is **not** registered as an agent tool (`apps/api/app/tools/registry.py` has no `list_trips`).
>
> So the model has one trip in context, no way to fetch the rest, and no instruction telling it that its trip context is partial → it fills the gap and asserts a count.
>
> Related to the agent-native-parity principle: a user can list their trips in the UI; the agent cannot.
>
> ## Repro
>
> 1. Log in as a user with ≥2 trips.
> 2. Open the chatbot from any trip (or from a page with an active trip).
> 3. Ask "how many trips i have?" / "list my trips".
> 4. It answers with the active trip only, stated as the complete set.
>
> ## Expected
>
> - "how many trips i have?" → the real count, with the trip names.
> - Trips other than the active one can be referenced by name ("How about Da Nang chill trip?" should resolve to the existing Da Nang trip, not be treated as a brand-new idea — see screenshot 1, where it offers to *draft* a Da Nang plan the user already has).
>
> ## Suggested fix (not implemented)
>
> 1. Add a `list_trips` agent tool wrapping `TripService.list_trips()` with `user_id` via `InjectedState` (mirror `get_trip_summary`), read-only, registered in `registry.py` for the planner/trip-capable sub-agents (and consequently MCP).
> 2. Return a compact list (id, title, city, dates, status) so the model can both count and disambiguate.
> 3. Let a trip named in conversation switch/target the active trip — decide whether `list_trips` alone is enough or a `select_trip` / trip-resolution step is needed so `get_trip_summary` can be called for a non-active trip.
> 4. Prompt guard: never state a trip count/list from `trip_context` — `Active trip: …` is one trip, not the inventory. Call `list_trips` first.
> 5. Eval goldens: "how many trips do I have" (2+ trips) and "tell me about my <other trip>".
>
> ## Notes
>
> - Not a data bug — both trips are in the DB and `GET /trips` returns them.
> - Anything MCP-exposed inherits the same tool set, so the fix lands there too.

## What changed

The agent gains a read-only `list_trips` tool over the already-owner-scoped
`TripService.list_trips()`, bound to planner and journal, withheld from the MCP surface, and
backed by a two-trigger prompt rule so the model reaches for it instead of counting from the one
trip in its context. The shared trip-context label now says it is one open trip, not the list.

### Rationale

Lane is `high-risk` on two independent grounds. (1) A new entry in `TOOLS_BY_DOMAIN` is not a
private helper: `ALL_TOOLS` feeds `/agent/manifest` and the MCP server, so the tool ships as a
client-visible contract the moment it is registered — the manifest's block-mode `public-contract`
gate. (2) The tool returns the caller's whole trip inventory, so its `user_id` scoping is an
authorization surface: a wrong or missing `InjectedState` binding leaks other users' trips
(the class of bug #118 and #125 already hit in this same tool layer).

Confidence is `medium`, not `high`, because the issue leaves suggestion 3 explicitly undecided —
whether `list_trips` alone closes the bug, or whether a `select_trip` / trip-resolution step is
also needed so `get_trip_summary` can target a non-active trip. Those are materially different
scopes (read-only vs. a state-mutating trip switch touching `TravelAgentState.trip_id`). A safe
default exists (ship read-only `list_trips` + prompt guard + goldens; defer trip switching), which
kept this at `medium` rather than `low` — and `medium` on a high-risk task escalated per
`rules/orchestration.md`. **Resolved 2026-09-09:** the user chose option A on both escalations
(`ESCALATIONS.md` E001, E002), leaving one interpretation, so confidence is now `high`. Lane stays
`high-risk`. **Superseded the same day by E003:** E002-A's condition was unsatisfiable — over MCP
`user_id` IS a caller-supplied argument (FastMCP builds the served schema from the raw signature,
so `InjectedState` is invisible to it; verified by dumping `get_trip_summary`'s `inputSchema`), and
that surface is unauthenticated. `list_trips` would have needed only a `user_id` to dump a user's
inventory. E003-B therefore excludes it from MCP by name, with a test asserting its absence. The
`public-contract` gate is now authorized for the narrower surface it still ships on:
`GET /agent/manifest`, which publishes tool names and readOnly/destructive metadata only. The lane
stays `high-risk` on authorization grounds regardless.

### Alternatives considered

- **Widen `load_context` to inject every trip into the prompt instead of adding a tool** — no new
  tool surface, but it burns context on every turn, still cannot fetch details for a non-active
  trip, and leaves the agent without the parity the issue asks for. Rejected as the primary path;
  worth re-examining in `brainstorming`.
- **Prompt guard only ("never state a trip count")** — stops the confident wrong answer but leaves
  the question unanswerable. Insufficient alone; keep it as part of the fix, not instead of it.

### Deviations

- **Rule 3 (task 1.2)** — the diff carries an incidental `ruff format` reflow of the unrelated
  `language:` annotation in `state.py`. Pre-existing format violation, zero behavior change; the
  implementer's report understated it as "none" and the reviewer caught it.
- **Rule 3 (task 1.1)** — `ruff format` run on `trip_tools.py` after the insertion left a
  three-blank-line gap. Formatting only, confined to the task's own file.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| Intake evidence schema | `python .claude/scripts/verify_summary.py --lane gh-166-list-trips-tool` | 0 | run at intake handoff | |
| Issue root cause: no `list_trips` agent tool | `grep -rn "list_trips" apps/api/app` | 0 | at intake, hits were routers/repositories/services only — none under `app/tools/` | |
| Tool returns the real count and names | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_list_trips.py -q` | 0 | 9 passed | SC-1 |
| Payload carries no trip id, items is a count | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_list_trips.py -q -k projection` | 0 | 1 passed, 8 deselected | SC-2 |
| `list_trips` absent from the MCP surface | `cd apps/api && ../../.venv/bin/python -m pytest tests/mcp/test_mcp_server.py -q` | 0 | 7 passed; re-run 3x after a reviewer's mutation probe transiently reddened it | SC-3 |
| Owner scoping and missing user_id | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_list_trips.py -q -k owner` | 0 | 2 passed, 7 deselected | SC-4 |
| Domain bindings and readOnly metadata | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_tool_registry.py -q` | 0 | 59 passed | SC-5 |
| active.yaml resolves to the prompts carrying the rule | `cd apps/api && ../../.venv/bin/python scripts/check_gh166_prompt_wiring.py` | 0 | planner v14, journal v3 | SC-6 |
| Tool output is JSON-serializable | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_list_trips.py -q -k json` | 0 | 1 passed, 8 deselected | SC-7 |
| Shared trip-context label | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_state_system_prompt.py -q` | 0 | 16 passed | SC-9 |
| Goldens load, updated golden declares tools_expected | `cd apps/api && ../../.venv/bin/python -m pytest tests/eval -q` | 0 | 160 passed; dataset count constant 102 to 103 | SC-8 |
| Observed route pinned on the counting golden | `cd apps/api && ../../.venv/bin/python scripts/check_gh166_golden_flow.py` | 0 | expected_flow=planner, a member of ALL_SUBAGENTS | SC-10 |
| Baseline decision recorded | `cd apps/api && ../../.venv/bin/python scripts/check_gh166_baseline_note.py` | 0 | negative control: exits 1 before the note is written | SC-11 |
| Lint | `cd apps/api && ../../.venv/bin/ruff check app scripts` | 0 | all checks passed | |

The **full** backend suite at HEAD reports 2309 passed / 57 failed. Those 57 are environmental,
not this branch: a worktree needs a real `apps/api/.env` to run, and its presence breaks the tests
that assert a *missing* key (`test_llm_defaults_require_no_key`, `test_get_embeddings_fake_without_key`)
plus the dashboard basic-auth suites. Proven rather than assumed — the same subset was run at the
merge base `20f3c79` in a throwaway worktree with the identical `.env`, and the failing test ids
are byte-identical to HEAD's (`diff` empty, 57 = 57). CI has no `.env`, so they do not appear there.

Beyond the rows above, the affected directories were swept as a whole —
`pytest tests/tools tests/mcp tests/agents tests/eval tests/prompts -q` — twice: 908 passed on the
clean baseline before any change, 925 passed at HEAD. It is cited here rather than added as a
Verify row because it runs ~75s, and `rules/plan-format.md` bars a whole-suite row (the 60s limit
exists so the gate can re-run every row; this one timed it out, which is how the violation was
found). The full suite runs at branch finish and in CI.

Baseline decision: **accepted**, not refreshed — pinned `journal` pass_rate 0.500, run on this branch 0.333.
Those two numbers are NOT comparable and the second must not overwrite the first: different
provider, EN-only, `repeat: 1`. Reasoning under Not auto-verified.

### Not auto-verified

- **The agent's actual reply to "how many trips do I have?"** — reached *truth* for the mechanism,
  not for the answer. A real run on this branch (isolated `gh166` stack) shows the agent calling
  `list_trips` on its own and routing to `planner`: `tools_expected` passed. The *count* it states
  is still unproven end-to-end, because the runner hardcodes `user_id = "eval"` and nothing seeds
  trips for it, so the tool honestly returns 0. The count is covered by unit tests instead, which
  control their own data. Closing this gap needs a seeded-trip eval fixture — a separate piece of
  work that `eval/adapters/db_oracle.py` already records as missing.
- **The two prompt rules changing model behavior** — reached traceability only. SC-6 proves
  `active.yaml` resolves to the files carrying the rule; no deterministic check can prove the
  model obeys it. The observed run is one sample, at `repeat: 1`.
- **Baseline comparability — the reason the delta was accepted rather than refreshed.** The run
  could not be like-for-like: the branch's seeded provider (`clinepass`) returned 401
  ("re-authenticate your Cline account"), so all 5 goldens errored and nothing was observed. The
  isolated stack's `agent_config` rows were repointed to `openai` / `gpt-5-mini` — a change
  confined to a throwaway container's database, touching neither the repo nor the dev stack — to
  get any observation at all. That run was also EN-only (`--language en`, 3 cases) at `repeat: 1`,
  against a baseline captured over the full suite at `repeat: 3`. Overwriting a whole-suite
  baseline from that would destroy it.
- **The pinned `expected_flow: planner` was observed under supervisor v11.** Merging `main`
  brought in gh-173's **supervisor v12**, which rewrites the fan-out rule. Reading v12, the
  trigger is narrow and tool-keyed — a fan-out needs the message to ask for a concierge-only tool
  (`get_local_tips`, `get_visa`, `search_travel_knowledge`), and `target_agent` stays a single
  specialist — so "how many trips do I have?" should still land on `planner`. That is reasoning
  about a prompt, not an observation, and this SUMMARY says elsewhere that such claims are not
  deterministically checkable. The golden was **not** re-run after the merge. It folds into the
  like-for-like run already wanted below.
- **Whether this change affects the two other journal failures.** In the same run
  `journal-ambiguous-en-01` failed `reply_language` (replied vi to an en prompt) and
  `journal-multi_turn-en-01` failed `format_quality` (0.3). Neither is a golden this work
  authored. `ambiguous-en-01` routed to `concierge`, whose prompt is untouched, so this change
  cannot plausibly explain it. `multi_turn-en-01` routed to `planner`, whose prompt **was**
  changed — so it cannot be cleared either. Under a provider swap, neither can be attributed.
  **A like-for-like judged run should be done once Cline auth is restored, before merge.**
- The lane's `public-contract` claim — reached traceability (registry → `ALL_TOOLS` → the manifest
  is read from source); `hooks/risk-corroboration.sh` scored the real diff at commit time.

### Advisory Findings

Independent correctness review (six find angles, 8 candidate locations, independent scorer per
location on a different model). **No finding reached the blocking threshold.** Two were defects in
this work's own success-criteria checks and were fixed rather than recorded; the rest stand.

**Fixed in `a67a362`:**

- `check_gh166_golden_flow.py` asserted the observed flow against `TOOLS_BY_DOMAIN`'s keys, and
  its docstring claimed there was "no enum to read". Both wrong: `ALL_SUBAGENTS`
  (`app/agents/constants.py`) calls itself the single source of truth, and the multi-intent
  fan-out path sets `current_flow` to `SYNTHESIZE_NODE`, which the eval runner copies into the
  very field `expected_flow` is compared against. A future honest observation of `synthesize`
  would have been rejected as "not a sub-agent the supervisor can route to". Now derived from
  `ALL_SUBAGENTS` + `SYNTHESIZE_NODE`. In fairness the practical gap was narrow: `TOOLS_BY_DOMAIN`'s
  keys happen to be exactly the five sub-agent names, so `synthesize` was the only value the old
  check would have wrongly rejected. The false docstring claim was the worse half.
- `check_gh166_baseline_note.py`'s decision regex had no word boundary and no `IGNORECASE`:
  `Baseline decision: acceptedly unresolved — 0.5 and 0.3` PASSED as "accepted", and a naturally
  capitalised `Accepted` FAILED a correctly recorded decision — the same wrong-branch class the
  script's own comment calls "worse than no check". Both probes re-run after the fix: the first
  no longer matches, the second does.

**Recorded, not fixed:**

- `list_trips` is uncapped while the REST equivalent (`GET /trips`) paginates the same service
  call, and the payload persists as ToolMessage content in the checkpoint for the rest of the
  thread. An account with hundreds of trips costs tokens, not correctness. Seven scalar fields per
  entry keeps it modest; capping belongs with the pagination question, not here.
- `check_gh166_prompt_wiring.py` tests for the bare substring `list_trips`, so a future prompt
  mentioning the tool only in a negation would still pass. Correct on this branch — both prompt
  diffs are pure appends carrying the real two-trigger rule.
- The MCP exclusion is name-keyed and its test asserts absence by the same name, so a rename would
  re-expose the tool with both passing vacuously. No wrong behavior today.
- `TripRepo.list_trips` runs `select(models.TripItem)` with no filter — every itinerary item of
  every user, bucketed in Python. Pre-existing (that file has zero diff on this branch), but this
  change newly wires an LLM-triggered, per-utterance caller into it. Worth fixing when someone
  next touches that file.

Clean on the areas flagged for scrutiny: owner scoping (no IDOR path), the `trip_id is None`
branch, the `dump()` projection against null city/dates/no items, MCP reachability (the exclusion
is checked unconditionally before the only `add_tool` call site), and the shared label (every
consumer uses substring/split, none exact equality).

### Intent Findings

Independent plan-blind review against issue #166 verbatim. Verdict PASS; three items recorded.

- **Drift (accepted, equivalent-or-better).** Suggestion 2 asked for `(id, title, city, dates,
  status)`. Shipped: `title, city, start_date, end_date, travelers, items, is_active`. `id` is
  dropped deliberately — under E001-A nothing can consume it and the planner prompt forbids
  showing one. `status` does not exist on the `Trip` schema at all (only `TripItem` has one);
  `is_active` serves the stated purpose ("count and disambiguate") instead. `travelers` and the
  `items` count are additive.
- **Gap (deferred, not fixed).** Suggestion 5 asked for a golden with 2+ trips. The golden ships,
  but the runner hardcodes `user_id = "eval"` with no seeded trips, so it proves routing and tool
  selection, not the count. Unit tests cover the count. Closing it needs a seeded-trip eval
  fixture — separate work, already recorded above and in `eval/adapters/db_oracle.py`.
- **Excess (kept, with a follow-up).** Three permanent slug-named scripts under
  `apps/api/scripts/` that the issue did not ask for. They exist because SC-6, SC-10 and SC-11
  must stay re-runnable. `check_gh166_baseline_note.py` in particular asserts on the *text* of
  this SUMMARY, so a permanent check is coupled to a spec document that will outlive the spec.
  Worth folding into `tests/` or deleting after merge; not removed here because that would leave
  three success criteria unverifiable.

**Residual risk the reviewer named and this work does not close:** the naming trigger lives only
in the planner and journal prompts. A "what about my Da Nang trip" utterance that the supervisor
routes to `concierge` is defended only by the shared trip-context label, since concierge binds no
trip tools. It also holds no `create_trip`, so it cannot open a duplicate trip — the failure mode
there is a vaguer answer, not the original bug.

### Rollback

- `git revert b2c6c30 a67a362 f5f097d 15d5b07 28bb989 027cb67 6747754 9ff37a4 92227be 8ed14d9`
  — newest first, because `a67a362` edits scripts that `15d5b07` and `f5f097d` add; reverting the
  older commits first would conflict on those two files. Every commit is additive and reversible. No migration, no schema change, no data written, no external state.
- The prompt bump reverts with the rest: `active.yaml` returns to `planner: 13` / `journal: 2`,
  and v14 / v3 become unreferenced files rather than needing deletion.
- The isolated eval stack is separate from anything shipped: `docker compose -p gh166 down -v`.

### Harness-Delta

- **backlog → compound.** `hooks/commit-quality-gate.sh` resolves `REPO_DIR` from
  `CLAUDE_PROJECT_DIR` (line 26) and `cd`s there (line 33), so a commit from any linked worktree
  audits the **main checkout's** index instead of its own. A half-staged spec in the main checkout
  blocked commits from every worktree in the repo, and no agent-side workaround exists: the gate
  is a PreToolUse hook, so an inline `CLAUDE_PROJECT_DIR=` prefix on the `git commit` line never
  reaches it. The fallback on line 26 is already correct — it is the env var winning over
  `--show-toplevel` that breaks the worktree case. Peer session `travel-pi-0e` is writing the
  record.
- **backlog.** Root `.gitignore:31` is a bare `scripts/`, which also matches
  `apps/api/scripts/`. New helper scripts there are silently skipped by `git add`; the three
  `check_gh166_*.py` files only landed via `git add -f`, as the seven pre-existing tracked files
  in that directory presumably did. Narrowing the pattern to `/scripts/` belongs in its own change.
- **backlog.** A reviewer subagent ran a mutation probe (deleting a block, running tests,
  restoring) in the shared worktree while the controller was running its own verification. The
  controller's `tests/mcp` run caught the mutated window and reported a false failure. Review
  isolation needs either a scratch copy or a lock; reviewers were told to avoid in-place mutation
  only after the fact.
