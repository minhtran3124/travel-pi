import { describe, expect, it } from "vitest";

import { parseSSE, type SSEEvent } from "./parseSSE";

/** Build a ReadableStream<Uint8Array> from a list of string chunks. */
function streamFromChunks(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  let i = 0;
  return new ReadableStream<Uint8Array>({
    pull(controller) {
      if (i < chunks.length) {
        controller.enqueue(encoder.encode(chunks[i++]));
      } else {
        controller.close();
      }
    },
  });
}

async function collect(stream: ReadableStream<Uint8Array>): Promise<SSEEvent[]> {
  const out: SSEEvent[] = [];
  for await (const event of parseSSE(stream)) out.push(event);
  return out;
}

/** Serialise a typed event the way the backend does (compact JSON `data`). */
function sse(event: string, data: Record<string, unknown>): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

/** Convenience: extract only text from token events. */
function tokens(events: SSEEvent[]): string[] {
  return events
    .filter((e): e is Extract<SSEEvent, { type: "token" }> => e.type === "token")
    .map((e) => e.text);
}

describe("parseSSE — typed protocol", () => {
  it("parses token events from {content} JSON", async () => {
    const stream = streamFromChunks([
      sse("token", { content: "Hello" }),
      sse("token", { content: " world" }),
    ]);
    const events = await collect(stream);
    expect(tokens(events)).toEqual(["Hello", " world"]);
  });

  it("reassembles a token JSON split across byte chunks", async () => {
    const stream = streamFromChunks([
      'event: token\ndata: {"con',
      'tent":"split"}\n\n',
    ]);
    const events = await collect(stream);
    expect(tokens(events)).toEqual(["split"]);
  });

  it("preserves newlines inside token content (JSON-escaped, single data line)", async () => {
    const stream = streamFromChunks([sse("token", { content: "a\n\nb" })]);
    const events = await collect(stream);
    expect(tokens(events)).toEqual(["a\n\nb"]);
  });

  it("reconstructs a multibyte char split across two byte chunks", async () => {
    const bytes = new TextEncoder().encode(sse("token", { content: "😀" }));
    // Split inside the 4-byte 😀 (its bytes span indices 31–34).
    const splitAt = 33;
    const parts = [bytes.slice(0, splitAt), bytes.slice(splitAt)];
    let i = 0;
    const stream = new ReadableStream<Uint8Array>({
      pull(controller) {
        if (i < parts.length) controller.enqueue(parts[i++]);
        else controller.close();
      },
    });
    const events = await collect(stream);
    expect(tokens(events)).toEqual(["😀"]);
  });

  it("parses start with conversationId", async () => {
    const events = await collect(
      streamFromChunks([sse("start", { conversation_id: "c1" })]),
    );
    expect(events[0]).toEqual({ type: "start", conversationId: "c1" });
  });

  it("parses subagent handoff", async () => {
    const events = await collect(
      streamFromChunks([sse("subagent", { name: "planner" })]),
    );
    expect(events[0]).toEqual({ type: "subagent", name: "planner" });
  });

  it("parses tool_call with camelCased argsPreview + null subagent", async () => {
    const events = await collect(
      streamFromChunks([
        sse("tool_call", {
          id: "t1",
          name: "search_flights",
          args_preview: '{"city":"Paris"}',
          subagent: null,
        }),
      ]),
    );
    expect(events[0]).toEqual({
      type: "tool_call",
      id: "t1",
      name: "search_flights",
      argsPreview: '{"city":"Paris"}',
      subagent: null,
    });
  });

  it("parses tool_result and maps status", async () => {
    const events = await collect(
      streamFromChunks([
        sse("tool_result", { id: "t1", status: "ok" }),
        sse("tool_result", { id: "t2", status: "error" }),
      ]),
    );
    expect(events).toEqual([
      { type: "tool_result", id: "t1", status: "ok" },
      { type: "tool_result", id: "t2", status: "error" },
    ]);
  });

  it("parses a panel event into camelCased toolCallId + kind + data", async () => {
    const events = await collect(
      streamFromChunks([
        sse("panel", {
          tool_call_id: "tc1",
          kind: "route",
          data: { recommended_mode: "car", geometry: null },
        }),
      ]),
    );
    expect(events[0]).toEqual({
      type: "panel",
      toolCallId: "tc1",
      kind: "route",
      data: { recommended_mode: "car", geometry: null },
    });
  });

  it("parses interrupt with conversationId + payload", async () => {
    const events = await collect(
      streamFromChunks([
        sse("interrupt", {
          conversation_id: "conv-abc",
          payload: { type: "plan_approval", draft: "Book flight VN123?" },
        }),
      ]),
    );
    expect(events[0]).toEqual({
      type: "interrupt",
      conversationId: "conv-abc",
      payload: { type: "plan_approval", draft: "Book flight VN123?" },
    });
  });

  it("parses done with currentFlow (terminal)", async () => {
    const events = await collect(
      streamFromChunks([
        sse("token", { content: "hi" }),
        sse("done", { conversation_id: "c1", current_flow: "concierge" }),
      ]),
    );
    expect(events.at(-1)).toEqual({
      type: "done",
      conversationId: "c1",
      currentFlow: "concierge",
      suggestions: [],
    });
  });

  it("parses done with a suggestions array of string keys", async () => {
    const events = await collect(
      streamFromChunks([
        sse("done", {
          conversation_id: "c1",
          current_flow: "booking",
          suggestions: ["booking.bookThis", "booking.comparePrices"],
        }),
      ]),
    );
    expect(events.at(-1)).toEqual({
      type: "done",
      conversationId: "c1",
      currentFlow: "booking",
      suggestions: ["booking.bookThis", "booking.comparePrices"],
    });
  });

  it("defaults suggestions to [] when the field is absent (backward-compat)", async () => {
    const events = await collect(
      streamFromChunks([
        sse("done", { conversation_id: "c1", current_flow: null }),
      ]),
    );
    const done = events.at(-1) as Extract<SSEEvent, { type: "done" }>;
    expect(done.suggestions).toEqual([]);
  });

  it("coerces a non-array suggestions value to []", async () => {
    const events = await collect(
      streamFromChunks([
        sse("done", {
          conversation_id: "c1",
          current_flow: null,
          suggestions: "nope",
        }),
      ]),
    );
    const done = events.at(-1) as Extract<SSEEvent, { type: "done" }>;
    expect(done.suggestions).toEqual([]);
  });

  it("parses error events", async () => {
    const events = await collect(
      streamFromChunks([sse("error", { code: "internal", message: "boom" })]),
    );
    expect(events[0]).toEqual({
      type: "error",
      code: "internal",
      message: "boom",
    });
  });

  it("emits a reset between draft and final answer", async () => {
    const events = await collect(
      streamFromChunks([
        sse("subagent", { name: "concierge" }),
        sse("token", { content: "draft" }),
        sse("reset", {}),
        sse("token", { content: "final" }),
        sse("done", { conversation_id: "c1", current_flow: null }),
      ]),
    );
    expect(events.map((e) => e.type)).toEqual([
      "subagent",
      "token",
      "reset",
      "token",
      "done",
    ]);
    expect(tokens(events)).toEqual(["draft", "final"]);
  });

  it("skips an unknown event type forward-compatibly", async () => {
    const events = await collect(
      streamFromChunks([
        "event: future_thing\ndata: {}\n\n",
        sse("token", { content: "ok" }),
      ]),
    );
    expect(events).toHaveLength(1);
    expect(tokens(events)).toEqual(["ok"]);
  });

  it("skips a segment with malformed JSON instead of crashing", async () => {
    const events = await collect(
      streamFromChunks([
        "event: token\ndata: not-json\n\n",
        sse("token", { content: "after" }),
      ]),
    );
    expect(tokens(events)).toEqual(["after"]);
  });

  it("ignores a bare data: line with no event (legacy frame)", async () => {
    const events = await collect(streamFromChunks(["data: orphan\n\n"]));
    expect(events).toEqual([]);
  });

  it("flushes a final segment lacking a trailing \\n\\n", async () => {
    const events = await collect(
      streamFromChunks([`event: token\ndata: ${JSON.stringify({ content: "tail" })}`]),
    );
    expect(tokens(events)).toEqual(["tail"]);
  });

  it("accepts an async iterable of strings (no network)", async () => {
    async function* gen() {
      yield 'event: token\ndata: {"con';
      yield 'tent":"xy"}\n\n';
    }
    const out: SSEEvent[] = [];
    for await (const e of parseSSE(gen())) out.push(e);
    expect(tokens(out)).toEqual(["xy"]);
  });
});
