// Bespoke SSE parser for the agent `/agent/stream` endpoint.
//
// The backend framing (authoritative, see specs/web-trip-planner/research-brief.md
// §"Area 2"): each event is `data: <chunk>\n\n`; the terminal event is
// `data: [DONE]\n\n`. The payload is PLAIN TEXT (not JSON) and there is exactly
// one event type (no `event:` field).
//
// This parser is network-free and unit-testable: feed it any ReadableStream of
// bytes OR an async iterable of strings.

const DATA_PREFIX = "data: ";
const DONE = "[DONE]";

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
 * Reduce one complete SSE segment (the text between `\n\n` delimiters) to its
 * payload. Lines starting with the 6-char `data: ` prefix are stripped; any
 * other line is tolerated as a continuation of the current event (e.g. a token
 * that itself contained a newline) and kept verbatim. Lines are rejoined with
 * `\n` so a multi-line token is reconstructed intact.
 */
function segmentToPayload(segment: string): string {
  return segment
    .split("\n")
    .map((line) => (line.startsWith(DATA_PREFIX) ? line.slice(DATA_PREFIX.length) : line))
    .join("\n");
}

/**
 * Async generator yielding each event payload as raw text. Stops (without
 * emitting) when the `[DONE]` terminal event is seen.
 */
export async function* parseSSE(
  source: ByteOrTextSource,
): AsyncGenerator<string> {
  let buffer = "";

  for await (const text of toTextChunks(source)) {
    buffer += text;

    const segments = buffer.split("\n\n");
    // Keep the trailing (possibly partial) segment in the buffer.
    buffer = segments.pop() ?? "";

    for (const segment of segments) {
      if (segment.length === 0) continue;
      const payload = segmentToPayload(segment);
      if (payload === DONE) return;
      yield payload;
    }
  }

  // Flush any trailing complete-but-undelimited segment at stream end.
  const tail = buffer.trim();
  if (tail.length > 0) {
    const payload = segmentToPayload(buffer);
    if (payload !== DONE) yield payload;
  }
}
