<!--
  Canonical SUMMARY.md shape (templates/SUMMARY.template.md). Header block is machine-read:
  hooks/risk-corroboration.sh greps `Lane:`; the trust-metrics ledger reads Lane/Confidence/Flags.
-->

# gh-179-synthesize-stream-first-chunk-only — Summary

Lane: normal
Confidence: high
Reason: no manifest hard gate (one branch of the SSE mapper; no auth/authz/data-model/route/provider/high-blast path). 2 flags: existing behavior (the streaming path every chat turn takes) and public contract (the SSE event sequence a client consumes) — the event *taxonomy* does not change, only how many `token` events a fan-out turn produces, which is the defect.
Flags: existing behavior, public contract
Affects: apps/api/app/streaming/mapper.py (the `synthesize` branch of `stream_agent_events`)
Input-type: change request (bug #179, found by UAT while verifying #178/PR #184)
Route: normal — branch off `main` → subagent-driven-development, test-first.
Escalate: no — one interpretation, and the mechanism is proven on the wire before any edit.

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> dinh bang chung UAT vao PR va sang fix 179 de dong tron ven vong

Issue #179 (rewritten title): "Agent SSE: a fanned-out turn streams only the first chunk of the synthesized answer". On any multi-intent turn the SSE stream carries one `token` event holding the first chunk of the answer, so the chat panel renders a single character while `POST /agent/chat` returns the complete text.

## What changed

Nothing yet — intake only.

### The issue as originally filed was mis-scoped, twice

I filed #179 from a screenshot and got both attributions wrong: it is not a frontend defect, and it is
not specific to the clarification (`awaiting_user`) path. Corrected on the issue before starting.

- **Not the frontend.** Counting events on the wire (`POST /agent/stream`, one fan-out turn) gives
  7 `tool_call`, 7 `tool_result`, 3 `panel`, **1 `token` — `{"content":"I"}`**, 1 `done`. The server
  sends one token; the client renders one token.
- **Not clarification.** `synthesize` runs on every fanned-out turn. The turn I screenshotted was
  both fanned out *and* ended in a clarifying question; only the first mattered.

### Cause

`mapper.py`'s `synthesize` branch suppresses every message chunk after the first:

```python
if root is None and node_name == "synthesize":
    if synthesize_answer_emitted:
        continue
```

Its comment states the assumption — *"the synthesize node currently uses `llm.invoke()`, so there is
exactly one meaningful answer event per run"*. `app/clients/llm.py:99` builds every model with
`streaming=True`, and its own comment says *"streaming=True routes invoke through `_stream`"* (it is
set so OpenAI reports `usage_metadata`). So the node streams, LangGraph's `messages` mode yields it
chunk by chunk, and the flag discards chunks 2..N of the same message.

The dedupe intent is real — the finished message does surface again — but "first event only" is the
wrong mechanism once the node streams. The sub-agent branch, twenty lines below, already dedupes by
**message id** and is the model to copy.

### Rationale

Lane `normal`: a single branch in one function, but on the path every chat turn takes, and the SSE
sequence is a client-visible contract. Confidence `high`: the mechanism was measured on the wire
before any code was read, and re-measured against the code that produces it.

### Alternatives considered

- **Abandon the dedupe entirely** — would re-introduce the duplicate answer the flag was added to stop.
- **Fix it in the frontend** (accumulate differently) — would be treating the symptom at the last
  link in the chain; the missing text never leaves the server.

### Deviations

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| a live fan-out turn streams exactly one token event | `curl -sN -X POST localhost:8000/agent/stream ... ; grep -c '^event: token'` | 0 | printed `1`; the token payload is `{"content":"I"}` while `/agent/chat` returns the full answer | |
| every model is built with streaming enabled | `grep -n 'streaming=True' apps/api/app/clients/llm.py` | 0 | line 99, with the comment "streaming=True routes invoke through `_stream`" | |
| the synthesize branch suppresses after the first chunk | `grep -n 'synthesize_answer_emitted' apps/api/app/streaming/mapper.py` | 0 | flag set on the first chunk, `continue` on every later one | |
| the sub-agent branch dedupes by message id instead | `sed -n '200,213p' apps/api/app/streaming/mapper.py` | 0 | compares `msg_id` to `last_msg_id`, emits a `reset` on a genuinely new message | |

### Not auto-verified

- **No fix exists yet**, so no behavioral claim is made about the repaired stream.
- **Whether streamed chunks share one message id** is the assumption the fix rests on. It is
  consistent with the sub-agent branch already relying on it, but it has NOT been measured for the
  synthesize node specifically; the first task is a test that would fail if it were false.
- The `1 token` measurement is from **one** live turn, not a repeated sample.

### Rollback

- `git revert <sha>` — one branch in one function; nothing persisted and no contract change.

### Harness-Delta

- backlog → `compound`: two issues in a row (#178, #179) were filed with a confidently wrong
  mechanism, and both times the wrong link in the chain got the blame. What broke the pattern was
  measuring the boundary *between* components — the ToolMessages the sub-agent received, the events
  on the SSE wire — rather than inspecting the visible end. Worth recording as a debugging rule:
  when a symptom appears at the last link, measure what the previous link emitted before attributing
  the fault.
