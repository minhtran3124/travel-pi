---
slug: gh-146-synthesize-reply-language
status: active
owner: Minh Tran
created: 2026-09-07
---

# Synthesize node replies in the detected conversation language

## 1. Motivation

Issue #146: on multi-intent turns the `synthesize` node replied in Vietnamese to an English message (`budget-ambiguous-en-02`, 3/3 judged runs). Every sub-agent pins its reply language through `with_reply_language(system, state)` (`app/agents/subagents/_base.py:255`); the synthesize node builds its own inline `SystemMessage` and skips that guard. Design: `design.md` (approved). Research: `research-brief.md` (Standard).

## 2. Non-goals

- No move of the inline synthesize prompt into the prompt registry.
- No post-hoc language detection or re-ask.
- No change to `with_reply_language` itself or to any sub-agent.

## Global Constraints

- Branch `fix/gh-146-synthesize-reply-language` off `main`, in an isolated worktree (`using-git-worktrees`); the main checkout stays untouched.
- Files touched: `apps/api/app/agents/nodes.py` and the new `apps/api/tests/agents/test_synthesize_node.py` only.
- Run backend commands from `apps/api/` with `../../.venv/bin/python`; no `.env` copy in the worktree (dotenv secrets break `monkeypatch.delenv` tests).
- Apply the guard **inside** `synthesize(state)` (per call); never mutate the module-level `system` built once in `make_synthesize_node`.
- Stage and commit as separate commands; no tooling trailers in commit messages.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|------|-------------------------|-----------------------|------------|
| SC-1 | With `state["language"] == "en"`, the synthesize node's first outgoing message is a `SystemMessage` containing `Reply in the traveller's own language: en`; with no language set it is unchanged | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_synthesize_node.py -q` | exit 0 |
| SC-2 | Graph-level multi-intent behaviour is unchanged (synthesize still runs and ends the turn at `current_flow == "synthesize"`) | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_multi_intent_routing.py tests/agents/test_task_ledger.py tests/agents/test_plan_everything.py -q` | exit 0 |
| SC-3 | Lint is clean on the touched files | `cd apps/api && ../../.venv/bin/ruff check app/agents/nodes.py tests/agents/test_synthesize_node.py` | exit 0 |

A keyed `python -m eval --suite full --capability budget` run (evalkit branch, user spend) is the only proof on a real model; it is not an SC row and is listed under SUMMARY `### Not auto-verified`.

## 4. Tasks

### Task 1.1 — Unit test for the synthesize node's outgoing system message (wave 1)

- **Files:** apps/api/tests/agents/test_synthesize_node.py
- **Action:** Test first. Create the file with the `CapturingLLM(FakeLLM)` idiom from `tests/agents/test_state.py:222-230` (override `_generate` to stash `messages`). Build the node directly: `node = make_synthesize_node(capturing)` (import from `app.agents.nodes`), call `node({"task_results": [{"agent": "budget", "findings": "x", "index": 0}], "language": "en", "messages": []})`. Assert (a) `captured["messages"][0]` is a `SystemMessage` whose content contains `Reply in the traveller's own language: en` and still contains `Combine the specialist findings`; (b) `captured["messages"][1]` is a `HumanMessage` containing `Conversation language: en`; (c) the returned dict has `current_flow == "synthesize"`. Second test: same call with no `language` key → the system message does not contain `Reply in the traveller's own language`. Both tests fail before Task 1.2 (assertion (a) fails) and pass after.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_synthesize_node.py -q`
- **Done:** File exists with the two tests; before Task 1.2 the first test fails on assertion (a) and the second passes; after Task 1.2 both pass (exit 0).
- **Criteria:** SC-1
- **Interfaces:** Consumes the pre-existing make_synthesize_node factory (app/agents/nodes.py:161) and the FakeLLM test model (app/clients/llm.py:165). Produces `tests/agents/test_synthesize_node.py`.

### Task 1.2 — Apply the reply-language guard in the synthesize node (wave 2)

- **Files:** apps/api/app/agents/nodes.py
- **Action:** Extend the import at line 32 to `from app.agents.state import TravelAgentState, with_reply_language`. Inside `synthesize(state)` (line 179 onward), before the invoke: `system_msg = with_reply_language(system, state)` and change line 193 to `llm.invoke([system_msg, HumanMessage(content=prompt)])`. Add a two-line comment mirroring `_base.py:252-254` (one detection, one source of truth; also covers a reflection REVISE re-entering this node). Keep the `Conversation language:` prose line and everything else unchanged.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_synthesize_node.py tests/agents/test_multi_intent_routing.py -q`
- **Done:** Both new tests pass; `tests/agents/test_multi_intent_routing.py` passes unchanged; `../../.venv/bin/ruff check app/agents/nodes.py` reports 0 findings; `git diff --stat` shows only `app/agents/nodes.py` (plus the Task 1.1 test file).
- **Criteria:** SC-1, SC-2, SC-3
- **Interfaces:** Consumes `tests/agents/test_synthesize_node.py` from Task 1.1 (the failing assertion it must turn green) and the pre-existing with_reply_language guard (app/agents/state.py:181, unchanged). Produces `app/agents/nodes.py` (synthesize node with the guard).

## 5. Risks

- **Directive may not be sufficient on a real model** — worker findings written in Vietnamese could still dominate; only a keyed run shows this. Mitigation: the SUMMARY records the keyed run as not auto-verified; issue #146 stays open until a real run confirms.
- **Reflection REVISE path** re-enters `synthesize` (nodes.py comment at 196-199); the guard applies there too — desired, but it means a REVISE cannot flip the language either, which is the intended behaviour.
- **Test brittleness on prompt wording** — assertions match the guard's fixed sentence (`Reply in the traveller's own language: en`), already asserted by `test_state.py`, not the synthesize prose.

## 6. Status Log

- 2026-09-07 — plan written after design.md approval and a Standard research brief; not yet executed.
- 2026-09-07 — design approved (spec reviewer ✅), research-brief Standard, PLAN reviewed ✅ (independent pass); not yet executed
- 2026-09-07 — tasks 1.1, 1.2 complete; commits 5fcab8f, b548859 (review pass/approved)
