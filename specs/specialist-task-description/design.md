# specialist-task-description — Design

Status: **proposed, authored from research-brief defaults — not yet user-approved.** The intake
lane is `normal`; this file exists only because the schema shape is a real fork (two viable
designs). It records the decisions the plan builds on so they can be reversed in one place.

## Problem

On a fan-out turn the supervisor writes N `AgentTask`s that all carry the same `query` (the whole
user sentence), and no node reads `query` anyway. Every specialist receives the full history and
must guess its own slice. Upstream (deepagents "fork" mode) solves this by appending a fixed
preamble + task description after the inherited history.

## Decisions

**D1 — Schema: a parallel list, `plan` untouched.** `SupervisorIntent` gains
`task_queries: list[str] | None = None`, positionally aligned with `[target_agent, *plan]`. Code
fills `AgentTask.query` from it and falls back to the last user message for any missing/blank
entry, so a model that ignores the field degrades to today's behaviour. Rejected: `plan` as
`[{agent, query}]` objects — breaks `test_wire_schema_keeps_plan_enum`, re-enters the gh-180
coercer, and changes an enum the model has routed reliably on since v9.

**D1 addendum — no supervisor prompt change (2026-09-10, decision E003-A).** A v13 prompt section
teaching `task_queries` was built and reverted: it dropped the budget+concierge fan-out in 6/18
probe samples (0/30 on v12 and main). The field's schema description alone makes the model fill
`task_queries` (12/12 real splits under v12). The field applies only when two or more tasks are
emitted, because the model also filled it for single intents (6/6 on a booking request).

**D2 — Delivery: folded into the single leading `SystemMessage` (revised 2026-09-10).**
`with_task_note(system_msg, state)` appends `TASK_NOTE_PREAMBLE + query` to the end of the leading
system message, after `with_reply_language`; `messages` is untouched and nothing is stored.
The first version appended a separate trailing `SystemMessage`. The final correctness review
rejected it: the codebase requires one leading system message (`system_with_summary` docstring,
pinned by four tests in `test_profile_injection.py` / `test_procedural_injection.py`, which went
red), and langchain-anthropic raises `Received multiple non-consecutive system messages` on
that shape, so every routed turn on an Anthropic-configured specialist crashed. The trailing
note also landed after the reflection REVISE note and after each tool round's results.
Cost accepted: the query changes per turn, so the cached prompt prefix now diverges at the end
of the system message instead of after the history — not measured (see SUMMARY `Not
auto-verified`). Rejected: `HumanMessage` (language-flip bug); per-provider branching (complexity
for a provider that is not configured today).

**D3 — Scope: a note only for a real split (revised 2026-09-10, decision E001-A).** The specialist
always reads `state["tasks"][0]["query"]`; single-intent gets the supervisor's list, fan-out gets
`tasks=[task]` from `synthesis_worker` because a compiled subgraph drops the undeclared `task` key.
`with_task_note` skips the note when the query equals the last `HumanMessage`, which is the
single-intent case and every fan-out fallback. The first version added it on both paths, which
restated the traveller's sentence in the system prompt and, after D2 moved the note there, changed
the cached prefix on every single-intent turn for no new information.

## Out of scope

Reflection changes (step 3), prompt caching (step 1, own spec), any change to `synthesize`,
`synthesis_worker` state propagation, or the specialists' own prompts.

## Measurement

Offline: plumbing tests (SC-1…SC-8 in PLAN.md). Value: a new judged rubric `ask_coverage` on two
fan-out goldens, run via `make eval-check` (paid, manual, k=3) before merge — recorded in
SUMMARY `### Not auto-verified` if not run.
