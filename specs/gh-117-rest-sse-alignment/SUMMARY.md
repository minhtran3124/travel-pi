# Summary — Align REST and SSE final answer on multi-intent turns

## What changed

- `apps/api/app/routers/agent.py`: REST reply assembly now returns the **last** content-bearing, non-tool-calling `AIMessage` of the current turn, instead of joining every sub-agent answer. This matches the SSE path's "last answer wins" semantics and removes duplication caused by each queued sub-agent regenerating the whole turn answer.
- `apps/api/app/streaming/mapper.py`: `reset` is now emitted **intentionally** when the sub-agent changes, not accidentally because the new sub-agent's `AIMessage` has a different `id`. Reflection revision still emits `reset` as before.
- `apps/api/tests/api/agent/test_agent_chat.py`:
  - Renamed and updated `test_chat_multi_intent_turn_returns_both_subagent_answers` → `test_chat_multi_intent_turn_returns_last_subagent_answer` to assert only the last sub-agent's answer is returned.
  - Added `test_chat_and_stream_yield_same_final_answer_for_multi_intent` driving both `/agent/chat` and `/agent/stream` with the same scripted `FakeLLM` and asserting equal final text.
- `apps/api/tests/api/agent/test_stream_events.py`: Added `test_mapper_emits_reset_on_subagent_handoff` verifying the SSE reset event on supervisor handoff.

## Root cause

The reply assembler assumed each queued sub-agent produced a **slice** of the answer, but each sub-agent is a full ReAct loop that produces a **complete answer** to the whole turn. REST joined these complete answers, causing duplication. SSE only avoided duplication because its `reset` event fired accidentally on message-id change across sub-agents.

## Verification

```bash
.venv/bin/python -m pytest apps/api/tests/ -q
```

Result: `1818 passed, 148 warnings`.

## Issue

<https://github.com/minhtran3124/travel-pi/issues/117>
