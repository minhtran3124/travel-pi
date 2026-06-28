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
| BE wave 1+2 | `pytest tests/tools/test_routing_tools.py tests/api/routes/test_routes.py tests/api/agent/test_stream_events.py tests/services/test_routing_service.py` | 0 | 41 passed |
| BE lint | `ruff check app/... tests/...` | 0 | All checks passed |
| FE parser | `pnpm vitest run src/lib/stream/parseSSE.test.ts` | 0 | 19 passed (incl. panel) |
| FE typecheck | `npx tsc --noEmit` | 0 | clean |
| FE lint | `pnpm lint` | 0 | clean |
| Pre-existing | `pnpm vitest run src/components/chat/useAgentStream.stream.test.tsx` | 1 | 2 fail on clean v3 too — NOT this change |

### Rollback

- Reversible feature work — `git revert <sha>` per task commit; drop the worktree branch
  `feat/agent-side-panel` if abandoned.

### Deviations

- Scope-tighten — Built only the `RoutePanel` projection in `panels.py`, not `Places`/`Weather`
  (the plan listed all three). Those land with their tool conversions; defining them now would be
  speculative unused code (behavior.md §2). `panel.ts` keeps `kind`/`data` loose so they pass
  through forward-compatibly. Commit `ee6ea6b` / `43b8da7`.
- Rule 1 — Two test assertions fixed mid-run: mapper-panel test must include the always-emitted
  `done`; `RoutePanel` import re-added after `ruff-on-edit` stripped it (added before first use).
  Commit `ee6ea6b`.
- Plan correction — `RouteResponse.geometry` promoted from "optional v2" to v1 (the reference look
  needs the road line and ORS already returns it). Recorded in RESEARCH §4 / DESIGN. Commit `ee6ea6b`.
