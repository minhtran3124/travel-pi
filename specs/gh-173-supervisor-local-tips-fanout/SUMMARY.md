<!--
  Canonical SUMMARY.md shape (templates/SUMMARY.template.md). Header block is machine-read:
  hooks/risk-corroboration.sh greps `Lane:`; the trust-metrics ledger reads Lane/Confidence/Flags.
-->

# gh-173-supervisor-local-tips-fanout — Summary

Lane: normal
Confidence: high
Reason: no manifest hard gate (the surface is a supervisor prompt version, the model-visible `plan` field description, and their pin tests — no auth/authz/schema/route/provider/high-blast path). 2 flags: existing behavior (changes an LLM-decided routing outcome that every turn passes through) and weak proof (prompt compliance is probabilistic; the golden is red 4 of 5 observed runs, not 5 of 5).
Flags: existing behavior, weak proof
Affects: apps/api/app/prompts/supervisor/* (+ app/prompts/active.yaml, app/prompts/CHANGELOG.md), the `plan` field description in apps/api/app/agents/supervisor.py, apps/api/tests/prompts/test_supervisor_prompt.py (new)
Input-type: change request (bug #173, found while measuring the planner path for #147)
Route: normal — branch off `main` → xia2 (Standard) → writing-plans (>2 files) → subagent-driven-development.
Escalate: no — one clear interpretation. The issue states the expected behavior, supervisor v11 §3 already states the rule the agent is dropping, and the fix shape is the one #146/#155/#156 used on this same prompt family.

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> review issue https://github.com/minhtran3124/travel-pi/issues/173 va tim best way to fix it. dam bao ko break workflow cua chatbot hien tai. ko hacky.

Earlier turn that opened this spec:

> hay merge PR hien tai, sau do tiep tuc fix cho issue vua moi open

Issue #173 (verbatim title): "eval: supervisor drops the local-tips fan-out on a full trip-planning request (routing-multi-en-04)". Body: golden `routing-multi-en-04` — "Plan everything for a Tokyo weekend: flights, a hotel, places to see, the weather, **local tips** and a day-by-day plan" — expects `expected_tasks: ["planner", "concierge"]`; the supervisor returns `["planner"]`, so the local-tips step is dropped and the traveller never gets the concierge's travel-knowledge answer. Supervisor v11 §3 explicitly carves that case out; the golden is right and the agent is wrong.

## What changed

Supervisor prompt **v11 → v12**, plus the mirrored schema description. v11 §3 enumerated the
*planner's* tools by name but stated the fan-out exception as a judgment call, so the decidable
half won and "plan everything … local tips …" collapsed to planner-alone. v12 states both halves
in tools: the three concierge-only tools (`get_local_tips`, `get_visa`, `search_travel_knowledge`)
are named as the fan-out trigger, `get_weather`/`search_places` are named as *not* triggers (the
#149 guard), the Routing Examples block gains the contrastive twin of its planner-alone example,
and `## Multi-step Plan` gains the converse of its omit-rule. A second round, after independent
review, closed the same defect class elsewhere in the file: Routing Rule 1 ("Choose **exactly
one** sub-agent") was the prompt's loudest checkable instruction and was unqualified, so it is
now scoped to `target_agent` and points at Rule 3 for the `plan` decision; the `## Multi-step
Plan` intro's judgment-shaped "cannot cover" gate is anchored to Rule 3's tool list; and the
trigger list was reopened ("an ask the primary has no tool for") so the next concierge-only tool
is not silently excluded. `SupervisorIntent.plan`'s
`Field(description=...)` carries the same carve-out. No graph, node, dedupe, HITL, tier-gating or
state change.

Measured effect on the routing capability (k=3): **14/17 → 16/17**, held across both prompt
rounds. `routing-multi-en-04` (#173) went red → green, and `routing-multi-en-01` (#149, the
opposite bug on the same rule) went red → green as a side effect of the weather/places guard.

### Intake findings (2026-09-09, read-only)

**The carve-out exists but is not decidable by the model.** Every other signal points the other way:

- `app/prompts/supervisor/v11.md` §3 enumerates the **planner's** tools by name
  (`search_flights`, `search_hotels`, `search_places`, `get_weather`, routing, `create_trip`,
  `add_itinerary_item`) but states the exception as a judgment call — *"a genuinely INDEPENDENT
  extra a single specialist cannot do itself (e.g. local tips / travel knowledge → concierge)"*.
  The model can check the first half against a list; it can only guess at the second.
- The `## Routing Examples` few-shot block contains *"plan my weekend: flights + a hotel + places
  to see + weather + a day-by-day itinerary" → **planner** alone (`plan=[]`)* — the golden's input
  **minus local tips**. There is **no** fan-out example anywhere, so the nearest neighbour to the
  golden's message answers planner-alone.
- The model-visible description of `SupervisorIntent.plan` (`app/agents/supervisor.py:69-81`)
  repeats *"Omit any step that a single specialist can do itself"* and never mentions the
  carve-out. Per #156, the prompt and the schema description are read independently.
- `## Multi-step Plan` repeats the omit-rule a third time, again without the exception.

**The discriminator is in code and is crisp** (`app/tools/registry.py:38-70`, verified):
planner and concierge overlap on places/weather/climate/routing, but three tools are
**concierge-exclusive** — `get_local_tips` (TIP_TOOLS), `get_visa` (VISA_TOOLS) and
`search_travel_knowledge` (KNOWLEDGE_TOOLS). The planner literally cannot answer a local-tips ask.
That fact is what the prompt is asking the model to infer, and never states.

**Why this must not be fixed by "making fan-out louder":** #149 is the *opposite* bug on the same
decision (`routing-multi-en-01` "flights + weather" fans out when v11 says planner alone). Any edit
that raises general fan-out pressure trades #173 green for #149 redder. `routing-multi-en-03`
(budget + concierge) passes today, so fan-out is not broken — the boundary is.

### Proposed fix direction (not implemented)

Supervisor **v12**, prompt-only — no graph, dedupe, HITL, tier-gating or state change:

1. §3 — keep the one-toolset rule, then replace the judgment-shaped exception with a mechanical
   test naming the concierge-exclusive tools: local tips, visas, and general travel knowledge have
   **no planner tool**, so they are the fan-out trigger; weather and places **do** have one
   (`get_weather`, `search_places`) and stay in-planner.
2. `## Routing Examples` — add the **contrastive pair**: keep the existing "plan my weekend…" →
   planner alone, and put the same sentence **plus local tips** → `target_agent=planner`,
   `plan=["concierge"]` directly beneath it. A contrast teaches the boundary; a second fan-out
   example on its own would only add pressure (the #149 risk).
3. `## Multi-step Plan` — mirror the same exception where the omit-rule is repeated.
4. `SupervisorIntent.plan` field description (`app/agents/supervisor.py`) — mirror it there too,
   since the schema description is read independently of the prompt.
5. Pin the four points with a new `tests/prompts/test_supervisor_prompt.py`, in the shape of
   `tests/prompts/test_planner_prompt.py`.
6. Bump `app/prompts/active.yaml` supervisor 11 → 12 + a `CHANGELOG.md` entry.
7. Measure `python -m eval --suite full --capability routing --repeat 3` before and after. Ship
   gate: `routing-multi-en-04` green **and** `routing-multi-en-01/02` (planner-alone) and
   `routing-multi-en-03` (fan-out) no worse than the pre-change run at the same k.

### Rationale

Lane `normal`: no hard gate, but it changes an LLM-decided routing outcome on the hottest prompt
in the graph, and the proof is probabilistic. Confidence `high`: the expected behavior is stated
by the issue *and* by the prompt itself, and the repair shape is the one the sibling supervisor
fixes (#146/#155/#156) already used.

### Alternatives considered

- **Edit the golden to expect `["planner"]`** — the reading #147 first made and had to retract;
  v11 §3 says the fan-out is correct, so this moves the oracle to match a defect. Rejected.
- **Code-level fan-out** (append `concierge` when the message matches tips/knowledge keywords) —
  deterministic, but hard-codes intent detection that the supervisor exists to do, for one phrasing
  in one language, and would fire on #149's shape too. This is the "hacky" option the user ruled
  out. Kept only as a fallback if the prompt does not hold at k=3.
- **A second fan-out few-shot without the contrast pair** — cheapest, but it is exactly the edit
  that risks flipping #149/`routing-multi-en-01` further red. Rejected in favour of the pair.

### Deviations

- **Process, not code:** Waves 1–3 were implemented directly in the main thread rather than
  dispatched to implementer subagents (`rules/orchestration.md`). The diff is prompt wording whose
  correctness depends on the intake analysis, and parallel subagents on this shared checkout race
  the git index (`docs/solutions/`… `parallel-subagents-shared-git-index-commit-race`). The
  independent-review half of the contract was kept: a separate read-only reviewer ran on the
  staged diff.
- **Rule 3 (auto-fix blocking):** `apps/api/scripts/` is matched by the root `.gitignore`
  (`scripts/`), so the comparison helper SC-8 depends on could not live there. It was placed at
  `apps/api/eval/compare_capability.py`, which is tracked, and PLAN.md's SC-8 row was repointed.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| v12 names the three concierge-only tools as the fan-out trigger | `../../.venv/bin/python -m pytest tests/prompts/test_supervisor_prompt.py -q -k concierge_only_tools` | 0 | | SC-1 |
| v12 keeps weather/places planner-owned (the #149 guard) | `../../.venv/bin/python -m pytest tests/prompts/test_supervisor_prompt.py -q -k planner_owned_not_a_trigger` | 0 | | SC-2 |
| the Routing Examples block carries the contrastive pair | `../../.venv/bin/python -m pytest tests/prompts/test_supervisor_prompt.py -q -k contrastive_pair` | 0 | | SC-3 |
| the `plan` field description carries the same carve-out | `../../.venv/bin/python -m pytest tests/prompts/test_supervisor_prompt.py -q -k plan_field_description` | 0 | | SC-4 |
| the pin actually bites | removed the weather/places bullet from `v12.md`, re-ran the module, restored it | 1 | `test_supervisor_prompt_keeps_planner_owned_not_a_trigger` failed while the rule was absent; 4 passed again after restoring | SC-2 |
| active.yaml resolves to a real, nonempty v12 | `../../.venv/bin/python -m pytest tests/prompts/test_active_versions_load.py tests/api/prompts/test_prompt_registry_helpers.py -q` | 0 | | SC-5 |
| the supervisor's routing/dedupe/HITL topology is unchanged | `../../.venv/bin/python -m pytest tests/agents/test_supervisor_plan_semantics.py tests/agents/test_multi_intent_routing.py tests/agents/test_plan_everything.py tests/agents/test_supervisor.py -q` | 0 | 34 passed, zero edits to those modules | SC-6 |
| `v11.md` was not edited in place | `git diff --exit-code main -- apps/api/app/prompts/supervisor/v11.md` | 0 | | SC-7 |
| routing capability, before the change, k=3 | `../../.venv/bin/python -m eval --suite full --capability routing --repeat 3 --out eval/reports/gh173-before.json` | 0 | 14/17. `multi-en-04` FAIL (got `['planner']`), `multi-en-01` FAIL (got `synthesize`) | |
| routing capability, after the change, k=3 | `../../.venv/bin/python -m eval --suite full --capability routing --repeat 3 --out eval/reports/gh173-after.json` | 0 | 16/17. `multi-en-04` PASS (got `['concierge','planner']`), `multi-en-01` PASS (got `planner`) | |
| no stable golden regressed | `../../.venv/bin/python eval/compare_capability.py eval/reports/gh173-before.json eval/reports/gh173-after.json` | 1 | fixed 3, regressed 1 — the single "regression" is `routing-multi_turn-en-01`, analysed below | SC-8 |
| the one red golden is a pre-existing crash, not a routing regression | `../../.venv/bin/python -m eval --suite full --capability routing --language en --repeat 5 --out eval/reports/gh173-after-en-k5.json` | 0 | 11/12. `multi-en-01/02/03/04` all PASS. `multi_turn-en-01` fails with the **same `SupervisorIntent.plan` ValidationError** recorded against it in the committed `eval/baselines/main.json` | SC-8 |
| routing capability, after the reviewer round, k=3 | `../../.venv/bin/python -m eval --suite full --capability routing --repeat 3 --out eval/reports/gh173-after2.json` | 0 | 16/17 again. `multi-en-01/02/03/04` all PASS; the Rule-1 / Multi-step-intro / open-list edits cost nothing | SC-8 |
| the reviewer round's rewritten pins still bite | deleted the weather/places guard from **both** places in `v12.md`, re-ran the module, restored it | 1 | `test_supervisor_prompt_keeps_planner_owned_not_a_trigger` failed only when the rule was absent from both locations — it correctly stayed green when the rule survived in the other one | SC-2 |
| the contrastive-pair pin still bites | deleted the `**local tips**` example line, re-ran the module, restored it | 1 | `test_supervisor_prompt_has_contrastive_pair` failed | SC-3 |
| the reviewer round did not disturb the workflow | `../../.venv/bin/python -m pytest tests/prompts/test_supervisor_prompt.py tests/agents/test_supervisor_plan_semantics.py -q` | 0 | | SC-6 |
| the BE suite's 59 failures are pre-existing, not caused by this change | ran the 12 failing modules on a temp worktree at `main` and on this branch, then `diff`ed the sorted `FAILED` lists | 0 | 59 failed on both; the two lists are byte-identical. They are dashboard/auth, visa, tips, routing, config and embeddings modules — none touches the supervisor, the prompt registry or the agent graph | |
| ruff clean on the touched Python | `../../.venv/bin/ruff check app/agents/supervisor.py eval/compare_capability.py` | 0 | | |

### Not auto-verified

- **`SC-8`'s compare command exits 1, not 0.** `compare_capability.py` is golden-blind: it reports
  any pass→fail flip as a regression, and `routing-multi_turn-en-01` flipped. The judgement that
  this is *not* a regression from this change is mine, and it rests on two facts a machine did not
  decide: (a) that golden is recorded **FAIL** in the committed `eval/baselines/main.json` with the
  identical `SupervisorIntent.plan` ValidationError, so the before-run's PASS was the outlier;
  (b) the crash — not the `got='journal'` routing miss — is what reproduces: it appeared in the
  k=5 en-only re-measure **and** again in the post-reviewer-round k=3 run. `got='journal'` was
  seen exactly once, in one k=3 run, and never again across two later runs on two different
  prompt revisions. Reached *provenance*; a reader who disagrees should re-run the k=5 command.
- **`routing-multi_turn-vi-01` "fixed" is not claimed.** It crashed in the before run and passed
  after, but it is the same unstable golden — that flip is noise, not evidence for this change.
- **#149 is not closed by this work.** `routing-multi-en-01` went green at k=3 and k=5 here, but
  that issue has its own history of flipping; this SUMMARY claims the measurement, not the fix.
- **Nothing was checked against the live dev agent.** Prompt text is not hot-reloaded
  (`docs/solutions/agent/langgraph-thread-reset-and-prompt-reload.md`); `python -m eval` builds its
  own graph, so the running container still serves v11 until `docker exec api-api-1 touch app/main.py`.
- **The 59 pre-existing suite failures were not diagnosed, only attributed.** The comparison
  proves they predate this branch; it does not say why they fail. Two of my own runs were
  misleading before I got there — the first passed `--timeout=300`, which this pytest has no
  plugin for, so it ran nothing while `tail`'s exit 0 read as a pass; the second truncated 45 of
  the 59 names through `tail -15`. Both are recorded here because the wrong lesson to draw is
  that the suite is green.
- **A separate, unfiled defect was observed:** the model intermittently returns a nested object in
  `plan` (`{'target_agent': 'journal', 'slots': None}`) instead of a specialist literal, crashing
  the turn with a pydantic ValidationError. Seen in the committed baseline and in two runs here.
  Out of scope for #173.

### Rollback

- `git revert <sha>`, or — for an immediate prompt-level revert with no code change — set
  `supervisor: 11` in `apps/api/app/prompts/active.yaml`. `v11.md` is untouched, and the
  `Field(description=...)` addition is inert without the v12 prompt.

### Review

One independent read-only reviewer ran on the Wave 1–2 staged diff (`rules/orchestration.md`
keeps per-task review always-on regardless of lane). Two verdicts:

- **Spec — PASS.** It re-derived the tool-ownership claim itself and added a fact this SUMMARY
  had not checked: none of `journal`/`booking`/`budget` holds the three tools either
  (`app/tools/registry.py:65-71`), so "concierge-only" is literally true, not merely
  "planner lacks them".
- **Quality — PASS on prompt craft, with three findings, all accepted and fixed in Task 5.1**
  (unqualified collapse-to-one instructions elsewhere in the file; a closed trigger list; two
  verbatim-sentence pins). Its two record gaps (an unfilled `### Verify`, an undeclared file in
  PLAN §2) were raised against a snapshot taken before those sections were finalized, and are
  closed here.

The reviewer also flagged the SC-8 exit-1 as gate-red and asked for a re-measure rather than a
silent ship. That re-measure is the k=5 row above, and it is what settled the question.

### Harness-Delta

- backlog → `compound`: two supervisor issues in this family now (#149 fans out when it should
  not, #173 fails to fan out when it should). The durable lesson is a boundary rule, not a
  salience one: **a prompt rule that enumerates one side's tools and leaves the other side to
  judgment will collapse to the enumerated side.** Both halves of a routing boundary must name
  concrete tools, and the few-shot block needs the contrastive pair, not one more example.
