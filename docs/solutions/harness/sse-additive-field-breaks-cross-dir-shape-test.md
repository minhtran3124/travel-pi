---
problem_type: failure
module: harness/testing
tags: wave-verify, contract-test, sse, exact-shape-assert, blast-radius, test-partition, streaming
severity: standard
applicable_when: A wave task adds a field to a shared event/DTO factory while exact-shape (==) assertions on that payload live in a test file in a different directory than the changed module.
affects:
  - apps/api/tests/api/agent/test_stream_events.py
supersedes: null
confidence: high
confirmed_at: 2026-07-08
---

## Applicable When

Adding a field to a shared event/DTO factory (e.g. `apps/api/app/streaming/events.py`
`panel()` / `done()`) when there exist exact-shape `==` assertions on that payload in a test
file that lives in a **different directory** from the changed module.

## Symptom

The additive (superset) payload broke three `_payload(ev) == {...}` assertions in
`apps/api/tests/api/agent/test_stream_events.py`. The wave's `<verify>` only ran
`tests/streaming`, so the break went undetected and rode along silently for **two waves**
before a later task's broader run surfaced it.

## Wrong Approach

Scoping the wave `<verify>` to the changed module's own test directory (`tests/streaming`)
and assuming an additive field is backward-compatible for every consumer.

## Why It Failed

Exact-shape `==` assertions are a **contract test**: any added key breaks them even though
the change is additive/superset. The contract test for `events.py` lived under
`tests/api/agent/`, was in no task's `<files>`, and was not exercised by the wave verify —
so nothing flagged it. This is adjacent to but not the same as
[[wave-shared-file-partition]] (two subagents *colliding* on one shared file); here a change
in module A broke a stranded contract test for A that no task owned or ran.

## Correct Approach

When a change adds a field to a shared factory/DTO:
1. `grep` for exact-shape assertions on that payload across the **whole** test tree
   (`== {` on the event/DTO, not just the module's own test dir).
2. Add the owning test file to the task's `<files>`.
3. Include its directory in the `<verify>` command, regardless of where it sits relative to
   the source module.

## Guardrail

`proposed:` A task that edits a shared event/DTO factory must (a) list every `== {...}`
shape-assertion test for that payload in its `<files>`, and (b) run those test dirs in
`<verify>`. Cross-directory contract tests are not covered by a module-local verify — the
blast-radius hook flags the file edit, but nothing flags an *un-run* contract test.

## Related

- docs/solutions/harness/wave-shared-file-partition.md
