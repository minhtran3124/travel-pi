# rag-tool-output-wrapping — Summary

Lane: high-risk
Confidence: high
Reason: audit/security hard gate — this is prompt-injection defence on every tool result and every retrieved document that reaches the model, and it changes the shape of what all five specialists read back from their tools.
Flags: audit/security, existing-behavior, multi-domain, weak-proof
Affects: apps/api/app/agents/subagents/_base.py (the `ToolNode` construction — two branches, `:278` and `:283`, in one function shared by all five specialists), apps/api/app/tools/rag_tools.py, the five hand-built `ToolMessage` sites (`_base.py:151` trip guard, clarification_tools.py:55, trip_tools.py:547 and :583, agents/retry.py:226), apps/api/app/prompts/communication_style/, apps/api/eval/ goldens
Input-type: change request
Route: brainstorming → xia2 (Deep) → writing-plans → using-git-worktrees → subagent-driven-development
Escalate: no — this reopens the deferral recorded as E001 in `specs/memory-poisoning-hardening/ESCALATIONS.md`; the owner reopened it and decided both open questions in the same turn (new spec + PR rather than extending PR #214; wrap every tool output rather than only externally-authored ones).

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

hold on cho bọc mem của rag + tool

(Decisions taken in the same turn, in answer to two questions: deliver as a **new spec + PR**, leaving PR #214 and its review receipt intact; and wrap **every tool output**, not only the tools whose results carry third-party prose.)

This completes the second proposal bullet of `docs/reviews/2026-09-15-threat-intel-review.md` §1,
which asked to wrap "memory / RAG / tool output" and which the memory spec deliberately narrowed to
memory only:

> - Bọc memory / RAG / tool output trong khối có nhãn rõ *"dữ liệu người dùng, không phải chỉ thị hệ thống"*.

## What changed

In progress (waves 1-2 of 3 complete; see `PLAN.md` Status Log for full detail):

- `app/core/text.py` `escape_angle_brackets`; `app/agents/tool_output.py` (new) `wrap_tool_output` /
  `strip_wrappers`; `communication_style` prompt v8 → v9; summarizer system prompt gains one line
  (wave 1).
- Eval adapter (`eval/adapters/langgraph_runner.py`) strips the wrapper before pairing tool output
  for judging (wave 2, task 2.2).
- The `"tools"` node in `build_subagent` (`app/agents/subagents/_base.py`) now wraps every tool
  result as `<tool_output name="...">...</tool_output>` (escaped, not deleted) via a callable
  registered in place of the bare `ToolNode` — **not** the hook or node seam the design originally
  proposed; see `### Intent Findings` below (wave 2, task 2.1).

Remaining: wave 3 (RAG-specific proof, task 3.1), then the review chain and PR.

### Rationale

The memory half shipped in PR #214 closes the *persistence* channel: the extractor no longer reads
ToolMessages, so tool text can no longer become a standing instruction. What it does not close is
the *live turn* — a retrieved document or a tool result still reaches the model as unlabelled text
in the same position as the assistant's own instructions. Two facts from the intake survey decide
the shape of the work: there is exactly one `ToolNode` wiring (`subagents/_base.py:278,283`) and
langgraph has already collapsed every tool return shape to a string by the time it becomes a
`ToolMessage`, so one chokepoint covers all five specialists; but four sites build a `ToolMessage`
by hand and bypass that node entirely, so "wrap at ToolNode" is not the same guarantee as "every
ToolMessage is labelled".

### Alternatives considered

- Extend PR #214 — rejected by the owner: it would invalidate the pinned review receipt and force
  the whole final review chain to re-run on a larger diff.
- Wrap only the tools whose results carry third-party prose (RAG, hotel/place descriptions, tips,
  visa summaries) — rejected by the owner in favour of covering every tool output, since any tool
  can start interpolating externally-authored text without the classification list being updated.

### Deviations

- none (Rule 1-3 auto-fixes). Two in-flight escalations changed the plan itself rather than the
  implementation — see `### Intent Findings`.

### Intent Findings

- **Drift (material, escalated and resolved in-flight — E001, E002 in `ESCALATIONS.md`).** The
  approved design's seam (langgraph's `wrap_tool_call`/`awrap_tool_call` hook on `ToolNode`) was
  measured, during task 2.1's implementation, to disarm `TRANSIENT_RETRY` + `graceful_fallback` for
  planner and concierge — the two specialists doing real external I/O, i.e. the highest-value
  injection surface this spec targets. The first replacement (a `label_tools` node after `tools`)
  was also measured broken: it adds a super-step per tool round that overruns
  `agent_recursion_limit` on an existing test. The shipped seam wraps the `"tools"` node's own
  callable instead — same node, same edges, no added super-step, exception propagation untouched.
  Behavior at the boundary (every tool result wrapped as data-not-instructions) is unchanged from
  intent; only the internal mechanism moved, twice, under measurement. Both escalations and their
  evidence are recorded in `specs/rag-tool-output-wrapping/ESCALATIONS.md`.
- **Advisory (four Minor findings from task 2.1's review, none blocking):** `_label_one`'s
  exception guard covers only the wrap call, not the surrounding `model_copy`; `create_trip`'s D3
  coverage is unit-level, not graph-level (the identity assertion is the real protection either
  way); the idempotence prefix is coupled to the tag constant by convention, not by construction;
  and `test_booking_turn_no_revise.py` needed an out-of-file `strip_wrappers` fix (commit e914eb00)
  once tool output started arriving wrapped. Full detail in `PLAN.md` Status Log.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| intake lane evidence | `python3 .claude/scripts/verify_summary.py --lane rag-tool-output-wrapping` | 0 | intake-time lane check | |

### Not auto-verified

- The intake survey's claims about chokepoints and bypass sites — reached traceability (read at intake); no behaviour re-run yet.

### Rollback

- `git revert <sha>` (intake artifacts only)

### Harness-Delta

- none
