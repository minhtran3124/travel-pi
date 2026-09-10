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

**D2 — Delivery: a trailing `SystemMessage`, built at invoke time, never stored.**
`_base.py::assistant` passes `[system_msg, *state["messages"], task_note]` to the model. The note
is `TASK_NOTE_PREAMBLE + query`. It is not returned in `{"messages": [...]}`, so it is never
checkpointed or replayed on later turns (the PR #140 replay class). Rejected: `HumanMessage`
(upstream-literal) — `docs/solutions/agent/reflection-humanmessage-language-flip.md`.

**D3 — Scope: both paths, one read.** The specialist always reads `state["tasks"][0]["query"]`.
Single-intent: the supervisor's list. Fan-out: `synthesis_worker` sets `inner_state["tasks"] = [task]`
because a compiled subgraph drops the undeclared `task` key (probe 2026-09-10). Rationale: one code path, and step 3 of the review
(reflection sees the question) can reuse the same text. The single-intent query is usually a
restatement of the user sentence; appended after the history it does not touch the cached prefix.

## Out of scope

Reflection changes (step 3), prompt caching (step 1, own spec), any change to `synthesize`,
`synthesis_worker` state propagation, or the specialists' own prompts.

## Measurement

Offline: plumbing tests (SC-1…SC-8 in PLAN.md). Value: a new judged rubric `ask_coverage` on two
fan-out goldens, run via `make eval-check` (paid, manual, k=3) before merge — recorded in
SUMMARY `### Not auto-verified` if not run.
