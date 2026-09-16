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

Intake only — no code changed yet.

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

- none

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
