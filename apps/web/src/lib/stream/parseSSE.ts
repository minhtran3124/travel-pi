// Bespoke SSE parser for the agent `/agent/stream` endpoint.
//
// Wire contract (authoritative, see specs/web-trip-planner/research-brief.md §"Area 2"):
//   Token event  — no `event:` field:  data: <chunk>\n\n
//   Interrupt    — named event:        event: interrupt\ndata: {...}\n\n
//   Terminal     — (unchanged):        data: [DONE]\n\n
//
// This parser is network-free and unit-testable: feed it any ReadableStream of
// bytes OR an async iterable of strings.

const DATA_PREFIX = "data: ";
const EVENT_PREFIX = "event: ";
const DONE = "[DONE]";

// ── Exported event types ──────────────────────────────────────────────────────

export interface SSETokenEvent {
  type: "token";
  text: string;
}

export interface SSEInterruptPayload {
  type: string;
  draft: string;
}

export interface SSEInterruptEvent {
  type: "interrupt";
  conversationId: string;
  payload: SSEInterruptPayload;
}

export type SSEEvent = SSETokenEvent | SSEInterruptEvent;

// ── Internal helpers ──────────────────────────────────────────────────────────

type ByteOrTextSource =
  | ReadableStream<Uint8Array>
  | AsyncIterable<string | Uint8Array>;

function hasGetReader(
  source: ByteOrTextSource,
): source is ReadableStream<Uint8Array> {
  return typeof (source as ReadableStream<Uint8Array>).getReader === "function";
}

/** Normalises any supported source into an async iterable of decoded strings. */
async function* toTextChunks(
  source: ByteOrTextSource,
): AsyncGenerator<string> {
  const decoder = new TextDecoder();

  if (hasGetReader(source)) {
    const reader = source.getReader();
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        if (value) yield decoder.decode(value, { stream: true });
      }
      // Flush any bytes of a multibyte codepoint split across the final chunk.
      const tail = decoder.decode();
      if (tail) yield tail;
    } finally {
      reader.releaseLock();
    }
    return;
  }

  for await (const chunk of source) {
    yield typeof chunk === "string"
      ? chunk
      : decoder.decode(chunk, { stream: true });
  }
}

/**
 * Reduce one complete SSE segment (the text between `\n\n` delimiters) to a
 * structured event. Reads the optional `event:` field and all `data:` lines.
 * Returns `null` when the segment is the `[DONE]` terminal (caller must stop).
 */
function parseSegment(segment: string): SSEEvent | null {
  const lines = segment.split("\n");
  let eventType: string | null = null;
  const dataLines: string[] = [];

  for (const line of lines) {
    if (line.startsWith(EVENT_PREFIX)) {
      eventType = line.slice(EVENT_PREFIX.length);
    } else if (line.startsWith(DATA_PREFIX)) {
      dataLines.push(line.slice(DATA_PREFIX.length));
    } else if (line.length > 0) {
      // Continuation line (e.g. a token that itself contained a newline) —
      // kept verbatim so multi-line tokens are reconstructed intact.
      dataLines.push(line);
    }
  }

  const text = dataLines.join("\n");

  if (text === DONE) return null;

  if (eventType === "interrupt") {
    try {
      const parsed = JSON.parse(text) as {
        conversation_id: string;
        payload: SSEInterruptPayload;
      };
      return {
        type: "interrupt",
        conversationId: parsed.conversation_id,
        payload: parsed.payload,
      };
    } catch {
      // Malformed interrupt JSON — surface as a plain token rather than crash.
      return { type: "token", text };
    }
  }

  return { type: "token", text };
}

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * Async generator yielding each SSE event as a structured `SSEEvent`. Stops
 * (without emitting) when the `[DONE]` terminal event is seen.
 *
 * Token events carry `{type:'token', text}` — exactly as before, just wrapped.
 * Interrupt events carry `{type:'interrupt', conversationId, payload}`.
 */
export async function* parseSSE(
  source: ByteOrTextSource,
): AsyncGenerator<SSEEvent> {
  let buffer = "";

  for await (const text of toTextChunks(source)) {
    buffer += text;

    const segments = buffer.split("\n\n");
    // Keep the trailing (possibly partial) segment in the buffer.
    buffer = segments.pop() ?? "";

    for (const segment of segments) {
      if (segment.length === 0) continue;
      const event = parseSegment(segment);
      if (event === null) return; // DONE — stop the generator
      yield event;
    }
  }

  // Flush any trailing complete-but-undelimited segment at stream end.
  const tail = buffer.trim();
  if (tail.length > 0) {
    const event = parseSegment(buffer);
    if (event !== null) yield event;
  }
}
