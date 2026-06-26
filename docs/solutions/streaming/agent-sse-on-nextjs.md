---
problem_type: knowledge
module: streaming
tags: sse, nextjs, streaming, fetch-readablestream, proxy-buffering, agent
severity: standard
applicable_when: Consuming a Server-Sent-Events stream (e.g. an LLM agent token stream) from a backend in a Next.js app.
affects:
  - apps/web/src/components/chat/useAgentStream.ts
  - apps/web/src/lib/stream/parseSSE.ts
  - apps/web/next.config.ts
supersedes: null
confidence: high
confirmed_at: 2026-06-26
---
## Applicable When

Building a browser client that consumes an SSE token stream from a backend in a Next.js app — especially an LLM/agent chat widget POSTing a request body.

## Pattern

Three non-obvious constraints, learned building the agent co-pilot:

1. **Stream DIRECT-to-origin, not through the Next rewrite proxy.** A Next `rewrites()` proxy (and compression) buffers SSE, stalling token streaming (Next.js issues #48427 / #9965). Point the stream at the backend origin via `NEXT_PUBLIC_API_URL`; keep the `/api/be/*` proxy only for JSON.
2. **Use `fetch` + `ReadableStream` + `TextDecoder`, NOT `EventSource`.** `EventSource` is GET-only and cannot send headers or a POST body — unusable for `POST /agent/stream`. Raw `fetch` does not auto-parse SSE, so parse the framing yourself.
3. **The `data: <chunk>\n\n` framing is ambiguous when a token contains `\n\n`.** A plain-text SSE payload (no JSON/base64 encoding) means a paragraph break inside a token is indistinguishable from the event delimiter. The robust fix is **backend-side** (base64/JSON-encode each `data:` payload). If you can't change the BE, tolerate `data:`-less continuation lines (rejoin with `\n`) — content-fidelity only, not a crash.

## How to Use

- Parser: accumulate bytes → `TextDecoder`; split on `\n\n`; keep the trailing partial in the buffer; strip the `data: ` prefix; stop on `[DONE]`; **flush the decoder once at stream end** (`decoder.decode()`) so a multibyte codepoint split across the final bytes isn't dropped.
- Fallback safety: if you fall back from a dropped stream to a **non-idempotent** sync endpoint (e.g. `POST /agent/chat`), only do so when **zero tokens were received** — otherwise the agent may have already performed server-side writes and the fallback re-executes them (duplicate mutations). Keep the partial text + surface an error instead.
- Multi-turn memory: if the stream returns no `conversation_id` (plain text) and the BE mints a fresh thread on null, **client-pin a `crypto.randomUUID()` conversation_id on the first send** and reuse it across stream + fallback (see the related bug doc).

## Code Example

```ts
// flush the decoder so a multibyte char at the very end isn't lost
const tail = decoder.decode(); if (tail) yield tail;

// only fall back when nothing was streamed (avoid duplicate non-idempotent writes)
if (!received) { /* POST /agent/chat fallback */ }
else { setError("connection dropped mid-reply"); /* keep partial, do NOT re-send */ }
```

## Gotchas

- `process.env.NEXT_PUBLIC_*` must be exposed at build for the browser; CORS on the origin must allow the browser.
- The plain-text framing limitation is recorded as a Phase-2 backend item (encode SSE payloads).

## Related
- docs/solutions/ci/pnpm-node-floor-mismatch.md
- docs/solutions/monorepo/phase1-architecture-decisions.md
