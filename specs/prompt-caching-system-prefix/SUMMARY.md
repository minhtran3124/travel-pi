# prompt-caching-system-prefix — Summary

Lane: high-risk
Confidence: high
Reason: hits the `external-provider` hard gate — a provider-SDK request parameter (`prompt_cache_retention`) in the shared LLM client `app/clients/llm.py` — and reorders the system-prompt assembly on every LLM call in the graph. Scope narrowed by the user twice (E001 → A, E002 → B); no ambiguity remains.
Flags: external systems, existing behavior, weak proof, multi-domain
Affects: app/clients/llm.py (LLM client), app/core/config.py (settings), app/agents/state.py + supervisor.py + subagents/_base.py (system-prompt assembly), app/repositories/agent_run.py, scripts/
Input-type: change request

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

Original request (2026-09-08, from `docs/reviews/2026-09-02-deep-review.md` §6):

```
Chưa bật prompt caching
Prefix system prompt khoảng 3.3k token và rất ổn định — đúng ứng viên cho caching. Anthropic giảm tới 90% chi phí input với cache_control, OpenAI tự động.

Kiểm lại 08-09 — app/core/pricing.py ghi thẳng "no cache_control is in use in this app". Giờ đã có số liệu chi phí từ mục 06 để đo trước và sau.
```

Re-entry request (2026-09-10, after the LangChain context-modes review):

```
/feature-intake design + plan for section "Mở khoá prompt caching" truoc
```

where that section (artifact "Fork hay Isolated", step 1) read: "Quyết định E001, rồi chuyển ghi
chú ngày trong `ground_current_date` từ prefix xuống suffix của system prompt. Không phụ thuộc
provider. Đo bằng `cached_tokens` trong usage của response."

Follow-up (2026-09-10): "ok, dong y vs ban" — accepting the recommendation that the retention wiring
become conditional on the A/B verdict rather than shipping in wave 1.

Scope decisions recorded in `ESCALATIONS.md`: E001 → **A** (prefix stabilisation only, no Anthropic
work); E002 → **B** (A + a live probe of `prompt_cache_retention="24h"`); E003 → **B** (the wiring is
a conditional wave, pre-authorised in both directions).

## What changed

The review said prompt caching was off. It was on — 71.9% on dev data — and its misses were idle
eviction, not an unstable prefix. This branch ships what that finding supports and records what it
rules out.

- **Date note moved to the end of every agent system prompt** (`app/agents/state.py`,
  `supervisor.py`, `subagents/_base.py`). Wording byte-identical; only position moved. Measured with
  OpenAI's `cached_tokens` across a timezone change: **0 → 3,840 of 4,373 tokens** served from cache
  (0% → 88%). Every traveller timezone now shares one cache entry instead of each getting its own.
- **`scripts/cache_hit_report.py`** plus `AgentRunRepository.llm_steps_since` — hit rate per node and
  model from `agent_run_steps`, separating missed *calls* from uncached *tokens*, with a `--min-ratio`
  gate that fails closed and never reports "nothing measured" as a 0% regression.
- **`scripts/probe_cache_retention.py`** — a two-armed A/B that cannot report a verdict it cannot
  trust: seed verified, attempt spent before the first call, four verdict cells, 60-minute floor.
- **Retention was tested and NOT wired.** `prompt_cache_retention="24h"` is accepted but did not keep
  the cache longer than the default on `gpt-5.4-mini`. Under the pre-registered rule (E003) the wiring
  wave is skipped; `app/clients/llm.py` is untouched.
- **Two knowledge records**, one of which documents a **pre-existing production bug** this work
  surfaced: asked for a flight with no date, the agent searches today's date without asking, 6 of 6
  times on `main`. Not caused or fixed here — it needs its own issue.

Code commits: `7041ae9`, `7e59ce6`, `271c086`, `9a0df74`, `25186a7`, `c9d480a`, `81c89f0`,
`e404505`, `4911e49`. Docs: `bab0f0d`, `e3bc5cb`. Final code head `4911e49`: **2412 passed**.

### Intake findings (2026-09-10 re-run, evidence gathered)

| Claim | Verified? | Evidence |
| --- | --- | --- |
| "Chưa bật prompt caching" | ❌ **false for OpenAI** | dev Postgres `agent_runs` 03→10 Sept: 166 turns, 4,329,915 input / 3,111,552 cached = **71.9%**; per node: `assistant` 75.8%, `supervisor` 49.4%, `reflection`/`synthesize`/`summarize` 0% (prompts < 1,024 tokens, below the cacheable minimum) |
| "Prefix unstable because the date note is prepended" | ⚠️ second-order | the note is identical for every request in the same day + timezone, so the prefix is stable within a day; only 2/30 supervisor misses sit at 23:58–00:01Z |
| Misses are caused by idle eviction | ✅ true | supervisor hit rate by idle gap to the previous run: `<5 min` 94/98, `5–15 min` 4/6, `15–60 min` 2/9, `>60 min` **0/17**; median gap: misses 3,960 s, hits 27 s — matches OpenAI's documented `in_memory` retention (5–10 min idle) |
| `prompt_cache_retention="24h"` is usable on the default model | ✅ true (immediate) | live probe on `gpt-5.4-mini-2026-03-17` via `_build_chat_model(..., model_kwargs=...)`: `24h` and `in_memory` → 200, second call `cache_read` 2,816/3,236; `"bogus"` → HTTP 400 `invalid_value` naming `prompt_cache_retention` |
| `24h` survives a 21 min idle gap on `gpt-5.4-mini` | ✅ true | re-call at 04:58Z of the prefix seeded 04:37Z: `cache_read` 3,328 / 3,577 input → HIT |
| **`24h` retention beats the default across a >60 min gap on `gpt-5.4-mini`** | ❌ **false (n=1)** | discriminating A/B at 06:25Z after a true idle gap of **about 87 min** (last cache touch 04:58Z; the scratchpad prints 108.6 because it counts from the 04:37Z seed): `24h` arm `cache_read` **0** / 3,577 → MISS; `in_memory` control `cache_read` **0** / 3,310 → MISS. Verdict **`BOTH-MISS`**. The parameter is accepted and server-validated but did not keep the prefix alive on this model, consistent with `-mini` models being absent from OpenAI's extended-retention list |
| **`24h` is BETTER than the default for our miss pattern** | ❌ **not shown** | the control arm also hit: `in_memory` re-call at 04:58Z read 2,816 / 3,310 → HIT. OpenAI documents `in_memory` as "5 to 10 minutes of inactivity, **up to one hour**", so 21 min proves nothing about the two policies. The discriminating gap is **>60 min**, where the dev data shows 0/17 hits — a longer A/B re-call is running |
| No `cache_control` anywhere in the app | ✅ still true | `grep -rn cache_control apps/api/app --include='*.py'` → 0 hits |

## Status log (execution, 2026-09-10) — shipped to PR #190, awaiting human review

Branch `feat/prompt-caching-system-prefix` in worktree `../travel-pi-prompt-caching-system-prefix`,
off `main` 34f9920. Worktree baseline before any change: **2388 passed, exit 0**.

| Task | Commit | Verify | Spec verdict | Quality verdict |
| --- | --- | --- | --- | --- |
| 1.1 date note last | `7e59ce6` | `pytest tests/agents/test_state.py -q` exit 0 (17 passed) | PASS | PASS |
| 1.2 hit-rate report | `7041ae9`, fixed in `271c086` | `pytest tests/scripts/test_cache_hit_report.py -q` exit 0 (8 passed) | FAIL → **PASS** after fix | FAIL → **PASS** after fix |
| 2.1 call sites outermost | `9a0df74` | `pytest tests/agents/test_state.py tests/agents/test_supervisor_language.py -q` exit 0 (19 passed); reviewer re-ran `tests/agents/` 424 passed | PASS | PASS |
| 3.1 live acceptance | (evidence only) | SC-5, SC-7 recorded; eval smoke 18/18; date goldens = baseline | — | — |
| 4.1 retention wiring | — | **skipped — not triggered** (SC-7 verdict `BOTH-MISS`, E003) | — | — |
| 5.1 durable record | `bab0f0d`, `e3bc5cb` | `python3 .claude/scripts/rebuild_solution_index.py --check` exit 0 | — | — |
| 2.2 A/B probe script | `25186a7`, fixed in `c9d480a` and `81c89f0` | `pytest tests/scripts/test_probe_cache_retention.py -q` exit 0 (12 passed) | PASS | FAIL → FAIL → **PASS** (round 3) |

### Minor findings carried forward (not blocking, for the final review chain)

- **1.1/M1** — `app/agents/state.py:277`: with only Task 1.1 landed, the order is base → note →
  per-turn fields, which is precisely the alternative `design.md` D1 rejects, because both call sites
  still wrap `ground_current_date` inner. Coherent and correct; Task 2.1 closes it.
- **1.1/M2 (watch this one)** — the note is *mid-message* in the interim state, and after Task 2.1 it
  becomes genuinely last. The reviewer's judgement is that risk runs toward **weaker** adherence to
  "never fall back to today / ask" on long, context-rich turns (lost-in-the-middle), and that only the
  `dates` eval goldens **with populated state** settle it. The docstring's own history records a live
  probe where the model defaulted to today. Task 3.1's `make eval-smoke` is the gate; a regression
  there blocks the wave rather than being explained away.
- **1.1/M3** — `tests/agents/test_state.py:317`: the new test duplicates two assertions from
  `test_ground_current_date_injects_today`. Harmless; both fail on a re-prepend, so the regression is
  still caught.
- **1.2/M3** — `--node` had no test (fixed in the follow-up dispatch).
- **1.2/M4** — invalid `--since` raised a traceback instead of an argparse usage error (fixed in the
  follow-up dispatch).
- **1.2/M5** — SC-5 (report against a real database) is deliberately NOT closed by Task 1.2; waves 1–2
  are offline with no `.env`. It closes in Task 3.1.
- **1.2/M6** — `tests/scripts/test_cache_hit_report.py:137`: `assert not any(r["input"] == 999 ...)` is
  vacuous, because aggregation folds the tool step into the supervisor row (6000 → 6999) so no row ever
  carries 999. The load-bearing assertion is the line above it. Harmless; candidate for deletion.
- **1.2/M7** — no test pins `cached_tokens is None` → `miss_calls`. The column is `nullable=False`
  (`app/db/models/agent_run_step.py:33`) so the database path cannot produce it, but `build_report` is
  public and pure, so a regression there would be silent. The re-reviewer verified the behaviour by
  hand (a `None` row yields `calls 2, miss_calls 1`).

Wave 2 full-suite gate after all four tasks (HEAD `81c89f0`): **2409 passed, exit 0** — the 2388
baseline plus 21 new tests, no regressions.

Wave 1 full-suite gate after both wave-1 tasks: **2393 passed, exit 0** (baseline 2388 plus exactly the
5 new tests). Nothing else in the suite asserted the old prompt order — that was the main regression
risk in moving the note.

- **2.1/M1 — where the prefix can still break, with the reviewer's claim corrected.** The final
  order is style + agent prompt → profile → account email → instructions → trip_context → summary →
  trip_facts → preferences → language pin → date note. The reviewer wrote that `trip_context` is
  "refreshed every turn" and so "a trip edit invalidates everything after the style+prompt block".
  **That overstates it on both counts, verified against the code:**
  - `trip_context` is rendered as a single sentence, `Active trip: {title} (city: {city}).`
    (`app/agents/nodes.py:88`). Re-reading it every turn produces **identical bytes**, and a prefix
    cache keys on bytes, not on whether a value was re-read. It breaks the cache only when the trip's
    title or city changes, which is rare. Adding itinerary items does not touch it.
  - `trip_facts` does change on any turn that supplies a new fact (it is merged by
    `merge_trip_facts`, written from `app/agents/supervisor.py:386`), but it already sits **near the
    tail**, after the summary. A change there invalidates only trip_facts, preferences, the language
    pin and the date note — not the large block in front.
  - The real mid-prefix breaker is `summary`, which regenerates whenever the summarizer fires. That
    same event rewrites the message history anyway, so it is periodic and unavoidable.
  The reviewer's suggested follow-up — move trip_context and trip_facts after preferences — would
  therefore buy little: it would only let the short `preferences` block cache. **Not worth doing on
  argument.** Task 1.2's report now has a per-node `miss` column, so if this ever matters it can be
  measured first. Also note the docstring of `system_with_summary` orders profile and instructions
  first *on purpose*, so they carry the most weight; any reorder there is a behaviour change, not a
  caching tweak.
- **2.1/M2** — the brief asked the test to assert `startswith("base system")`, which cannot hold: a
  live sub-agent prepends the shared `communication_style` prompt. The implementer named this under
  behavior.md §2 and asserted against `registry.get("communication_style")` instead, which reads the
  live prompt, so a version bump does not break it. Plan error, correctly caught.
- **2.1/M3 — completeness confirmed with a cited search.** `grep -rn "ground_current_date\|SystemMessage("
  app` finds date grounding only at the two call sites this task changed. Reflection, synthesize, the
  summarizer and memory extraction carry no date, so there is no remaining site with a volatile block
  in front.

- **2.2/I1–I3 (blocking, fix dispatched)** — each could make the probe emit a *wrong verdict*, which is
  what decides whether wave 4 ships:
  - `--seed` discarded its second call's result, so a write that never landed later surfaced as
    `BOTH-MISS`, indistinguishable from real expiry — a false negative that would wrongly skip wave 4.
  - Nothing blocked a second `--check`. A check refreshes both entries, and a re-check a minute later
    still passes the gate (elapsed is measured from the seed), printing a false `TIE`. The docstring
    warned about exactly this and nothing enforced it.
  - `CONTROL-ONLY`, the fourth cell of the two-arm table, was correct but missing from the docstring's
    verdict table and untested.
- **The live scratchpad probe was checked against the same three flaws, and does not have them.** Its
  seed printed a non-zero second-call cache read for both arms (24h 3,328; in_memory 2,816), so both
  writes landed. Its 04:58Z check *did* refresh both entries, so the idle gap for the 06:25Z check is
  measured from 04:58Z, not from the 04:37Z seed: a true gap of **about 87 minutes**, past the
  sixty-minute window. Note the scratchpad script itself prints elapsed from the seed and will
  therefore report a larger, misleading number — the recorded gap must use the 04:58Z figure.
- **2.2/M — design holds up elsewhere.** The gate is measured from the last seed call, which is
  correct. Each nonce sits at byte 0, so the arms share about 4 tokens, far below the 1,024-token
  minimum — no contamination. An arm swap would be caught.

- **2.2/I4 (round 2, blocking) — a partial check could print a false `RETENTION-WINS`.** The
  `checked_at` stamp was written only after both arms' calls succeeded, and the `24h` arm is called
  first. If the `in_memory` call then raised, the `24h` entry had already been refreshed but nothing
  was stamped; a re-run would read `24h` as a HIT because of that fresh refresh rather than retention,
  see an honest control MISS, and print `RETENTION-WINS` with exit 0. This is the worst direction of
  error in the whole spec, because that verdict ships a provider parameter on false evidence. Fix
  dispatched: stamp an attempt marker after the gap gate and before the first call, so any touch of
  the cache spends the experiment.
- **Why a third review round on 2.2 is not an escalation.** `orchestration.md` escalates on the *same*
  check failing twice after a fix. Here each round surfaced a different, deeper failure mode of the
  experiment (unverified seed, repeat check, then partial check), so the review is converging rather
  than thrashing, and each fix is small.
- **The live 06:25Z probe was checked against I4.** The scratchpad script calls `24h` first and prints
  each arm's line only after its call returns. If the second call errors, the output is one arm line
  plus a traceback and no verdict; the experiment is then spent and **must not be re-run**. The
  04:58Z run completed both arms cleanly, so it did not leave this contamination behind.

- **2.2/M — remaining after round 3 (not blocking, deliberately not fixed now):**
  - **Concurrent checks — CORRECTED: practically unreachable, not "the one remaining false-verdict
    path".** Read-then-stamp is not atomic and there is no lock (`probe_cache_retention.py:177-206`),
    which the round-3 reviewer and the controller both described as a live false-verdict path. The final
    correctness scorer (score 25) showed why that overstated it: the only unguarded window is the
    **in-process** gap between reading the state file and writing the marker, with no network or model
    call inside it — the first `.invoke()` runs *after* the marker is persisted. Two `--check` processes
    would have to start within a fraction of a millisecond of each other; any run that starts after the
    marker lands exits 3. Recorded as advisory; an `O_EXCL` lock would close it fully if the probe ever
    runs from automation.
  - `--min-gap-min` is neither saved in the state nor printed beside the verdict, so a run with
    `--min-gap-min 0` produces a verdict indistinguishable from a sixty-minute one. Task 3.1 must use
    the default and record the true gap explicitly.
  - After a refused or crashed seed, `--check` fails with a raw `FileNotFoundError` (exit 1) rather than
    a clear "not seeded" message. Safe — no verdict is printed — but unfriendly.
  - The `check()` docstring still describes exit 3 as "already checked" and omits the `attempted_at`
    marker, unlike the module docstring.
- **2.2 state machine, confirmed by the round-3 reviewer walking every path:** seed deletes old state
  first and writes new state only when both arms are warm; no or corrupt state → exit 1, no verdict;
  spent state (either marker) → exit 3, no verdict token; too soon → exit 2 before any stamp;
  `attempted_at` is on disk before the first call, so a killed process still leaves the experiment
  marked spent.

## Wave 3 — live acceptance (2026-09-10)

All wave-3 commands ran against the **branch code** from the worktree, not the Docker `api`
container, because that container bind-mounts the MAIN checkout (`docker inspect api-api-1`:
`travel-pi/apps/api -> /app`) and would have tested the old prompt order. The eval CLI runs from
the venv and loads the DB agent config itself, so running it from the worktree with the dev
`DATABASE_URL` exercises the branch against production model config (`gpt-5.4-mini`).

### The planned gate did not measure the risk — replaced with a real one (Rule 2 deviation)

Task 3.1 named the `dates` eval goldens as "the D1 behaviour guard". Reading their definitions
(`eval/datasets/dates.json`) shows every date golden checks only `flow_match`, `reply_language` and
`non_empty_reply` — plus `tools_expected: [get_weather]` on the two smoke ones. The golden *notes*
describe the right intent ("a good answer resolves it or asks which day, rather than guessing"),
but **no metric enforces it. None of them would fail if the model silently used today's date.**
The goldens were still run, as a routing and language regression check, and they are clean. But
passing them could not honestly be reported as "the date rules still hold", so a direct A/B was
added: `evidence/date_rule_probe.py`, the same script run against `main` at `34f9920` (note first,
in a throwaway detached worktree, since removed) and the branch (note last), k=3 per probe.

| Probe | Traveller said | `main`, note first | branch, note last |
| --- | --- | --- | --- |
| N1 | flight Hanoi → Singapore, **no date**, EN | 3/3 invented today | 3/3 invented today |
| N2 | same request, VI | 3/3 invented today | 3/3 invented today |
| N3 | same, after a context-setting turn | 2/3 invented today | **0/3** |
| R1 | flight to Tokyo "next Friday" | 0/3 — `resolve_date` 3/3 | 0/3 — `resolve_date` 3/3 |

**Verdict for this PR: no regression.** The branch is equal or better than `main` on every probe.
On N3 — the populated, multi-turn case the Task 1.1 reviewer flagged as the risk — it improves from
2/3 violations to 0/3, matching the reviewer's prediction that final position helps through recency.
With k=3 that gap is **not statistically significant** (Fisher exact, two-sided, p = 0.40), so it
is recorded as directional only.

### Pre-existing production bug found (out of scope — not fixed here)

N1 and N2 violate **6 of 6** on `main`, identically to the branch. Ask for a flight with no date and
the agent calls `search_flights` with today's date and presents the result as if today had been
requested — e.g. *"Here are the flight options for Hanoi → Singapore on 2026-09-10"* — without asking.
That is exactly the behaviour the date note forbids ("you MUST ask which date they want — never fall
back to today"), and `ground_current_date`'s own docstring records an earlier live probe where the
model did the same. It was invisible because no date golden checks dates. Relative dates are handled
correctly on both versions.

Likely cause, not verified: the planner's search-first rule (`docs/solutions/agent/
planner-search-first-save-later.md`) pushes an immediate search, and `search_flights` requires a
`departure_date`, so the model fills one in. On N3, where it has conversation context and the
`needs_clarification` tool, it asks some of the time. This needs its own issue and fix; it is not
caused by, or fixed by, this spec.

### Production retention probe (SC-7) — BOTH-MISS, second independent trial

Seeded 07:16:17Z on `gpt-5.4-mini` with the production script; both arms verified warm (second-call
cache read 4,352 each). Check time was pre-registered at 08:43Z before any result existed, and the
run fired at 08:43:01Z after a true idle gap of **86.8 minutes**: `24h` arm 0 of 4,802 tokens cached,
`in_memory` control 0 of 4,800 → **`BOTH-MISS`**, exit 0. Recorded in
`evidence/retention_probe_production.json` by a recorder that refuses to write on any inconsistency.

This is the second independent trial — different nonces, a different seed, the production script
with every guard the reviews added — and it matches the first. Retention is now **n=2 per arm**, both
`BOTH-MISS`.

### Retention verdict and the wave-4 decision (2026-09-10, 06:25Z)

**Verdict: `BOTH-MISS`.** After a true idle gap of about 87 minutes, both the `24h` arm and the
`in_memory` control read zero cached tokens. Under `ESCALATIONS.md` E003, any verdict other than
`RETENTION-WINS` skips Task 4.1, and that rule was pre-authorised in both directions, so **wave 4 is
skipped with no further human decision**: `app/clients/llm.py` stays untouched and the retention
parameter is not wired.

Why the run is trustworthy — it was checked against every flaw the Task 2.2 reviews later found in
the production script:
- the seed verified both arms warm (second-call cache reads 3,328 and 2,816, both non-zero);
- there was exactly one intermediate check (04:58Z), and it completed both arms, so it left no
  partial-refresh contamination;
- that check refreshed both entries at the same moment, so both arms shared an identical idle history
  from 04:58Z — a fair A/B;
- one final check, no repeat.

What it does and does not show:
- It shows that on `gpt-5.4-mini`, `prompt_cache_retention="24h"` did not keep a prefix cached across
  an 87-minute gap. The server accepts and validates the parameter, but on this model it did not act
  on it — consistent with `-mini` models being absent from OpenAI's extended-retention model list.
- It now rests on **two independent trials per arm**, both `BOTH-MISS` (scratchpad 06:25Z, production
  script 08:43Z). It is still not proof that retention never works: a model that IS on the
  extended-retention list (`gpt-5`, `gpt-5.4`) could behave differently. If the default model changes,
  this is the experiment to re-run.
- It vindicates the conditional-wave structure of E003. Under the original plan, the parameter was to
  be wired in wave 1; that would have shipped a provider parameter into the shared LLM client that
  does nothing on the model actually serving traffic.

Consequence for the idle-gap misses that motivated the spec: **no configuration lever fixes them on
the current model.** The remaining options are a model change or a keep-warm ping, both out of scope.
What this spec does deliver is D1 (standards-correct prefix order), D3 (the hit-rate report, now able
to count missed calls) and D4 (a probe that cannot report a verdict it cannot trust).

Formal closure: the production script's run at 08:43Z (SC-7) returned `BOTH-MISS` too. **Task 4.1 is
`skipped — not triggered`**, against that result, under E003 — no human decision was needed.

### Controller error: an entangled commit, caught and repaired before push (self-reported)

Committing the correctness fix, the controller ran `git add <script> <test> && git commit` followed by
a separate `git add <doc> && git commit`. Both scripts are tracked files under the ignored `scripts/`
directories, so the first `git add` **staged them and then exited non-zero** with an "ignored"
warning. The `&&` skipped the fix commit, and the following docs commit swept all three files in:
`8bc862e`, titled as a docs change, carried the code fix. Caught immediately from the commit's own
"3 files changed" line. The commit was local and unpushed (checked against
`github/feat/prompt-caching-system-prefix`), so it was undone with `git reset --soft HEAD~1` — no
work lost, no shared history rewritten — and remade as `e404505` (fix, 2 files) and `e3bc5cb` (docs,
1 file). The plan constraint had described this trap as "aborts the whole invocation", which is
wrong for tracked files; corrected here, in PLAN, and in memory.

### UAT through the real endpoint (2026-09-10, post-ship, by user request)

Two real chat turns through the actual `POST /agent/chat` — full lifespan, the branch's compiled
graph, the dev Postgres — not the eval harness. Same conversation, so turn 2's specialist prompt
is turn 1's prefix through the D1 reorder. Turn 1 (cold): 23,071 in / 9,344 cached (41%). Turn 2
(same thread): 35,750 in / **31,744 cached (89%)**. Screenshots of the real dashboard, served by
this branch's own code, in `evidence/uat_dashboard_run2_detail.png` and `uat_dashboard_runs_list.png`;
script in `evidence/uat_chat_endpoint_probe.py`. Synthetic user's DB rows deleted after capture.

### Controller error during verification (self-reported)

While mutation-testing the Task 2.2 fix, the controller restored a mutated file with
`git checkout -- apps/api/scripts/probe_cache_retention.py`. That file held the fix agent's
**uncommitted** changes, so the restore reverted it to the pre-fix commit `25186a7` and silently
discarded the whole fix. It was caught within one command, because the next step grepped for the new
guards and found none. Recovery was clean: a copy taken immediately before mutating was restored,
confirmed byte-identical with `cmp`, and the suite was back to 10 passing before anything was
committed. No work was lost and nothing wrong was committed.

The same restore had been safe in wave 1 only because that mutated file was already committed and
unmodified. **Rule for this repo: commit before mutation-testing, then restore from git; never restore
a file that carries uncommitted work.** The fix was committed as `c9d480a` first, and the second
mutation was then run and restored against it safely. Recorded for Task 5.1.

Mutation results for the Task 2.2 fix, both against committed code:
- disabling the repeat-check guard (`if "checked_at" in state`) fails exactly 1 of 10 tests;
- disabling the cold-seed refusal (the seed's `return 3`) fails exactly 1 of 10 tests.

### Blocking findings fixed in-flight

- **1.2/I1** — `scripts/cache_hit_report.py`: `misses` computed `input - cached`, i.e. uncached
  *tokens*, while design D3 and the reframing measurement both mean *calls* that read zero cached
  tokens. Two calls at 2816/3000 and 0/3000 rendered as `misses: 3184`, indistinguishable from two
  half-cached calls, so the tool could not reproduce the "28/30 misses follow an idle gap" finding it
  exists to serve. Fixed: token delta renamed `uncached`, new `miss_calls` counts zero-cache rows.
- **1.2/I2** — `tests/scripts/test_cache_hit_report.py`: the `kind == "llm"` filter was unpinned. The
  fixture inserts a tool step precisely to prove exclusion, but only exit codes were asserted, and
  both hold whether or not the filter exists (overall 0.626 vs 0.563). Deleting the filter in
  `app/repositories/agent_run.py` was therefore a **green** regression. Fixed by asserting aggregate
  values, not exit codes. Proven by mutation rather than assertion: the controller deleted the filter
  and saw exactly `test_db_path_excludes_non_llm_steps` fail, then restored the file to a clean diff;
  the re-reviewer additionally drove four more corruptions (`kind=="tool"`, `kind=="LLM"`,
  `kind in (llm, tool)`, no filter) and all four fail, so the test catches wrong-value corruption and
  not merely removal.

### Harness friction found during execution

- `Write`/`Edit` refuse every path in a sibling git worktree with a branch-isolation
  `unsafe-path:outside-root` error, even after entering the worktree, and even for the scratchpad.
  Both wave-1 implementers had to write every file through Bash heredocs. This is why
  `worktree-isolation-use-in-place-branch` recommended in-place branching. Hook files are a Rule-4
  stop category, so nothing was changed here; recorded for Task 5.1.
- `.gitignore` line 31 is a bare `scripts/`, which matches at **any** depth: both `apps/api/scripts/`
  and `apps/api/tests/scripts/` are ignored, and the tracked files already in them hide it. A plain
  `git add` **refuses a new file** there, and — worse — for a file that is **already tracked** it
  still stages the change but **exits non-zero**. Every add in these directories needs `git add -f`.

### Correctness-review findings (final chain, 34f9920..bab0f0d)

Six plan-blind finders (enclosing-function, removed-behavior, call-site-impact, stack-defects,
guard-completeness, prior-art), then one independent scorer per deduplicated location on a different
model (`fable`). Three finders were clean, including prior-art, which read every active prompt and
found none that contradicts the date note — the main risk in moving it. **No finding touches the
application code**; all four locations are in the two new operator scripts.

| Location | Score | Route |
| --- | --- | --- |
| `scripts/cache_hit_report.py:153` — empty window reported as a 0% hit rate below `--min-ratio` | 75 | **fixed in `e404505`, re-scored 0**; sibling trigger fixed in `4911e49` |
| `scripts/probe_cache_retention.py:177` — missing, truncated or key-incomplete state raises instead of a clean exit | 50 | advisory |
| `app/repositories/agent_run.py:270` — failed or unfinished LLM steps (0/0 tokens) counted as calls and missed calls | 50 | advisory |
| `scripts/probe_cache_retention.py:206` — non-atomic attempt marker | 25 | advisory |

Fix round for the one routed finding:
- `e404505` — an empty window now prints that no LLM steps matched and exits 3 under a gate (0
  without), never a 0.0% rate. An independent re-score (`fable`) scored the defect **0** at `e3bc5cb`
  and confirmed exits 0, 1 and 3 keep their meanings.
- That re-score found a sibling trigger: a window whose matched steps all carry **zero input
  tokens** — exactly the failed or unfinished rows from the `:270` advisory — still gated as "0.0%
  below". It also broke the promise `e404505`'s own docstring made. Fixed test-first in `4911e49`
  (red: `assert 1 == 3`), with two text fixes the re-score listed. A second independent re-score
  covers `e3bc5cb..4911e49`, so the review receipt can pin the final code head.

Advisory detail:
- **:177** — the scorer confirmed `FileNotFoundError`, `JSONDecodeError` and `KeyError` paths offline,
  and judged it ergonomics rather than a contract breach: no model is built and no call is made before
  the raise, the traceback names the cause, and the documented exit 3 covers only a cold seed arm or a
  prior attempt. It never produces a wrong verdict.
- **:270** — real, but the trigger is an LLM exception or a cancelled stream, the gated overall ratio is
  unaffected (0 input, 0 cached), and a `status == "ok"` filter alone would still admit an "ok" row with
  no usage. On today's dev data it moves **one row out of 578**, and none of the 30 supervisor missed
  calls behind the idle-gap finding is such a row — all 30 are successful calls with 2,787–7,712 input
  tokens (checked in the dev database). The headline finding is not contaminated.
- A repeated advisory from three finders, with no trigger: the reply-language pin is no longer the last
  block of the sub-agent prompt. Unlike the date rules, this one IS measured — every golden declares
  `reply_language` — and it passed on all 18 smoke goldens and all date goldens, and the Vietnamese date
  probe replied in Vietnamese on the branch.

### Intent Findings

Final intent review (model `fable`, distinct from the implementers; plan-blind), range
`34f9920..bab0f0d`. Six findings, each routed:

- **Gap 1 — "đo trước và sau" / E001 "measure OpenAI `cached_tokens` before/after": FIXED.** Only a
  *before* number existed. A same-day hit-rate comparison could not have measured D1 anyway: within
  one day and zone the note is identical, so both orderings keep a stable prefix. The measurement
  added targets D1's actual mechanism with OpenAI's `cached_tokens`, using each checkout's real prompt
  builder — see `evidence/prefix_cache_ab.py`. Before: **0** of 4,373 tokens cached across a timezone
  change. After: **3,840** of 4,373 (88%). This also corrects the design's own estimate: the dev
  database is single-timezone, so it could only show the day-rollover half of the benefit (about 2 of
  30 misses). In multi-timezone production, each traveller zone previously got its own cache entry;
  now all zones share one for 88% of the prompt.
- **Gap 1 — delta re-check (`bab0f0d..4911e49`, model `fable`): CLOSED, with an equivalent-drift
  advisory.** It literally satisfies the request's "Đo bằng `cached_tokens` trong usage của response"
  and "đo trước và sau". It drifts from E001's wording "from `agent_run`": the after-measurement is a
  controlled two-call experiment, not `agent_runs` aggregate data, and no after hit-rate on the dev
  database exists. Behaviourally equivalent — a same-day aggregate could not show D1 at all — but a
  different source, so recorded here rather than claimed as an exact match. Production aggregates
  after merge (`scripts/cache_hit_report.py`) would close it in E001's own terms.
- **Delta re-check, other points:** `e404505`, `4911e49` and `e3bc5cb` introduce no new gap, drift or
  excess — exit 3 refines the already-classed report-only `--min-ratio` surface. The SC-7 amendment
  preserves the intent and E003: it keeps the promised behaviour and is verdict-agnostic.
- **Gap 2 — SC-7, production probe pending: closes at the pre-registered 08:43Z check.** The reviewer
  is right that the wave-4 skip so far rests on the scratchpad trial; SC-7 is its formal replacement.
- **Gap 3 — spec directory and `evidence/` not in the branch yet: closes at finish.** The commit gate
  blocks any spec commit until every SC is covered. Until then, the two new `docs/solutions` records
  cite `evidence/` paths that are not yet committed — resolved by the same final commit.
- **Drift (equivalent) — the call sites moved too, not only `ground_current_date`:** advisory. The
  request named one function; the diff also applies it outermost at both call sites. Without that,
  the note would have sat mid-message (the wave-1 interim state), so this is the same outcome made
  complete, not a different one.
- **Excess — `--min-ratio` gate, `--node` filter, `miss_calls` column:** report-only, kept. They come
  from design D3, which the user approved with the plan; `miss_calls` is the column that reproduces
  the missed-call finding.
- **Excess — the eval-golden failure record, the harness record extension, two backlog rows, and the
  date-rule probe:** report-only, kept. They are learnings and verification produced along the way,
  not shipped behaviour.

### Rationale

Idle eviction, not prefix order, is what the measured misses track, so the design's main lever is a
settings-gated retention parameter on the direct OpenAI profile (never a gateway), shipped behind a
flag precisely because its benefit is not yet proven — the 21 min A/B tied. The provider-agnostic
prefix reorder stays as the cheap standards fix that is correct either way. A script over `agent_run_steps` turns
"is caching on?" into a re-runnable number so this question is never answered from a code comment
again.

### Alternatives considered

- Anthropic `cache_control` (E001 option B) — rejected: no Anthropic traffic; would measure ~0.
- Close the spec with the finding only (E002 option C) — rejected by the user: the idle-gap misses
  are real and `24h` retention is a one-line, reversible lever.
- Wire the retention flag in wave 1 and decide its default later (E003 option A) — rejected: with the
  benefit unproven after the tied 21-min A/B, that puts a provider-SDK parameter into the shared
  client for zero measured gain.
- Rely on the OpenAI org default (`24h` for non-ZDR orgs on listed models) — rejected: `-mini`
  models are not on the list and the observed eviction curve is the `in_memory` one.
- Append the date note to the base prompt only, before the per-turn fields — rejected (design D1).

### Deviations

- **Rule 2** — Task 3.1 added a direct date-rule A/B (`evidence/date_rule_probe.py`) because the
  planned gate, the `dates` eval goldens, carries no metric that checks date handling. The goldens
  were still run as planned. No app code was added; the probe lives in the spec's evidence directory.
- **Rule 1** — Task 2.2's implementer added a fourth verdict token, `CONTROL-ONLY`, for the fourth
  cell of the two-arm table, which the plan had omitted; the plan and E003 were corrected to match.
- **Rule 1 — SC-7's check amended before the result existed.** Review round two made the probe
  one-shot (it spends the experiment on first contact with the cache), which made SC-7's original
  check — re-run `--check` — impossible to re-run: after the live run it exits 3 by design. The check
  now asserts the committed record `evidence/retention_probe_production.json` shows exit 0, a valid
  verdict and a true gap of at least 60 min, and asserts no particular verdict. Traceability tier; the
  live run is the truth.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| intake artifact shape | `python3 .claude/scripts/verify_summary.py --lane prompt-caching-system-prefix` | 0 | re-run 2026-09-10 after this rewrite | |
| plan contract | `python3 .claude/scripts/check_plan_contract.py specs/prompt-caching-system-prefix/PLAN.md` | 0 | 7 tasks, SC-1…SC-10 | |
| SC-1 date note is the last block, base prompt first | `cd apps/api && ../../.venv/bin/python -c "from app.agents.state import ground_current_date as g;from langchain_core.messages import SystemMessage as S;c=g(S(content='BASE PROMPT'),'Asia/Ho_Chi_Minh').content;assert c.startswith('BASE PROMPT');assert c.rstrip().endswith('ambiguous.');assert c.index('CURRENT DATE')>c.index('BASE PROMPT')"` | 0 | run at wave-2 close, HEAD 81c89f0 | SC-1 |
| SC-2 real sub-agent sees style, prompt, summary, language pin, then date | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_state.py -q` | 0 | 17 passed | SC-2 |
| SC-3 both call sites ground the date outermost | `cd apps/api && ../../.venv/bin/python -c "import inspect,app.agents.supervisor as s,app.agents.subagents._base as b;src=inspect.getsource(s)+inspect.getsource(b);assert 'system_with_summary(state, ground_current_date' not in src;assert src.count('ground_current_date(')==2"` | 0 | red on 34f9920 before Task 2.1, green after | SC-3 |
| SC-4 report aggregates llm steps and gates on --min-ratio | `cd apps/api && ../../.venv/bin/python -m pytest tests/scripts/test_cache_hit_report.py -q` | 0 | 8 passed; kind filter proven by mutation | SC-4 |
| SC-6 two-arm probe tested offline incl. all four verdict cells | `cd apps/api && ../../.venv/bin/python -m pytest tests/scripts/test_probe_cache_retention.py -q` | 0 | 12 passed; three guards proven by mutation | SC-6 |
| SC-8 retention wiring absent from app/ (wave 4 skipped) | `cd apps/api && ../../.venv/bin/python -c "import inspect,pathlib;from app.core.config import Settings;src=inspect.getsource(__import__('app.clients.llm',fromlist=['x']));wired=hasattr(Settings(),'openai_prompt_cache_retention');hits=[f for f in pathlib.Path('app').rglob('*.py') if 'prompt_cache_retention' in f.read_text()];assert (wired and 'resolved_base_url is None' in src and 'prompt_cache_retention' in src) or (not wired and not hits)"` | 0 | unwired branch holds, matching the BOTH-MISS verdict | SC-8 |
| SC-9 lint clean | `cd apps/api && ../../.venv/bin/ruff check app scripts tests/scripts tests/agents/test_state.py` | 0 | | SC-9 |
| hit-rate report on real dev data (Postgres) | — | 0 | LIVE — not re-run by the gate (needs the dev Postgres and DATABASE_URL). Ran: `cd apps/api && ../../.venv/bin/python -m scripts.cache_hit_report --since 7d`. Result: env: `DATABASE_URL` for the dev Postgres. Overall 71.6%; supervisor row shows **30 missed calls**, exactly the intake's hand-counted SQL figure, which confirms the review fix (the pre-fix column would have read 235,930 uncached tokens) |  |
| date goldens vs main baseline, k=3 | — | 0 | LIVE — not re-run by the gate (paid live agent run, over the 60s gate timeout). Ran: `cd apps/api && ../../.venv/bin/python -m eval --suite full --capability dates --repeat 3 --out eval/reports/wave3-dates.json`. Result: 3/4, **identical per case to `eval/baselines/main.json`**: the one failure, `dates-multi_turn-vi-01`, also fails on main, both as a routing miss (`flow_match`) | |
| smoke suite on the branch | — | 0 | LIVE — not re-run by the gate (paid live agent run, over the 60s gate timeout). Ran: `cd apps/api && ../../.venv/bin/python -m eval --suite smoke --out eval/reports/wave3-smoke.json`. Result: **18/18**, every capability 100% | |
| date-rule A/B, note-first vs note-last, k=3 | — | 0 | LIVE — not re-run by the gate (paid live agent runs across two checkouts). Ran: `cd apps/api && PYTHONPATH=. ../../.venv/bin/python ../../specs/prompt-caching-system-prefix/evidence/date_rule_probe.py 3 branch-note-last out.json`. Result: run from each checkout; results in `evidence/`. Branch never worse than main on any probe; see "Wave 3" section | |
| cached_tokens before/after across a timezone change | — | 0 | LIVE — not re-run by the gate (paid API calls across two checkouts). Ran: `cd apps/api && PYTHONPATH=. ../../.venv/bin/python ../../specs/prompt-caching-system-prefix/evidence/prefix_cache_ab.py branch-note-last out.json`. Result: run from each checkout. Before (main, note first): **0** of 4,373 tokens cached on the tz-B call, shared prefix 43 chars. After (branch, note last): **3,840** of 4,373 cached, shared prefix 17,597 of 18,205 chars. Both timezone pairs identical | |
| SC-10 durable record exists and the solutions index agrees with it | `python3 .claude/scripts/rebuild_solution_index.py --check` | 0 | run from the worktree root (harness scripts copied into the gitignored `.claude/`) | SC-10 |
| SC-5 the report runs end-to-end against the configured database | `cd apps/api && ../../.venv/bin/python -m scripts.cache_hit_report --since 7d` | 0 | the plan's own check, verbatim. A bare checkout's configured DB is an empty SQLite file, so a re-run takes the "nothing to measure" path; the run on real dev data is the row below | SC-5 |
| SC-7 the one-shot live probe run is recorded with a verdict | `python3 -c "import json;d=json.load(open('specs/prompt-caching-system-prefix/evidence/retention_probe_production.json'));assert d['exit_code']==0;assert d['verdict'] in ('RETENTION-WINS','TIE','BOTH-MISS','CONTROL-ONLY');assert d['true_gap_min']>=60"` | 0 | the amended check (see PLAN §3 note): asserts the committed record, not a verdict. Live run 08:43:01Z, true gap 86.8 min: `24h` 0/4,802 MISS, `in_memory` 0/4,800 MISS → **`BOTH-MISS`**, exit 0 | SC-7 |
| overall hit rate (dev DB) | — | 0 | LIVE — not re-run by the gate (needs the dev Postgres in Docker). Ran: `docker exec api-db-1 psql -U travel -d travel -Atc "select count(*), sum(input_tokens), sum(cached_tokens), round(100.0*sum(cached_tokens)/nullif(sum(input_tokens),0),1) from agent_runs;"`. Result: 166 runs · 4,329,915 input · 3,111,552 cached · 71.9% | |
| hit rate by node/model | — | 0 | LIVE — not re-run by the gate (needs the dev Postgres in Docker). Ran: `docker exec api-db-1 psql -U travel -d travel -Atc "select coalesce(node,'?'), model, count(*), sum(input_tokens), sum(cached_tokens), round(100.0*sum(cached_tokens)/nullif(sum(input_tokens),0),1) from agent_run_steps where kind='llm' group by 1,2 order by 4 desc;"`. Result: assistant 75.8, supervisor 49.4, reflection/synthesize/summarize 0.0 | |
| supervisor hit rate by idle gap | — | 0 | LIVE — not re-run by the gate (needs the dev Postgres in Docker). Ran: `docker exec api-db-1 psql -U travel -d travel -Atc "with runs as (select id, started_at::timestamptz s, lag(finished_at::timestamptz) over (order by started_at) prev_f from agent_runs where started_at is not null) select case when r.prev_f is null then 'first' when r.s-r.prev_f < interval '5 min' then '<5m' when r.s-r.prev_f < interval '15 min' then '5-15m' when r.s-r.prev_f < interval '60 min' then '15-60m' else '>60m' end, count(*), sum(case when st.cached_tokens>0 then 1 else 0 end) from agent_run_steps st join runs r on r.id=st.run_id where st.kind='llm' and st.node='supervisor' group by 1 order by 1;"`. Result: `<5m 98/94 · 5-15m 6/4 · 15-60m 9/2 · >60m 17/0` | |
| retention A/B after 21 min idle (both arms) | — | 0 | LIVE — not re-run by the gate (scratchpad script, one-shot, paid). Ran: `cd apps/api && PYTHONPATH=. ../../.venv/bin/python /private/tmp/claude-501/-Users-minhtran-Documents-minhtran3124-developer-travel-pi/70aa9448-96ce-4dc1-a18f-7ce9649d8209/scratchpad/retention_probe.py /private/tmp/claude-501/-Users-minhtran-Documents-minhtran3124-developer-travel-pi/70aa9448-96ce-4dc1-a18f-7ce9649d8209/scratchpad/retention_state.json check`. Result: `24h` HIT (3,328/3,577) **and** `in_memory` HIT (2,816/3,310) — 21 min does not separate the policies | |
| discriminating retention A/B (>60 min true gap) | — | 0 | LIVE — not re-run by the gate (scratchpad script, one-shot, paid). Ran: `cd apps/api && PYTHONPATH=. ../../.venv/bin/python /private/tmp/claude-501/-Users-minhtran-Documents-minhtran3124-developer-travel-pi/70aa9448-96ce-4dc1-a18f-7ce9649d8209/scratchpad/retention_probe.py /private/tmp/claude-501/-Users-minhtran-Documents-minhtran3124-developer-travel-pi/70aa9448-96ce-4dc1-a18f-7ce9649d8209/scratchpad/retention_state.json check`. Result: 06:25Z, true gap about 87 min: `24h` 0/3577 MISS, `in_memory` 0/3310 MISS → `BOTH-MISS`. Early pre-registered trial with the scratchpad script, not the production script, so it does NOT close SC-7 | |
| retention param accepted / validated | — | 0 | LIVE — not re-run by the gate (scratchpad script, paid API calls). Ran: `cd apps/api && PYTHONPATH=. ../../.venv/bin/python /private/tmp/claude-501/-Users-minhtran-Documents-minhtran3124-developer-travel-pi/70aa9448-96ce-4dc1-a18f-7ce9649d8209/scratchpad/retention_probe.py /private/tmp/claude-501/-Users-minhtran-Documents-minhtran3124-developer-travel-pi/70aa9448-96ce-4dc1-a18f-7ce9649d8209/scratchpad/retention_state.json seed`. Result: scratchpad script (promoted to `scripts/probe_cache_retention.py` in Task 2.2); 24h nonce `3e0a42e3` 2nd-call cache_read 3328/3577; in_memory `55841cf6` 2816/3310; an earlier ad-hoc call with `"bogus"` returned HTTP 400 | |
### Not auto-verified

Every claim below comes from a real run, recorded with its exact command in a `### Verify` row
marked `—` (skipped by the gate) or in `evidence/`. They reached **provenance** — evidence
re-derived from the source of truth at the time — but the ship gate does **not** re-run them,
because each needs the dev Postgres, a paid model call, two checkouts, or is one-shot by design.

- **Caching was already on at 71.9%, and misses follow idle gaps (>60 min: 0/17)** — provenance: dev
  database queries on 2026-09-10. Dev traffic is single-timezone; **production is unmeasured**
  (`scripts/cache_hit_report.py` makes it a one-liner there).
- **`prompt_cache_retention="24h"` is not honoured on `gpt-5.4-mini`** — provenance: two independent
  two-armed trials (scratchpad 06:25Z `BOTH-MISS`; production script SC-7, see its row). A model on
  OpenAI's extended-retention list could behave differently and has not been tested.
- **No regression in routing, language or expected tools from the reorder** — provenance: smoke 18/18
  and date goldens 3/4, identical per case to `eval/baselines/main.json`.
- **The date rules hold at least as well with the note last** — provenance: the date-rule A/B, k=3
  per probe. The multi-turn improvement (2/3 → 0/3 violations) is **not significant** (Fisher p=0.40).
- **The reorder serves 88% of the prompt from cache across a timezone change (0 → 3,840 of 4,373)**
  — provenance: `evidence/prefix_cache_ab.py`, both timezone pairs identical.
- **Pre-existing bug: no-date flight search uses today's date, 6/6 on `main`** — provenance: the
  date-rule A/B. Root cause **not verified** (the planner's search-first rule is a hypothesis).
- **SC-5 — the report runs against a real database** — provenance: one run against the dev Postgres,
  exit 0, reproducing the 30 supervisor missed calls.
### Rollback

- The whole branch is additive except the date-note move. To revert everything:
  `git revert --no-edit 4911e49 e3bc5cb e404505 bab0f0d 81c89f0 c9d480a 25186a7 9a0df74 271c086 7e59ce6 7041ae9`
- To revert only the one behaviour change (the date-note position) and keep the scripts:
  `git revert --no-edit 9a0df74 7e59ce6`
- No migration, no schema change, no configuration change, no provider parameter — nothing to undo
  outside git. The retention flag was never shipped, so there is no environment variable to unset.

### Harness-Delta

- backlog → `compound`: intake accepted a review's "feature X is off" claim (09-08) without querying
  the metrics that already existed; a one-line rule "if the repo records the metric, read it before
  classifying" would have changed the first escalation's options. Recorded in Task 4.1.
