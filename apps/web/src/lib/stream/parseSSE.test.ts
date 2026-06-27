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

/** Convenience: extract only text from token events. */
function tokens(events: SSEEvent[]): string[] {
  return events
    .filter((e): e is Extract<SSEEvent, { type: "token" }> => e.type === "token")
    .map((e) => e.text);
}

describe("parseSSE", () => {
  it("assembles a multi-chunk stream into the correct concatenated text", async () => {
    const stream = streamFromChunks([
      "data: Hel",
      "lo\n\ndata:  wor",
      "ld\n\n",
      "data: !\n\n",
    ]);

    const events = await collect(stream);

    expect(tokens(events)).toEqual(["Hello", " world", "!"]);
    expect(tokens(events).join("")).toBe("Hello world!");
  });

  it("yields SSETokenEvent objects with type='token'", async () => {
    const stream = streamFromChunks(["data: hello\n\n"]);
    const events = await collect(stream);

    expect(events).toHaveLength(1);
    expect(events[0]).toEqual({ type: "token", text: "hello" });
  });

  it("stops emission at the [DONE] terminal event", async () => {
    const stream = streamFromChunks([
      "data: a\n\n",
      "data: b\n\n",
      "data: [DONE]\n\n",
      "data: c\n\n", // must never be emitted
    ]);

    const events = await collect(stream);

    expect(tokens(events)).toEqual(["a", "b"]);
  });

  it("tolerates a newline-containing token / a data:-less continuation line", async () => {
    const stream = streamFromChunks(["data: line1\nline2\n\nplain\n\n"]);
    const events = await collect(stream);

    expect(tokens(events)).toEqual(["line1\nline2", "plain"]);
  });

  it("flushes a final segment that lacks a trailing \\n\\n", async () => {
    const stream = streamFromChunks(["data: tail"]);
    const events = await collect(stream);

    expect(tokens(events)).toEqual(["tail"]);
  });

  it("reconstructs a multibyte char split across two byte chunks", async () => {
    const bytes = new TextEncoder().encode("data: 😀\n\n");
    const splitAt = 8;
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

  it("accepts an async iterable of strings (no network)", async () => {
    async function* gen() {
      yield "data: x";
      yield "y\n\n";
      yield "data: [DONE]\n\n";
    }

    const out: SSEEvent[] = [];
    for await (const e of parseSSE(gen())) out.push(e);

    expect(tokens(out)).toEqual(["xy"]);
  });

  // ── Interrupt event ─────────────────────────────────────────────────────────

  it("yields SSEInterruptEvent for event:interrupt segments", async () => {
    const payload = JSON.stringify({
      conversation_id: "conv-abc",
      payload: { type: "plan_approval", draft: "Book flight VN123?" },
    });
    const stream = streamFromChunks([
      "data: thinking…\n\n",
      `event: interrupt\ndata: ${payload}\n\n`,
      "data: [DONE]\n\n",
    ]);

    const events = await collect(stream);

    expect(events).toHaveLength(2);
    expect(events[0]).toEqual({ type: "token", text: "thinking…" });
    expect(events[1]).toEqual({
      type: "interrupt",
      conversationId: "conv-abc",
      payload: { type: "plan_approval", draft: "Book flight VN123?" },
    });
  });

  it("does NOT yield a token event for an interrupt segment", async () => {
    const payload = JSON.stringify({
      conversation_id: "conv-xyz",
      payload: { type: "plan_approval", draft: "Book hotel?" },
    });
    const stream = streamFromChunks([
      `event: interrupt\ndata: ${payload}\n\n`,
    ]);

    const events = await collect(stream);

    // Exactly one event — and it must be an interrupt, not a token
    expect(events).toHaveLength(1);
    expect(events[0].type).toBe("interrupt");
    expect(tokens(events)).toEqual([]);
  });

  it("includes the parsed conversationId and payload from the interrupt JSON", async () => {
    const raw = {
      conversation_id: "thread-999",
      payload: { type: "plan_approval", draft: "Confirm booking for 2 nights?" },
    };
    const stream = streamFromChunks([
      `event: interrupt\ndata: ${JSON.stringify(raw)}\n\n`,
      "data: [DONE]\n\n",
    ]);

    const events = await collect(stream);

    const interrupt = events[0];
    if (interrupt.type !== "interrupt") throw new Error("expected interrupt");
    expect(interrupt.conversationId).toBe("thread-999");
    expect(interrupt.payload.draft).toBe("Confirm booking for 2 nights?");
    expect(interrupt.payload.type).toBe("plan_approval");
  });

  it("treats a malformed interrupt JSON as a plain token (graceful fallback)", async () => {
    const stream = streamFromChunks([
      "event: interrupt\ndata: not-json\n\n",
    ]);

    const events = await collect(stream);

    expect(events).toHaveLength(1);
    expect(events[0]).toEqual({ type: "token", text: "not-json" });
  });

  it("handles an interrupt-only stream (no preceding tokens)", async () => {
    const raw = {
      conversation_id: "conv-solo",
      payload: { type: "plan_approval", draft: "Book it?" },
    };
    const stream = streamFromChunks([
      `event: interrupt\ndata: ${JSON.stringify(raw)}\n\n`,
    ]);

    const events = await collect(stream);

    expect(events).toHaveLength(1);
    expect(events[0].type).toBe("interrupt");
  });

  it("yields a reset event for event:reset segments (revised answer)", async () => {
    const stream = streamFromChunks([
      "data: draft\n\n",
      "event: reset\ndata: \n\n",
      "data: final\n\n",
      "data: [DONE]\n\n",
    ]);

    const events = await collect(stream);

    expect(events.map((e) => e.type)).toEqual(["token", "reset", "token"]);
    expect(tokens(events)).toEqual(["draft", "final"]);
  });
});
