import { describe, expect, it } from "vitest";

import { parseSSE } from "./parseSSE";

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

async function collect(stream: ReadableStream<Uint8Array>): Promise<string[]> {
  const out: string[] = [];
  for await (const payload of parseSSE(stream)) out.push(payload);
  return out;
}

describe("parseSSE", () => {
  it("assembles a multi-chunk stream into the correct concatenated text", async () => {
    // An event split across transport chunks plus several whole events.
    const stream = streamFromChunks([
      "data: Hel",
      "lo\n\ndata:  wor",
      "ld\n\n",
      "data: !\n\n",
    ]);

    const payloads = await collect(stream);

    expect(payloads).toEqual(["Hello", " world", "!"]);
    expect(payloads.join("")).toBe("Hello world!");
  });

  it("stops emission at the [DONE] terminal event", async () => {
    const stream = streamFromChunks([
      "data: a\n\n",
      "data: b\n\n",
      "data: [DONE]\n\n",
      "data: c\n\n", // must never be emitted
    ]);

    const payloads = await collect(stream);

    expect(payloads).toEqual(["a", "b"]);
  });

  it("tolerates a newline-containing token / a data:-less continuation line", async () => {
    // A token containing a newline frames as `data: line1\nline2\n\n`, so the
    // second physical line lacks the `data:` prefix. It must be treated as part
    // of the current event, not crash, and be reconstructed with its newline.
    const stream = streamFromChunks(["data: line1\nline2\n\nplain\n\n"]);

    const payloads = await collect(stream);

    expect(payloads).toEqual(["line1\nline2", "plain"]);
  });

  it("flushes a final segment that lacks a trailing \\n\\n", async () => {
    const stream = streamFromChunks(["data: tail"]);

    const payloads = await collect(stream);

    expect(payloads).toEqual(["tail"]);
  });

  it("accepts an async iterable of strings (no network)", async () => {
    async function* gen() {
      yield "data: x";
      yield "y\n\n";
      yield "data: [DONE]\n\n";
    }

    const out: string[] = [];
    for await (const p of parseSSE(gen())) out.push(p);

    expect(out).toEqual(["xy"]);
  });
});
