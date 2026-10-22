# SUMMARY — gh-109-clarification-restream

Lane: normal
Confidence: high
Reason: Read-only investigation spans the backend graph/SSE layer and frontend stream/render layer; no runtime code or public contract changes are authorized.
Flags: existing-behavior, cross-layer
Affects: agent clarification streaming only
Input-type: Investigation request
Route: normal → parallel read-only traces → evidence synthesis
Escalate: no

### Intent

Investigate GitHub issue #109 and determine why clarification replies visibly restart
several times before completing.

### Rationale

The same UI symptom can be caused by duplicate backend graph emissions, SSE `reset`
events, multiple browser requests, or frontend buffer replacement. The investigation
therefore traces the full path before recommending a fix.

### Alternatives

- Patch the UI to deduplicate repeated prefixes immediately — rejected because it could
  hide duplicate agent executions and duplicated side effects.
- Patch the backend stream mapper immediately — rejected until the emitted event sequence
  is established.

### Files touched

- `specs/gh-109-clarification-restream/PLAN.md`
- `specs/gh-109-clarification-restream/DEBUG.md`
- `specs/gh-109-clarification-restream/SUMMARY.md`
- `specs/gh-109-clarification-restream/reproduce.py`

### Findings

- **Confirmed root cause:** `apps/api/app/streaming/mapper.py` emits `reset`
  whenever a content-bearing sub-agent `AIMessage` has a different ID from the
  previous one. The event contract says `reset` means a reflection-rejected draft,
  but message IDs also change during normal ReAct `assistant → tool → assistant`
  rounds.
- `needs_clarification` is a tool in every specialist. A model may legally emit a
  prose preamble together with that tool call, then emit the complete clarification
  after the tool result. The mapper streams the preamble, sees the post-tool message's
  new ID, emits `reset`, and streams the repeated prefix again. Repeated sequential
  calls produce `token → reset → token → reset → token` (three visible starts).
- The browser does not reconnect or duplicate events. It parses each reset once and
  `smoothReveal.reset()` deliberately cancels buffered reveal text and blanks the
  assistant bubble, making the backend reset visibly flash/restart.
- Current `awaiting_user` guards correctly abandon queued ledger work and skip
  reflection. Therefore reflection is not re-invoking the clarification node on
  current HEAD. The closed #99 likely explains the original four-specialist/~3-reset
  observation, but its fix does not repair the overbroad mapper heuristic; current
  HEAD still reproduces an invalid reset inside a clarification tool loop.
- Existing tests encode the gap: the mapper test expects a reset for any new message
  ID, while clarification fixtures use an empty-content tool-call response and a
  buffered graph invocation, so they cannot observe re-streaming.

### Recommendation

- Preserve `reset` for genuine reflection revisions, but key it to an actual
  reflection-revision signal instead of generic message-ID inequality.
- Do not expose tool-calling assistant preambles as final answer prose. Buffer an
  assistant invocation until its completed update establishes whether it contains
  tool calls; discard pre-tool prose and stream only the final no-tool answer.
- Add a full graph/SSE regression with a content-bearing `needs_clarification` call
  followed by the final question. Assert one monotonic clarification, zero resets,
  and retain the existing genuine-reflection reset assertion.
- Do not solve this only with frontend prefix deduplication; that would hide incorrect
  server semantics and could mask duplicate agent/tool execution.

### Verify

| Check | Command | Exit | Notes |
|---|---|---|---|
| Backend mapper tests | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_stream_events.py -q` | 0 | 21 passed; required running outside the filesystem sandbox because `pytest-rerunfailures` binds a localhost status socket |
| Frontend SSE parser tests | `cd apps/web && /Users/minhtran/.nvm/versions/node/v24.17.0/bin/node /Users/minhtran/.nvm/versions/node/v24.17.0/lib/node_modules/corepack/dist/pnpm.js vitest run src/lib/stream/parseSSE.test.ts` | 0 | 21 passed |
| Offline current-graph probe | `.venv/bin/python specs/gh-109-clarification-restream/reproduce.py` | 0 | Observed `token(partial) → tool_call → tool_result → reset → token(complete) → done`; a two-call variant observed two resets/three visible starts |
| Reproducer lint | `.venv/bin/ruff check specs/gh-109-clarification-restream/reproduce.py` | 0 | Clean |
| Investigation artifact check | `git diff --check -- specs/gh-109-clarification-restream` | 0 | Clean |

### Deviations

- None.

### Blockers

- No raw SSE capture was attached to #109 and no live-provider/browser run was needed;
  the current-HEAD offline graph reproduction is deterministic and sufficient to
  confirm the mapper defect.

### Rollback

- Documentation-only investigation: remove `specs/gh-109-clarification-restream/` if the record is not wanted.
