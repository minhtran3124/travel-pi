# SUMMARY — agent-side-panel

**Lane:** normal
**Confidence:** high
**Reason:** Multi-file, multi-layer (service → schema → streaming → FE) but purely additive: a new
nullable `RouteResponse.geometry` field, a new `panel` SSE event, a `content_and_artifact` tool
convention, and a new FE drawer. No auth/authz, no data-loss/migration, no NEW external provider
(ORS already wired — we just stop discarding geometry it already returns), no removal of existing
behaviour. Design + plan reviewed against v3; foundation (routing tool, streaming taxonomy) already
merged.

## Rationale

`content_and_artifact` is the doc-correct way to send rich UI data to the browser without bloating
the model context (settled in `RESEARCH.md`). The mapper already iterates every `ToolMessage`, so
emitting a `panel` event off `.artifact` is a minimal change. Keyless MapLibre+OSM + a Google Maps
deep-link honours the no-Google-key ethos while matching the reference screenshot.

## Alternatives

- `Command(update=...)` tool returns — rejected (couples UI into core state, manual ToolMessage).
- `get_stream_writer` custom stream — deferred (ephemeral; not persisted for history rehydration).
- FE re-fetch via REST on tool_result — rejected (double work, arg-recovery race).

## Hard-gate notes

- **Public contract (additive):** `RouteResponse.geometry` (nullable) + a new `panel` SSE event are
  additive, not breaking — no route path/method/shape removed. If `risk-corroboration.sh` flags
  public-contract on commit, authorize with `RISK_WARN_CATEGORIES="public-contract"` per the
  established repo convention.

### Verify

| Check | Command | Exit | Notes |
|---|---|---|---|
| _(filled per task as waves complete)_ | | | |

### Rollback

- Reversible feature work — `git revert <sha>` per task commit; drop the worktree branch
  `feat/agent-side-panel` if abandoned.

### Deviations

_(Rule 1–3 auto-fixes recorded here as they occur.)_
