# gh-155-supervisor-booking-follow-on — Research Brief

Depth: **Standard** (intake: normal signals; the lane is high-risk only through the user-decided `remove-functionality` gate, so local mapping was done broadly). External surface: **none** — no dependency, integration, or version-specific API change (pydantic v2 behaviour is verified against the installed package, not assumed).

## Bottom Line

| Field | Value |
|---|---|
| **Recommendation** | **reuse existing** — `plan` already is the follow-on channel and the Python task filter already drops `booking`; the work is deleting the legacy field/fallback, a v11 prompt copy with one rule, and migrating 7 test files from `secondary_agent=` to `plan=[...]`. |
| **Why this is the lightest credible path** | No new abstraction; every line either removes a path or restates an existing rule in the prompt. |
| **Confidence** | 90% |
| **Next step** | `writing-plans` (PLAN.md in this directory), then `using-git-worktrees` on `fix/gh-155-supervisor-booking-follow-on` off `main`. |

## Repo Snapshot

| Field | Detected |
|---|---|
| Repo type | monorepo; this spec touches `apps/api` only |
| Primary language + runtime | Python 3.14 local / 3.12 CI |
| Frameworks | pydantic v2 (`SupervisorIntent` is a `BaseModel` with no `model_config`), LangGraph 1.x, prompt registry (`app/prompts/<name>/vN.md` + `active.yaml` + `CHANGELOG.md`) |
| Relevant packages | `app/agents/supervisor.py`, `app/prompts/supervisor/`, `tests/agents/`, `tests/api/agent/`, `tests/api/prompts/` |
| Important constraints | prompt edits are not hot-reloaded (memory `prompt-changes-need-graph-rebuild-not-hot-reloaded`: `docker exec api-api-1 touch app/main.py`); `active.yaml` is a pointer (docs/solutions `supervisor-active-yaml-is-a-pointer`); stage/commit separately; no Claude trailers |

## Feature Understanding and Assumptions

- **Requested:** stop the supervisor crashing when the model emits `secondary_agent="booking"` (#155) — user decision: prompt v11 rule + delete the legacy `secondary_agent` field and its fallback.
- **Success:** `SupervisorIntent` has no `secondary_agent`; a raw payload carrying it is silently ignored (no `ValidationError`); v11 is active and states the booking-follow-on rule; every test that used the legacy field passes on `plan=[...]`.
- **Assumptions taken:** pydantic default `extra="ignore"` (verified: no `model_config` on the model, spec reviewer confirmed empirically); `_SecondaryTarget` stays because `plan: list[_SecondaryTarget]` uses it.
- **Still to confirm:** none material.

## Evidence Ledger

| Label | Evidence |
|---|---|
| `Local` | `app/agents/supervisor.py:36` `_SecondaryTarget = Literal["planner","concierge","journal","budget"]`; `:69-79` `secondary_agent` field (description says "Never 'booking'"); `:80-90` `plan: list[_SecondaryTarget] \| None`; `:320-324` fallback `legacy = getattr(intent, "secondary_agent", None); candidates = [legacy] if legacy else []`; `:326-333` the task loop already skips `booking`, unknown and tier-gated steps and dedupes. |
| `Local` | `SupervisorIntent` has no `model_config` / `extra=` (grep) → pydantic v2 default `extra="ignore"`: an unknown `secondary_agent` key in a structured-output payload is dropped once the field is removed — the crash path disappears by construction. |
| `Local` | `app/prompts/supervisor/v10.md:99-125` "Multi-step Plan": already forbids `booking` and `target_agent` in `plan`; `:122-124` says the legacy `secondary_agent` "still works … like a one-item plan" — the sentence to delete in v11. No rule about `secondary_agent` never being `booking` (the field description in code had it; the model ignored it). |
| `Local` | v10 bump convention (commit `9714e88`): copy vN → vN+1, edit, `active.yaml` pointer, `CHANGELOG.md` entry at the TOP with heading `## <spec-slug> — <summary>`, bullets per prompt ("copied vN, then …; no existing line removed" or naming the removed line), closing `active.yaml: name → N`. |
| `Local` | `tests/api/prompts/test_prompt_registry_helpers.py:15-27` asserts active versions dynamically against `active.yaml` (no hardcoded 10); `tests/agents/test_prompt_map.py:116` likewise; dashboard tests read `registry.active_version("supervisor")`. A v11 bump needs no test edit there. |
| `Local` | Construction sites of `secondary_agent=` (7 files, 12 sites) and what each asserts: `tests/agents/test_supervisor_plan_semantics.py:89-94` `test_legacy_secondary_agent_is_kept` asserts `["planner","budget"]`; `tests/agents/test_task_ledger.py:197-205` `test_null_plan_falls_back_to_legacy_secondary` asserts legacy == one-item plan; `tests/agents/test_supervisor_slots.py:124-168` three tests (booking target forces empty → `["booking"]`; valid distinct secondary → `["planner","concierge"]`; secondary == target dropped → `["planner"]`); `tests/agents/test_multi_intent_routing.py:44,73,193` FakeLLM scripts `planner + concierge` and assert `current_flow == "synthesize"` / results cleared; `tests/agents/test_specialist_metadata_end_to_end.py:29`, `tests/agents/test_tier_gating.py:190,215` (`concierge + planner`, tier gating drops planner for free tier), `tests/api/agent/test_agent_chat.py:240,294` (planner + concierge through the router). Every site maps 1:1 to `plan=[<secondary>]` with the same assertion; only the two "legacy" tests change meaning. |
| `Local` | Eval evidence of the trigger: `eval/reports/run2.json` on `feat/agent-eval-pipeline` — `routing-multi_turn-en-01` `agent_run` check: `ValidationError … secondary_agent Input should be 'planner', 'concierge', 'journal'…`. |
| `Upstream` | Installed pydantic 2.x: `BaseModel` default `extra='ignore'` — unknown keys dropped silently (verified in-venv by the spec reviewer). |
| `Inference` | Removing the field cannot change well-formed behaviour: with `plan` set the fallback was never consulted; with `plan` null the fallback only mattered when the model used the legacy field, which v11 no longer describes. |

## Local Findings

- **Files:** `app/agents/supervisor.py` (schema + task loop), `app/prompts/supervisor/v10.md` → `v11.md`, `app/prompts/active.yaml`, `app/prompts/CHANGELOG.md`, 7 test files above.
- **Extension points:** prompt registry (`vN.md` + pointer), `SupervisorIntent` field descriptions (also fed to the model as the function-calling schema — the `plan` description already says "never 'booking'").
- **Conventions:** CHANGELOG entry per bump naming the spec slug; tests assert on `cmd.update["tasks"]` agent lists; FakeLLM `structured_responses=[SupervisorIntent(...)]`.
- **Reusable:** the task loop's booking/dedupe/tier filter — unchanged.
- **Missing:** a regression test that a raw structured-output payload with `secondary_agent` does not raise; v11.

## Upstream Findings

- Installed pydantic only (no remote fetch): `extra="ignore"` default confirmed; `Literal` validation raises `ValidationError` for `plan=["booking"]` — the residual exposure the design documents.

## Docs Findings

- none (local-only; no external surface).

## Recommendation

- **Primary:** reuse existing — delete the legacy path, bump v11, migrate tests.
- **Why lightest:** two production edits (one deletion, one prompt copy) and mechanical test migration.
- **Why the alternative lost:** widening the schema to accept `booking` keeps a field nobody needs and re-documents a rule the model already breaks; a `try/except ValidationError` hides malformed output.
- **What would flip it:** if the model starts writing `booking` into `plan` at a noticeable rate, a tolerant schema (accept then drop in code) becomes the right fix.

## Risks, Unknowns, and Follow-Up Questions

- **Technical:** the prompt rule is not crash-proof for `plan=["booking"]` (documented residual). The 12 test-site migration is mechanical but touches files other specs may edit — keep same-wave file sets disjoint.
- **Evidence gaps:** none blocking. The trigger is nondeterministic (1/3 judged runs), so proof is the unit test with a raw payload, not a paid eval.
- **Follow-up questions:** none.

## Source Pack

- **Local files read:** `apps/api/app/agents/supervisor.py`, `apps/api/app/prompts/supervisor/v10.md`, `apps/api/app/prompts/active.yaml`, `apps/api/app/prompts/CHANGELOG.md` (top entries + commit `9714e88` stat), `apps/api/tests/agents/{test_supervisor_plan_semantics,test_multi_intent_routing,test_specialist_metadata_end_to_end,test_task_ledger,test_tier_gating,test_supervisor_slots,test_prompt_map}.py`, `apps/api/tests/api/agent/test_agent_chat.py`, `apps/api/tests/api/prompts/test_prompt_registry_helpers.py`, `specs/gh-155-supervisor-booking-follow-on/{SUMMARY,design}.md`, memory notes `prompt-changes-need-graph-rebuild-not-hot-reloaded`, `supervisor-active-yaml-is-a-pointer`.
- **Upstream repositories or pages checked:** installed pydantic 2.x in `.venv` (default `extra` behaviour).
- **Official docs domains or pages checked:** - none (local-only; no external surface)

## Evidence Boundary

> Confirmed from artifacts: field/fallback line numbers, the 12 construction sites and their assertions, v10 wording, bump convention, dynamic version tests, pydantic default.
> Inferred from patterns: no behaviour change for well-formed output.
> Not checked: live model behaviour after v11 (needs a keyed run; optional).
