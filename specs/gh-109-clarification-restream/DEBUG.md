# Debug — GitHub issue #109

Issue: [Chatbot re-streams the same clarification reply ~3× before completing](https://github.com/minhtran3124/travel-pi/issues/109)

Investigated: 2026-07-22  
Status: root cause confirmed; runtime fix not implemented

## Symptom

For a multi-step request containing an ambiguous date such as “at the end of this
month,” the agent asks for an exact date. The clarification begins rendering, then
the same prefix disappears and restarts one or more times before the complete answer
is shown.

The visible behavior corresponds to this SSE pattern:

```text
token(partial clarification)
tool_call(needs_clarification)
tool_result
reset
token(repeated prefix + complete clarification)
done
```

If the model performs another sequential clarification-tool round, the sequence is:

```text
token → reset → token → reset → token
```

That produces three visible starts, matching the issue report.

## Deterministic reproduction

Run from the repository root:

```bash
.venv/bin/python specs/gh-109-clarification-restream/reproduce.py
```

The probe is offline. It builds the current graph with `FakeLLM`, scripts a planner
response containing both clarification prose and a `needs_clarification` tool call,
then prints the mapped SSE events.

Observed output:

```text
token {'content': 'I can do that — I just need one exact date ...'}
tool_call {'id': 'call-clarify-1', 'name': 'needs_clarification', ...}
tool_result {'id': 'call-clarify-1', 'status': 'ok'}
reset {}
token {'content': 'I can do that — I just need one exact date ... What exact departure date should I use?'}
done {...}
```

## Root cause

The `reset` event has reflection-specific semantics: discard a draft that the
reflection node rejected and replace it with the revised answer. The mapper does not
currently observe a reflection-revision signal. Instead, it uses assistant message-ID
inequality as a proxy:

- `apps/api/app/streaming/mapper.py:144-167` streams every content-bearing specialist
  `AIMessage` and emits `reset` whenever its ID differs from the previous message ID.
- `apps/api/app/agents/subagents/_base.py:103-146` implements specialists as ReAct
  loops: `assistant → tools → assistant`.
- `needs_clarification` is appended to every specialist at
  `apps/api/app/agents/subagents/_base.py:95-98`.
- `apps/api/app/tools/clarification_tools.py:22-55` returns a `ToolMessage` instructing
  the model to finish by asking for the missing detail. Tool execution therefore
  returns control to the assistant normally.

A provider may legally return prose and tool calls in the same assistant message.
The mapper streams that pre-tool prose. After the tool result, the assistant creates
the complete clarification as a new message with a new ID. The generic ID-change
heuristic emits `reset`, although reflection never rejected the first message.

Additional assistant/tool rounds create additional false resets.

## Frontend behavior

The frontend is behaving according to the current SSE contract:

- `apps/web/src/lib/stream/parseSSE.ts:192-198` maps each wire `reset` once.
- `apps/web/src/components/chat/useAgentStream.ts:341-345` forwards the reset to the
  reveal controller during a normal send. Resume and explicit retry use the same path.
- `apps/web/src/components/chat/smoothReveal.ts:84-88` cancels the animation, drops
  buffered text, and clears the rendered assistant message.

That deliberate clearing makes the invalid backend reset appear as a flash and
restart. Client-side prefix deduplication would hide the symptom without repairing
the event semantics.

## Ruled out

### Reflection re-running clarification

Current HEAD stops this path correctly:

- `apps/api/app/agents/nodes.py:264-275` abandons queued ledger work when
  `awaiting_user` is true.
- `apps/api/app/agents/nodes.py:170-178` ends reflection immediately for an
  awaiting-user turn.

Reflection is therefore not responsible for the deterministic current-HEAD reset.

### Browser reconnect or automatic retry

The client uses one `fetch` request and reads its `ReadableStream`; it does not use an
auto-reconnecting `EventSource`. Retry is an explicit user action, and duplicate sends
are guarded by the in-flight request state.

### React Strict Mode

Sending is event-driven rather than effect-driven. Effect cleanup aborts and disposes
the active stream; it does not start another request. Strict Mode is not the source of
the repeated SSE frames.

## Relationship to issue #99

Issue #99 exposed the same ambiguous-date request while the old task ledger drained
`planner → concierge → planner → budget`. That could produce three message-ID changes
and closely matches the original “~3×” observation.

The MIN-68 fix now abandons queued work and skips reflection after clarification. It
removes that amplifier, but it does not repair the mapper heuristic. A normal
`assistant → needs_clarification → assistant` round still reproduces an invalid reset
on current HEAD.

## Test gap

- `apps/api/tests/api/agent/test_stream_events.py:191-199` positively expects a reset
  for any new assistant message ID; it does not establish that reflection caused the
  ID change.
- `apps/api/tests/agents/test_ledger_early_exit.py` scripts the tool-calling response
  with empty content and uses buffered invocation, so it cannot observe a streamed
  preamble or reset.
- Genuine reflection-reset coverage exists in
  `apps/api/tests/api/agent/test_agent_chat.py:343-367`, but it does not distinguish
  reflection from ordinary ReAct tool rounds at the mapper boundary.
- Frontend parser coverage confirms that `reset` is decoded, but there is no
  end-to-end clarification stream fixture asserting monotonic rendering.

## Recommended fix boundary

1. Replace generic message-ID reset detection with an explicit signal that reflection
   rejected a draft and started a revision.
2. Avoid exposing assistant prose whose completed message contains tool calls. Buffer
   an assistant invocation until its completed update establishes whether it is a
   tool-calling message; discard pre-tool prose and stream the final no-tool answer.
3. Add a full graph/SSE regression using a content-bearing `needs_clarification` tool
   call followed by the final clarification. Assert exactly one monotonic answer and
   zero resets.
4. Preserve a separate regression asserting exactly one reset for a genuine
   reflection revision.

Do not fix only in the frontend. The server should not label ordinary tool-loop
messages as superseded reflection drafts, and masking them in the UI could conceal
duplicated graph or tool execution.

## Verification run

| Check | Command | Result |
|---|---|---|
| Offline reproduction | `.venv/bin/python specs/gh-109-clarification-restream/reproduce.py` | Confirmed invalid `reset` on current HEAD |
| Backend mapper tests | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_stream_events.py -q` | 21 passed |
| Frontend SSE parser tests | `cd apps/web && /Users/minhtran/.nvm/versions/node/v24.17.0/bin/node /Users/minhtran/.nvm/versions/node/v24.17.0/lib/node_modules/corepack/dist/pnpm.js vitest run src/lib/stream/parseSSE.test.ts` | 21 passed |
| Reproducer lint | `.venv/bin/ruff check specs/gh-109-clarification-restream/reproduce.py` | Passed |

## Separate observation

The deterministic probe also emits the same `tool_result` twice for the clarification
tool call. That duplication is not required to explain the visible text restart and
was not expanded into this issue's fix scope.
