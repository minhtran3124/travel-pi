---
problem_type: bug
module: agent/reflection
tags: langgraph, message-roles, reflection-loop, tool-error-handling, prompt-versioning, uvicorn-reload
severity: critical
applicable_when: Working on LangGraph multi-agent nodes that inject synthetic messages into state["messages"] (e.g. reflection/revision loops, retry prompts) where a prompt rule keys behavior off "the traveller's latest message".
affects:
  - apps/api/app/agents/nodes.py
supersedes: null
confidence: high
confirmed_at: 2026-07-03
---

## Problem

The travel-planning agent silently switched its reply language mid-conversation. A
user asked a question in Vietnamese; the first streamed response was Vietnamese, but
the final persisted answer (after the stream finished) came back in English. Logs
showed the turn passed through the reflection self-critique loop
(`node=reflection revisions=0` -> `reflection -> concierge (revise)`) right before the
language flipped.

## Root Cause

`make_reflection_node` in `apps/api/app/agents/nodes.py` runs a bounded LLM-judge loop:
on a `REVISE` verdict it appends a synthetic instruction ("Please improve your
previous answer.") to `state["messages"]` and routes back to the active sub-agent.
That instruction was wrapped in a `HumanMessage`. The sub-agent's system prompt
(`communication_style` v3) has a hard rule: "Detect the language of the traveller's
LATEST message and always reply in that same language." Because the injected
revision-trigger was a `HumanMessage`, the model treated it as the traveller's actual
latest message (in English) and matched its reply language to it — even though the
real user question, several turns back in message history, was Vietnamese. Any
internal/system-originated message injected as `HumanMessage` risks being misread as
literal user input by prompts that key behavior off "the latest human message."

## Fix

Changed the injected revision-trigger message from `HumanMessage` to `SystemMessage`
in `apps/api/app/agents/nodes.py` (`make_reflection_node`), and made the wording
explicit about its non-user origin: "Please improve your previous answer. This is an
internal review note, not a message from the traveller — keep replying in the
traveller's own language." A `SystemMessage` mid-history is not read as "the
traveller's latest message," so the language-detection rule now correctly keys off the
last real `HumanMessage`. The now-unused `HumanMessage` import was dropped from
`nodes.py`.

## Regression Test

[none] — existing reflection tests (`tests/agents/test_depth_toggles.py`,
`tests/agents/test_supervisor.py`) only assert on `goto`/`revisions` routing outcomes,
not on message role or reply-language preservation across a revision loop. No test
pins that a `REVISE` verdict on a Vietnamese-origin conversation still yields a
Vietnamese final answer.

## Code Example

```python
# apps/api/app/agents/nodes.py — make_reflection_node, on REVISE verdict
return Command(
    update={
        "revisions": revisions + 1,
        "messages": [
            SystemMessage(
                content="Please improve your previous answer. This is an "
                "internal review note, not a message from the traveller — "
                "keep replying in the traveller's own language."
            )
        ],
    },
    goto=target,
)
```

## Prevention

Any message a graph node injects into `state["messages"]` to steer the model — not
authored by the end user — must be a `SystemMessage` (or otherwise clearly
out-of-band), never `HumanMessage`, whenever a prompt rule keys behavior off "the
latest human message" (language detection, intent classification, etc.). When adding
a new synthetic-message injection point in `nodes.py`, grep the active
`communication_style` prompt for rules that reference "latest message" / "last
message" and verify the injected role won't be mistaken for it.

## Related

- [local-postgres-checkpointer](local-postgres-checkpointer.md)
