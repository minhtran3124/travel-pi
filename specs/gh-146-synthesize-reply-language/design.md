# gh-146-synthesize-reply-language — Design

Status: approved in brainstorming (2026-09-07). Lane: normal. Issue #146.

## Purpose

The `synthesize` node (multi-intent turns) must reply in the conversation language the supervisor detected, like every sub-agent does. Today it replied in Vietnamese to an English turn in 3/3 judged runs.

## Decision (user, brainstorming)

Guard only: apply the existing `with_reply_language(system, state)` (`app/agents/state.py:181`) to the synthesize node's system message, exactly as `subagents/_base.py:255` does. No registry move, no post-check.

Rejected: registry-ising the inline prompt (scope creep for this bug); post-hoc language detection + re-ask (extra LLM call per multi-intent turn).

## Components

| # | File | Change |
| --- | --- | --- |
| 1 | `apps/api/app/agents/nodes.py` (`make_synthesize_node`, lines 160–199) | Inside `synthesize(state)`: `system_msg = with_reply_language(system, state)` and invoke with `[system_msg, HumanMessage(prompt)]`. Keep the `Conversation language:` prose line (harmless). Import `with_reply_language` from `app.agents.state`. |
| 2 | `apps/api/tests/agents/test_synthesize_node.py` (new — no existing test imports `make_synthesize_node`; graph-level tests only assert `current_flow`) | New test: FakeLLM capturing the invoked messages; with `state["language"] == "en"` the first message is a SystemMessage containing `Reply in the traveller's own language: en`; with no language set the system message is unchanged (guard is a no-op). |

## Error behaviour

No new failure modes: `with_reply_language` is a pure function returning the base message when `language` is unset. Note the two fallbacks differ on purpose: the prose line uses `state.get("language", "en")` (always shows a language), the guard fires only when a language was actually detected.

## Tests / success criteria

- SC-1 the two unit tests above pass.
- SC-2 existing synthesize / multi-intent tests still pass (`pytest tests/agents -q -k "synth or multi_intent"`).
- SC-3 (optional, user spend) keyed `python -m eval --suite full --capability budget` on the evalkit branch after merge shows `budget-ambiguous-en-02` `reply_language` = en.

## Out of scope

Prompt registry entry for synthesize; the missing static suggestion map for `synthesize` (separate backlog item from review-b7).
