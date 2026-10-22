// Bespoke SSE parser for the agent `/agent/stream` endpoint.
//
// Wire contract — fully-typed protocol (see apps/api/app/streaming/events.py and
// specs/typed-agent-stream/PLAN.md). EVERY segment is a named event whose `data`
// is a compact JSON object:
//   event: start        data: {"conversation_id"}
//   event: token        data: {"content"}
//   event: reset        data: {}
//   event: subagent     data: {"name"}
//   event: tool_call    data: {"id","name","args_preview","subagent"}
//   event: tool_result  data: {"id","status"}            status ∈ ok|error
//   event: interrupt    data: {"conversation_id","payload"}
//   event: done         data: {"conversation_id","assistant_message_id","agent_run_id",
//                              "current_flow","suggestions"}                (terminal)
//   event: error        data: {"code","message"}                   (terminal)
//
// There is no bare-`data:` token frame and no `[DONE]` sentinel any more — the
// terminal is an explicit `event: done` (or `event: error`); the connection then
// closes and the generator ends naturally.
//
// This parser is network-free and unit-testable: feed it any ReadableStream of
// bytes OR an async iterable of strings.

const DATA_PREFIX = "data: ";
const EVENT_PREFIX = "event: ";

// ── Exported event types ──────────────────────────────────────────────────────

export interface SSEStartEvent {
  type: "start";
  conversationId: string;
}

export interface SSETokenEvent {
  type: "token";
  text: string;
}

/**
 * Emitted when the agent starts a fresh assistant message mid-stream (e.g. the
 * reflection node revised its answer and re-ran the sub-agent). The consumer
 * should clear the current bubble so only the final answer remains.
 */
export interface SSEResetEvent {
  type: "reset";
}

/** Active specialist (sub-agent) changed — e.g. supervisor handed off to booking. */
export interface SSESubagentEvent {
  type: "subagent";
  name: string;
}

/** A tool invocation started inside a sub-agent. */
export interface SSEToolCallEvent {
  type: "tool_call";
  id: string;
  name: string;
  argsPreview: string;
  subagent: string | null;
}

/** A tool invocation finished. */
export interface SSEToolResultEvent {
  type: "tool_result";
  id: string;
  status: "ok" | "error";
}

/** Structured side-panel payload from a tool's artifact (drawer renders by `kind`). */
export interface SSEPanelEvent {
  type: "panel";
  toolCallId: string;
  kind: string;
  data: unknown;
  /** Traveller's language the payload was localized to (e.g. "vi"). Absent → "en". */
  language?: string;
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

/** Terminal success event. */
export interface SSEDoneEvent {
  type: "done";
  conversationId: string;
  /** Persisted assistant message id — the handle feedback is filed against.
   * `null` after an interrupt (no reply row) or on payloads that predate it. */
  assistantMessageId: string | null;
  /** The agent_runs row that produced this turn; `null` when absent. */
  agentRunId: string | null;
  currentFlow: string | null;
  suggestions: string[];
  /** Traveller's language for this turn (e.g. "vi"). Absent → "en". */
  language?: string;
}

/** Terminal failure event surfaced in-band by the backend. */
export interface SSEErrorEvent {
  type: "error";
  code: string;
  message: string;
}

export type SSEEvent =
  | SSEStartEvent
  | SSETokenEvent
  | SSEResetEvent
  | SSESubagentEvent
  | SSEToolCallEvent
  | SSEToolResultEvent
  | SSEPanelEvent
  | SSEInterruptEvent
  | SSEDoneEvent
  | SSEErrorEvent;

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
async function* toTextChunks(source: ByteOrTextSource): AsyncGenerator<string> {
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
 * structured event. Returns `null` when the segment carries no event we model
 * or its JSON is malformed — the caller skips it (never crashes the stream).
 */
function parseSegment(segment: string): SSEEvent | null {
  const lines = segment.split("\n");
  let eventType: string | null = null;
  const dataLines: string[] = [];

  for (const line of lines) {
    if (line.startsWith(EVENT_PREFIX)) {
      eventType = line.slice(EVENT_PREFIX.length).trim();
    } else if (line.startsWith(DATA_PREFIX)) {
      dataLines.push(line.slice(DATA_PREFIX.length));
    } else if (line.startsWith("data:")) {
      // `data:` with no trailing space (e.g. an empty payload line).
      dataLines.push(line.slice("data:".length));
    }
  }

  if (eventType === null) return null;

  const raw = dataLines.join("\n");
  let data: Record<string, unknown> = {};
  if (raw.length > 0) {
    try {
      data = JSON.parse(raw) as Record<string, unknown>;
    } catch {
      return null; // malformed JSON — skip rather than crash
    }
  }

  switch (eventType) {
    case "start":
      return { type: "start", conversationId: String(data.conversation_id ?? "") };
    case "token":
      return { type: "token", text: String(data.content ?? "") };
    case "reset":
      return { type: "reset" };
    case "subagent":
      return { type: "subagent", name: String(data.name ?? "") };
    case "tool_call":
      return {
        type: "tool_call",
        id: String(data.id ?? ""),
        name: String(data.name ?? ""),
        argsPreview: String(data.args_preview ?? ""),
        subagent: data.subagent == null ? null : String(data.subagent),
      };
    case "tool_result":
      return {
        type: "tool_result",
        id: String(data.id ?? ""),
        status: data.status === "error" ? "error" : "ok",
      };
    case "panel":
      return {
        type: "panel",
        toolCallId: String(data.tool_call_id ?? ""),
        kind: String(data.kind ?? ""),
        data: data.data,
        language: data.language == null ? undefined : String(data.language),
      };
    case "interrupt":
      return {
        type: "interrupt",
        conversationId: String(data.conversation_id ?? ""),
        payload: (data.payload ?? { type: "", draft: "" }) as SSEInterruptPayload,
      };
    case "done":
      return {
        type: "done",
        conversationId: String(data.conversation_id ?? ""),
        assistantMessageId:
          data.assistant_message_id == null ? null : String(data.assistant_message_id),
        agentRunId: data.agent_run_id == null ? null : String(data.agent_run_id),
        currentFlow: data.current_flow == null ? null : String(data.current_flow),
        suggestions: Array.isArray(data.suggestions) ? data.suggestions.map(String) : [],
        language: data.language == null ? undefined : String(data.language),
      };
    case "error":
      return {
        type: "error",
        code: String(data.code ?? "internal"),
        message: String(data.message ?? ""),
      };
    default:
      return null; // unknown event — ignore forward-compatibly
  }
}

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * Async generator yielding each SSE event as a structured `SSEEvent`. Unknown or
 * malformed segments are skipped. The backend closes the connection after the
 * terminal `done`/`error` event, so the generator ends on its own.
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
      if (event !== null) yield event;
    }
  }

  // Flush any trailing complete-but-undelimited segment at stream end.
  if (buffer.trim().length > 0) {
    const event = parseSegment(buffer);
    if (event !== null) yield event;
  }
}
