# gh-180-supervisor-plan-invalid-entries — Summary

Lane: normal
Confidence: high
Reason: two flags (existing behavior, weak proof); no manifest hard gate — the fix ADDS a coercing `field_validator` on LLM structured output rather than removing an assert/raise, so weakening-validation is not tripped (named below as the one judgment call).
Flags: existing-behavior, weak-proof
Affects: apps/api/app/agents/supervisor.py (SupervisorIntent.plan schema + task-list build), apps/api/app/prompts/supervisor (optional v13 note), apps/api/eval (routing multi_turn goldens as the regression signal)
Input-type: change request
Route: using-git-worktrees → subagent-driven-development (PLAN.md required: >2 files — schema/validator, tests, optional prompt bump + CHANGELOG, eval re-run)
Escalate: no

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

User request (verbatim, via `/feature-intake`):

> cho issue nay https://github.com/minhtran3124/travel-pi/issues/180

GitHub issue #180 — "Agent: supervisor intermittently returns a nested object in plan, crashing the turn with a ValidationError" (bug, OPEN), scope-deciding text:

> The supervisor's structured output intermittently puts a **nested object** in `plan` where a specialist literal belongs, and the turn dies with a pydantic `ValidationError` [...] `plan=[{'target_agent': 'journal', 'slots': None}]` [...] instead of `plan=['journal']`. `_SecondaryTarget` is a `Literal`, so the whole run raises rather than degrading.

> Validation is doing its job; the question is what should happen when the model returns a malformed follow-on. Dropping an invalid `plan` step is already the documented behavior — the `plan` field description says *"Duplicate or invalid steps are dropped in code"* — so a nested object arguably belongs in that same bucket rather than raising. A `field_validator` that coerces `{'target_agent': X}` to `X`, or simply discards unparseable entries, would keep the primary route working. Worth pairing with a prompt note that `plan` holds bare specialist names.

> Whatever the fix, the two `multi_turn` goldens should stop flipping — that is the cheap regression signal.

Owner comment (2026-09-10), broadening scope:

> it is **not only nested objects**. [...] `input_value='booking', input_type=str` [...] So the failure class is **any value the model puts in `plan` that the Literal does not accept**, and a nested object is only one instance. [...] `SupervisorIntent.plan`'s own field description says: "Duplicate or invalid steps are dropped in code." They are not. [...] coerce or discard unparseable/forbidden `plan` entries in a `field_validator` so the primary route survives, and make the promise in the description true.

## What changed

<pending — filled by subagent-driven-development>

### Rationale

Intake classification only. The direction is fixed by the issue itself: make the field description true — `SupervisorIntent.plan` must accept whatever the model emits and drop/coerce in code before validation raises, so the primary route always survives. One interpretation; the coerce-vs-discard choice for `{'target_agent': X}` is a detail (safe default: coerce a dict carrying a valid secondary `target_agent`, drop everything else including `'booking'`), not a materially different implementation.

Classification evidence (read at intake):

- `apps/api/app/agents/supervisor.py:37` `_SecondaryTarget = Literal[...]`; `:69` `plan: list[_SecondaryTarget] | None` — pydantic raises before `:311-330` (the Python-side dedupe/`booking`/tier filter) ever runs, which is exactly the broken promise in the description.
- `:228` `with_structured_output(SupervisorIntent, method="function_calling")` — the error surfaces inside the supervisor node, killing the turn (matches "a real user-facing crash").
- Active prompt is `supervisor: 12` (`apps/api/app/prompts/active.yaml`); v12 already says `plan` must never contain `booking` (lines ~113-116 in v11, same rule in v12) — the prompt is not the missing piece, the validator is. A prompt note is optional polish; if added it must be a **new v13 + `active.yaml` bump + CHANGELOG entry** (registry is a pointer; see `docs/solutions/agent/supervisor-active-yaml-is-a-pointer.md`).
- Goldens `routing-multi_turn-en-01` / `routing-multi_turn-vi-01` in `apps/api/eval/datasets/routing.json`; baseline `apps/api/eval/baselines/main.json`.
- Existing test pattern to extend: `apps/api/tests/agents/test_supervisor_plan_semantics.py` (FakeLLM `structured_responses`). Note FakeLLM hands back an already-built `SupervisorIntent`, so the new tests must construct via `SupervisorIntent.model_validate({...})` with raw dict/str inputs to exercise the validator.

### Side-effect check (pre-plan, 2026-09-10)

Verified against code before planning, at the user's request:

- **Keep the `Literal` type; filter with `field_validator("plan", mode="before")`.** The function-calling schema today carries `enum: [planner, concierge, journal, budget]` for `plan` (checked via `SupervisorIntent.model_json_schema()`). Changing the type to `list[str]`/`list[Any]` would drop that enum hint and make the model emit MORE invalid values. A `mode="before"` validator keeps the wire schema byte-identical.
- **One existing test flips on purpose:** `tests/agents/test_supervisor_plan_semantics.py:110` `test_plan_with_booking_still_rejected` asserts `ValidationError` for `plan=["booking"]`. Rewrite it to assert booking is dropped (not raised); removing the `pytest.raises` line may trip the warn-mode weakening-validation hook.
- **No other consumer breaks:** only `supervisor.py:312` reads `intent.plan`, and it already handles `None` and `[]`. FakeLLM returns pre-built `SupervisorIntent` objects (no validation), so the 30+ test modules using it are unaffected. `ValidationError` is not in `_is_retryable_llm`, so today the node dies outright with no retry.
- **Accepted behavioural trade:** crash → silently dropped secondary intent. Mitigate by (a) coercing `{'target_agent': X}` to `X` when X is a valid secondary target, so the common nested case keeps its intent, and (b) `logger.warning` on every dropped entry so eval/log signal is not lost.
- **After fix:** re-run the routing eval so `routing-multi_turn-en-01/vi-01` stop flipping; baseline currently records the crash as FAIL, so consider `make eval-baseline` once stable (gate only blocks regressions, extra passes do not block).

### Alternatives considered

- **Lane `high-risk` via weakening-validation** — considered because the change loosens a pydantic `Literal` on `plan`. Rejected: no `assert`/`raise`/validator is removed; a validator is *added*, the `booking`/unknown filter at `:311-330` stays, and the schema guards LLM output (not a trust boundary from a client). The hook is warn-mode anyway; if the diff trips it, downgrade with `RISK_WARN_CATEGORIES="weakening-validation"` and record here.
- **Lane `tiny`** — rejected: >1 file (model + tests + eval re-run, possibly prompt v13/CHANGELOG), and a shared schema consumed by 30+ test modules.
- **Prompt-only fix** — rejected by the owner comment: the prompt already forbids `booking` and the model disobeys; the code must degrade gracefully.

### Deviations

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| intake summary shape | `python .claude/scripts/verify_summary.py --lane gh-180-supervisor-plan-invalid-entries` | 0 | intake-time only; implementation rows added by SDD | |

### Not auto-verified

- Lane/flag classification — reached traceability (read supervisor.py, prompts, goldens, manifest); not re-run because it is a judgment, corroborated later by `risk-corroboration.sh` on the staged diff.
- "The two multi_turn goldens stop flipping" — not yet run; requires `make eval-smoke` / judged routing run inside the Docker api container (see `docs/solutions/` eval-harness notes).

### Rollback

- `git revert <sha>`

### Harness-Delta

- none
