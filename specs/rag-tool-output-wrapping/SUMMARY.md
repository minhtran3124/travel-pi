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
- `apps/api/tests/tools/test_rag_output_wrapping.py` (new) proves the escaping chokepoint covers
  retrieved documents through a compiled graph; `app/tools/rag_tools.py` is unchanged (design D2,
  wave 3, task 3.1).

All three waves complete. Remaining: the final review chain, `.review-receipt.json`,
`verify_summary.py --check`, then `finishing-a-development-branch`.

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

- Rule 1 — `_label_tool_outputs`' `list`-shape branch matched only a bare `ToolMessage`, but
  `ToolNode._combine_tool_outputs` emits `{"messages": [ToolMessage]}` for every non-`Command`
  entry when `input_type == "dict"` (always true here), so a batch mixing a `Command`-returning
  tool with an ordinary tool left the ordinary tool's result unescaped and unwrapped. Found by
  5/6 correctness-review FIND angles independently (each via direct execution against the
  installed langgraph), scored 75/100, fixed by recursing into `dict` entries, re-reviewed and
  closed — the re-review ran the new test against the reconstructed pre-fix code and confirmed it
  fails there, so the test pins the fix rather than coincidentally passing. `app/agents/subagents/_base.py`, `apps/api/tests/agents/test_tool_output_wrapping.py`. Commit `968812af`.
- Two in-flight escalations changed the plan itself rather than the implementation — see
  `### Intent Findings`.

### Advisory Findings (correctness-review, scored below the 75 fix-loop threshold)

Full branch review, `.harness-state/sdd/package-branch-final.md` (BASE `68836c23`..HEAD `ffe80e5b`
pre-fix; finding above fixed at `968812af`). Six independent FIND angles, one independent score per
deduplicated location — none blocking, all below threshold:

| Score | Location | Finding |
| --- | --- | --- |
| 50 | `_base.py:114` | The "already wrapped" skip is a content sniff (`startswith("<tool_output ")`) rather than a provenance flag; a payload starting with that literal token would bypass escaping. No shipped tool can reach it today (every `-> str` tool return starts with a fixed first-party prefix; every dict/list return is JSON-serialized first). |
| 50 | `_base.py:86-90` | Docstring justifies `model_copy` via "`add_messages` upserts by id", but `ToolNode`'s messages have `id=None` at this point and `add_messages` assigns a fresh id — the actual protection is that the original is never separately appended, not id-upsert. No runtime bug; a wrong invariant statement. |
| 50 | `text.py:60` + `v9.md` | `escape_angle_brackets` escapes every `<`/`>` in tool content, and v9 forbids reversing it, so a legitimate value with a bracket (a price note, a layover time) could reach the traveller as `&lt;`/`&gt;` literally. No seeded catalog data with angle brackets found; the web client's markdown renderer decodes entities back for the reader, so impact is limited to non-markdown consumers. |
| 25 | `_base.py:106-111` | Non-`str` tool content (a block-list shape, or an empty list) fails open (passed through unlabelled) rather than failing closed like the memory guard's precedent. No current tool can produce a non-empty block-list `ToolMessage`; a code comment justifying this also cites the wrong test (an `AIMessage` test, not a `ToolMessage` one) — cosmetic, fixed as part of this note. |
| 25 | `v9.md` + `place_tools.py`/`hotel_tools.py` | Some tools embed first-party anti-hallucination / sold-out guard text inside a *successful* return, which this diff now wraps identically to untrusted content; v9's "disregard in-block instructions" language is scoped to role/rule-changing requests, not general guard text, so a live regression is plausible but unconfirmed — would need an eval case to demonstrate. |
| 25 | `_base.py:103` | The new `status == "error"` skip forwards `str(exc)` verbatim (via `describe_tool_failure`); no shipped exception path was found carrying externally-sourced text today, so this is a theoretical, not demonstrated, gap. |
| 25 | `langgraph_runner.py:142-157` | `_serialize_message` (pre-existing, unmodified) does not strip the wrapper the way `_pair_tool_calls` (new) does, so `Trace.messages` and `Trace.tool_calls[].output` render the same tool result differently. No current consumer reads `Trace.messages[].content` for a `ToolMessage` — dormant, not live. |
| 0 | `state.py:215` | Wrapped/escaped tool text can be laundered through the summarizer into `state["summary"]`, which is injected into every future system prompt unescaped and untagged. Pre-existing behavior (both the summarizer transcript build and `system_with_summary`'s summary injection are unchanged by this diff) — the new prompt line is an *incomplete* mitigation of a gap that predates this spec, not a new regression. |
| 0 | `langgraph_runner.py:95-111` | Eval strip doesn't unescape entities, so byte-identity only holds for content with no angle brackets — exactly the scope SC-7 and the test already declare; not a defect. |

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
- **Drift (material, escalated and resolved — E003 in `ESCALATIONS.md`).** Intent-review flagged
  that design D3 (no wrapping for `status == "error"` messages or `Command`-carried messages)
  narrows the owner's verbatim decision "wrap every tool output" — concretely, `create_trip`'s
  successful result (model/traveller-supplied `title`/`city`, delivered inside a `Command`) and the
  entire error channel stay unwrapped. Owner decision: **keep D3 as-is** — both carve-outs are
  first-party control/recovery text, not third-party content, and the narrowing is now documented
  in design.md rather than left implicit. No code change.
- **Advisory, open (E004 in `ESCALATIONS.md`, pending `make eval-smoke`).** Prior-art found that
  v9's "disregard in-block instructions" carve-out is scoped to role/rule-changing requests, not to
  the anti-hallucination / sold-out guard text some tools embed in a successful return — which this
  spec now wraps like any other tool content. Correctness-review scored this 25/100 (plausible,
  unconfirmed). Owner decision: run `make eval-smoke` on a zero-result search case before deciding
  whether v9 needs a carve-out — `apps/api/.env` is not present in this worktree, so the run is
  blocked pending owner action (supply the env file, or run from the main checkout and report back).
- **Advisory (four Minor findings from task 2.1's review, none blocking):** `_label_one`'s
  exception guard covers only the wrap call, not the surrounding `model_copy`; `create_trip`'s D3
  coverage is unit-level, not graph-level (the identity assertion is the real protection either
  way); the idempotence prefix is coupled to the tag constant by convention, not by construction;
  and `test_booking_turn_no_revise.py` needed an out-of-file `strip_wrappers` fix (commit e914eb00)
  once tool output started arriving wrapped.
- **Advisory (four Minor findings from task 3.1's review, none blocking):** the wrapper's `name`
  attribute is not pinned to the specific tool in the escaping test; the structural test depends on
  production `strip_wrappers` as its own inverse rather than a bracket-agnostic parse; nothing
  asserts the negative case (the raw tool itself returns unescaped text); the fake `hybrid_search`
  signature is looser than the real keyword-only one. A stale docstring in `app/agents/tool_output.py`
  still naming "the hook" as the sole caller (left over from E001/E002) was fixed directly (Rule 1).
  Full detail in `PLAN.md` Status Log.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| intake lane evidence | `python3 .claude/scripts/verify_summary.py --lane rag-tool-output-wrapping` | 0 | intake-time lane check | |
| escape primitive | `.venv/bin/python -m pytest apps/api/tests/core/test_text_escape.py -q` | 0 | idempotent, leaves `&` and `[`/`]` alone | SC-1 |
| wrap/strip helpers + delimiter forgery | `.venv/bin/python -m pytest apps/api/tests/agents/test_tool_output.py -q` | 0 | | SC-2 |
| duplicate-booking marker survives wrapping | `.venv/bin/python -m pytest apps/api/tests/agents/test_tool_output.py -q -k marker` | 0 | | SC-3 |
| tools-node wrapping (sync+async, both branches, mixed batch) | `.venv/bin/python -m pytest apps/api/tests/agents/test_tool_output_wrapping.py apps/api/tests/agents/test_trip_guard.py apps/api/tests/agents/test_prompt_map.py -q` | 0 | 61 passed post-fix `968812af` | SC-4 |
| communication_style v9 active + retention pins | `.venv/bin/python -m pytest apps/api/tests/prompts/test_active_versions_load.py -q` | 0 | | SC-5 |
| summarizer keeps tags | `.venv/bin/python -m pytest apps/api/tests/memory/test_summarizer_tool_labels.py -q` | 0 | | SC-6 |
| eval adapter strips wrapper, byte-identical when no brackets | `.venv/bin/python -m pytest apps/api/tests/ev*l/test_langgraph_runner.py -q` | 0 | 37 passed | SC-7 |
| lint | `.venv/bin/ruff check apps/api/app apps/api/ev*l` | 0 | | SC-8 |
| RAG documents arrive escaped through the real graph | `.venv/bin/python -m pytest apps/api/tests/tools/test_rag_output_wrapping.py -q` | 0 | 11 passed | SC-9 |
| fault-tolerance regression guard (E001) | `.venv/bin/python -m pytest apps/api/tests/agents/test_subagent_fault_tolerance.py -q` | 0 | flaky tool retries 3x, degrades via graceful_fallback | |
| full branch fallout | `.venv/bin/python -m pytest apps/api/tests/agents -q` | 0 | 512 passed | |

### Not auto-verified

- The intake survey's claims about chokepoints and bypass sites — reached traceability (read at intake); no behaviour re-run yet.

### Rollback

- `git revert <sha>` (intake artifacts only)

### Harness-Delta

- none
