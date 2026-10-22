# gh-155-supervisor-booking-follow-on — Design

Status: approved in brainstorming (2026-09-07). Lane: high-risk (user-decided remove-functionality). Issue #155.

## Purpose

A multi-intent turn whose second half is a booking ("…and book the cheapest one") must never crash the supervisor. Today the model can put `booking` into the legacy `secondary_agent` field, `SupervisorIntent` rejects it with a `ValidationError`, and the turn errors.

## Decision (user, brainstorming)

Prompt v11 rule + delete the legacy field. `plan` becomes the only follow-on channel; the model has no second field to route a forbidden target through.

Rejected: code-side tolerance (widen the schema and rely on the Python filter) — the user preferred removing the legacy surface over tolerating malformed output; catch-all `except ValidationError` — hides malformed output.

Known limit (stated once): a prompt rule is not crash-proof. If the model writes `booking` into `plan`, pydantic still rejects it. That is the same exposure as today for `plan` and is out of scope here; a follow-up may add a tolerant schema if it recurs.

## Components

| # | File | Change |
| --- | --- | --- |
| 1 | `apps/api/app/agents/supervisor.py` | Remove `secondary_agent` from `SupervisorIntent` (line 69) and the legacy fallback at lines 310–323 (`legacy = getattr(intent, "secondary_agent", None)`); `candidates = list(raw_plan or [])`. Keep `_SecondaryTarget` and the booking filter in the task loop as defence in depth. |
| 2 | `apps/api/app/prompts/supervisor/v11.md` (+ `active.yaml` supervisor: 11, `CHANGELOG.md`) | Copy of v10 with: the "legacy `secondary_agent` still works" sentence (v10:123) removed; the Multi-step Plan rules extended with one explicit line: a booking wish inside a multi-intent message is NOT a `plan` step — route the booking as `target_agent=booking` when it is the traveller's main ask, otherwise leave it out of `plan` and let the specialist mention it; `plan` never contains `booking`. CHANGELOG entry citing #155. |
| 3 | Tests constructing `SupervisorIntent(secondary_agent=…)` — `tests/agents/test_supervisor_plan_semantics.py`, `test_multi_intent_routing.py`, `test_specialist_metadata_end_to_end.py`, `test_task_ledger.py`, `test_tier_gating.py`, `test_supervisor_slots.py`, `tests/api/agent/test_agent_chat.py` | Migrate each to `plan=[…]`; `test_legacy_secondary_agent_is_kept` becomes `test_legacy_secondary_agent_is_ignored`: `SupervisorIntent` has no `extra` override, so pydantic v2's default `extra="ignore"` silently drops the key (verified in this venv by the spec reviewer) — assert the constructed intent has no such attribute and yields a single-task plan. |
| 4 | `apps/api/tests/agents/test_supervisor_plan_semantics.py` | New regression test: a FakeLLM structured response shaped like the #155 payload (`target_agent="planner", plan=["booking"]`) is rejected by the schema — documents the residual exposure — and a second test that `SupervisorIntent` has no `secondary_agent` field (`"secondary_agent" not in SupervisorIntent.model_fields`). |
| 5 | `apps/api/tests/api/prompts/test_prompt_registry_helpers.py` | Unchanged (asserts against active.yaml dynamically); dashboard tests pick up v11 automatically. |

## Data flow

Supervisor structured output → `SupervisorIntent` (target_agent, plan, slots, language) → `task_agents = [target] + dedup(plan minus booking/unknown/tier-gated)` → `tasks`. No behavioural change for well-formed output; the only removed path is `secondary_agent`.

## Error behaviour

- Model emits `secondary_agent` anyway: pydantic v2 default `extra="ignore"` (no override on the model) → silently dropped; the booking follow-on simply does not happen, no crash.
- Model emits `plan=["booking"]`: still a `ValidationError` (residual, documented).

## Tests / success criteria

- SC-1 `"secondary_agent" not in SupervisorIntent.model_fields`.
- SC-2 all migrated tests pass: `pytest tests/agents -q -k "supervisor or multi_intent or ledger or tier or slots or metadata"` and `tests/api/agent/test_agent_chat.py`.
- SC-3 `registry.active_version("supervisor") == 11` and `v11.md` contains the new rule and not the legacy sentence.
- SC-4 prompt-change gotcha honoured: the running dev container is rebuilt (`docker exec api-api-1 touch app/main.py`) before any live check (memory: prompt-changes-need-graph-rebuild).

## Out of scope

Tolerant schema for `plan`; eval re-run (the golden `routing-multi_turn-en-01` is re-checked only if the user authorises a keyed `--capability routing` run).
