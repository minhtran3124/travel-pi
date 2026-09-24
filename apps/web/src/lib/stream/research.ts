// Bespoke SSE parser for the deep-research progress stream.
//
// Wire contract — mirror of apps/api/app/streaming/research_events.py. EVERY
// segment is a named event whose `data` is a compact JSON object; payloads carry
// projected progress only (never message text, tool args or dossier content):
//   event: research_start     data: {"run_id","trip_id"}
//   event: research_phase     data: {"todos":[{"content","status"}]}
//   event: research_subagent  data: {"name","status"}
//   event: research_tool      data: {"name","status"}
//   event: research_file      data: {"path","bytes"}
//   event: research_eval      data: {"iteration","result","explanation"}
//   event: research_done      data: {"status","files","proposal_ready"}   (terminal)
//   event: research_error     data: {"code","message"}                    (terminal)
//
// Framing is identical to parseSSE.ts (`event:`/`data:` lines, `\n\n` segment
// delimiter, trailing-segment flush). Its helpers are module-private, so the
// line/segment logic is replicated here rather than importing it — parseSSE.ts
// stays untouched. This parser is network-free and unit-testable.

const DATA_PREFIX = "data: ";
const EVENT_PREFIX = "event: ";

// ── Exported event types ──────────────────────────────────────────────────────

export interface ResearchTodo {
  content: string;
  status: string;
}

/** Run began — carries the ids that scope every later event. */
export interface ResearchStartEvent {
  type: "research_start";
  runId: string;
  tripId: string;
}

/** The plan's todo list was (re)projected — drives the phase checklist. */
export interface ResearchPhaseEvent {
  type: "research_phase";
  todos: ResearchTodo[];
}

/** A sub-agent's status changed (e.g. dispatched, finished). */
export interface ResearchSubagentEvent {
  type: "research_subagent";
  name: string;
  status: string;
}

/** A tool invocation started or ended (name + status only, never args). */
export interface ResearchToolEvent {
  type: "research_tool";
  name: string;
  status: string;
}

/** A dossier file was written (path + byte size only, never content). */
export interface ResearchFileEvent {
  type: "research_file";
  path: string;
  bytes: number;
}

/** A rubric evaluation iteration produced a verdict. */
export interface ResearchEvalEvent {
  type: "research_eval";
  iteration: number;
  result: string;
  explanation: string;
}

/** Terminal success event — the run finished and (maybe) a proposal is ready. */
export interface ResearchDoneEvent {
  type: "research_done";
  status: string;
  files: string[];
  proposalReady: boolean;
}

/** Terminal failure event surfaced in-band by the backend. */
export interface ResearchErrorEvent {
  type: "research_error";
  code: string;
  message: string;
}

export type ResearchEvent =
  | ResearchStartEvent
  | ResearchPhaseEvent
  | ResearchSubagentEvent
  | ResearchToolEvent
  | ResearchFileEvent
  | ResearchEvalEvent
  | ResearchDoneEvent
  | ResearchErrorEvent;

// ── Internal helpers ──────────────────────────────────────────────────────────

/** Coerce a raw todos value into a clean `{content,status}` list. */
function toTodos(value: unknown): ResearchTodo[] {
  if (!Array.isArray(value)) return [];
  return value.map((t) => {
    const todo = (t ?? {}) as Record<string, unknown>;
    return {
      content: String(todo.content ?? ""),
      status: String(todo.status ?? ""),
    };
  });
}

/**
 * Reduce one complete SSE segment (the text between `\n\n` delimiters) to a
 * structured `ResearchEvent`. Returns `null` for an event name we do not model
 * (forward-compatible, matching parseSSE.ts) or for malformed JSON — the caller
 * skips it rather than crashing the stream.
 */
export function parseResearchSegment(raw: string): ResearchEvent | null {
  const lines = raw.split("\n");
  let eventType: string | null = null;
  const dataLines: string[] = [];

  for (const line of lines) {
    if (line.startsWith(EVENT_PREFIX)) {
      eventType = line.slice(EVENT_PREFIX.length).trim();
    } else if (line.startsWith(DATA_PREFIX)) {
      dataLines.push(line.slice(DATA_PREFIX.length));
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length));
    }
  }

  if (eventType === null) return null;

  const payload = dataLines.join("\n");
  let data: Record<string, unknown> = {};
  if (payload.length > 0) {
    try {
      data = JSON.parse(payload) as Record<string, unknown>;
    } catch {
      return null; // malformed JSON — skip rather than crash
    }
  }

  switch (eventType) {
    case "research_start":
      return {
        type: "research_start",
        runId: String(data.run_id ?? ""),
        tripId: String(data.trip_id ?? ""),
      };
    case "research_phase":
      return { type: "research_phase", todos: toTodos(data.todos) };
    case "research_subagent":
      return {
        type: "research_subagent",
        name: String(data.name ?? ""),
        status: String(data.status ?? ""),
      };
    case "research_tool":
      return {
        type: "research_tool",
        name: String(data.name ?? ""),
        status: String(data.status ?? ""),
      };
    case "research_file":
      return {
        type: "research_file",
        path: String(data.path ?? ""),
        bytes: Number(data.bytes ?? 0),
      };
    case "research_eval":
      return {
        type: "research_eval",
        iteration: Number(data.iteration ?? 0),
        result: String(data.result ?? ""),
        explanation: String(data.explanation ?? ""),
      };
    case "research_done":
      return {
        type: "research_done",
        status: String(data.status ?? ""),
        files: Array.isArray(data.files) ? data.files.map(String) : [],
        proposalReady: Boolean(data.proposal_ready),
      };
    case "research_error":
      return {
        type: "research_error",
        code: String(data.code ?? "internal"),
        message: String(data.message ?? ""),
      };
    default:
      return null; // unknown event — ignore forward-compatibly
  }
}

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * Async generator yielding each research SSE event as a structured
 * `ResearchEvent`. Unknown or malformed segments are skipped. The backend closes
 * the connection after the terminal `research_done`/`research_error` event, so
 * the generator ends on its own.
 */
export async function* readResearchStream(
  response: Response,
): AsyncGenerator<ResearchEvent> {
  const body = response.body;
  if (!body) return;

  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      if (!value) continue;

      buffer += decoder.decode(value, { stream: true });

      const segments = buffer.split("\n\n");
      // Keep the trailing (possibly partial) segment in the buffer.
      buffer = segments.pop() ?? "";

      for (const segment of segments) {
        if (segment.length === 0) continue;
        const event = parseResearchSegment(segment);
        if (event !== null) yield event;
      }
    }

    // Flush bytes of a multibyte codepoint split across the final chunk.
    buffer += decoder.decode();

    // Flush any trailing complete-but-undelimited segment at stream end.
    if (buffer.trim().length > 0) {
      const event = parseResearchSegment(buffer);
      if (event !== null) yield event;
    }
  } finally {
    reader.releaseLock();
  }
}
