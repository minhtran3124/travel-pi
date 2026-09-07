# gh-146-synthesize-reply-language — Summary

Lane: normal
Confidence: medium
Reason: 2 flags (existing behavior — the synthesize node's reply contract; weak proof — language choice is an LLM behaviour, reproduced by golden budget-ambiguous-en-02 in three of three runs). No manifest hard gate. Likely two or more files (nodes.py + tests, possibly moving the inline synthesize prompt into the prompt registry), so not tiny.
Flags: existing behavior, weak proof
Affects: apps/api/app/agents/nodes.py (`make_synthesize_node`, inline SystemMessage at nodes.py:169-192), apps/api/app/agents/state.py (`with_reply_language`), apps/api/tests/agents/*; prompt registry only if the design moves the inline prompt there
Input-type: change request (bug #146)
Route: normal, user asked for design + plan — brainstorming → xia2 (Standard) → writing-plans → using-git-worktrees (branch `fix/gh-146-synthesize-reply-language` off `main`) → subagent-driven-development.
Escalate: no (medium confidence: safe default is applying the existing `with_reply_language(system, state)` guard to the synthesize node, which every sub-agent already gets via `_base.py:255`; the fork is whether to also register the inline prompt in the registry)

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> cho bug agent #155, #146, #153. each item make design + plan to fix - new branch for each fixing

Issue #146 (opened 2026-09-07 from the review-b7 eval run): golden `budget-ambiguous-en-02` — "Compare Hanoi and Ho Chi Minh City for a 5-day trip: food, culture, and budget" (en). The supervisor fanned out to parallel workers and the `synthesize` node replied in Vietnamese (`reply_language` expected en, detected vi) in all three judged runs. Single-specialist turns honour the language; the synthesize path builds its own inline SystemMessage (nodes.py:169) and passes `Conversation language: {language}` as prose in the human prompt, but does not go through `with_reply_language`, the centralised guard every sub-agent gets (state.py:181, _base.py:255).

## What changed

`make_synthesize_node` now applies `with_reply_language(system, state)` inside `synthesize()` on every call, so the multi-intent synthesis reply carries the same system-level language directive every sub-agent gets (`app/agents/nodes.py`, +6/−2). New `tests/agents/test_synthesize_node.py` captures the outgoing messages with a `CapturingLLM(FakeLLM)` and asserts the directive is present when `state["language"] == "en"` and absent when no language was detected. No prompt registry change, no post-hoc detection.

### Rationale

The repo already has one mechanism for reply language (memory: agent-reply-language-centralized-default-en) and the synthesize node is the one LLM-writing node that bypasses it; reusing it is the lightest fix. The design question is only whether to fold the inline synthesize prompt into the versioned prompt registry while touching it (the review's item 8 notes prompt-versioning gaps).

### Alternatives considered

- Strengthen the prose hint (`Conversation language: vi`) in the human message — that is what fails today; a system-level directive is what the other nodes rely on.
- Post-process: detect language of the synthesized answer and re-ask — doubles cost on every multi-intent turn; rejected unless the guard alone proves insufficient.

### Deviations

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| Trigger corroborated (intake) | `<intake-era: grep -n with_reply_language apps/api/app/agents/nodes.py returned exit 1 before the fix>` | 1 | the synthesize node never applied the guard | |
| SC-1 unit test | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_synthesize_node.py -q` | 0 | 2 passed | SC-1 |
| SC-2 graph-level unchanged | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_multi_intent_routing.py tests/agents/test_task_ledger.py tests/agents/test_plan_everything.py -q` | 0 | 18 passed | SC-2 |
| SC-3 lint | `cd apps/api && ../../.venv/bin/ruff check app/agents/nodes.py tests/agents/test_synthesize_node.py` | 0 | | SC-3 |

### Not auto-verified

- Language of a real multi-intent reply — reached traceability (the directive is now in the system message, proven by the FakeLLM test); a keyed `--capability budget` run to watch `budget-ambiguous-en-02` flip is user spend and not run here.

### Rollback

- `git revert b548859 5fcab8f` on `fix/gh-146-synthesize-reply-language`.

### Harness-Delta

- none
