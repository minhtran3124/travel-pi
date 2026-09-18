import { describe, expect, it } from "vitest";

import {
  parseResearchSegment,
  readResearchStream,
  type ResearchEvent,
} from "./research";

/** Serialise a typed event the way the backend does (compact JSON `data`). */
function sse(event: string, data: Record<string, unknown>): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

/** One SSE segment (no trailing `\n\n`) → the parser input. */
function segment(event: string, data: Record<string, unknown>): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}`;
}

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

/** A minimal Response carrying only the SSE body stream. */
function responseFromChunks(chunks: string[]): Response {
  return { body: streamFromChunks(chunks) } as unknown as Response;
}

async function collect(response: Response): Promise<ResearchEvent[]> {
  const out: ResearchEvent[] = [];
  for await (const event of readResearchStream(response)) out.push(event);
  return out;
}

describe("parseResearchSegment — per event type", () => {
  it("maps research_start", () => {
    expect(
      parseResearchSegment(segment("research_start", { run_id: "r1", trip_id: "t1" })),
    ).toEqual({ type: "research_start", runId: "r1", tripId: "t1" });
  });

  it("maps research_phase with a todos list", () => {
    expect(
      parseResearchSegment(
        segment("research_phase", {
          todos: [
            { content: "Scout flights", status: "in_progress" },
            { content: "Rank hotels", status: "pending" },
          ],
        }),
      ),
    ).toEqual({
      type: "research_phase",
      todos: [
        { content: "Scout flights", status: "in_progress" },
        { content: "Rank hotels", status: "pending" },
      ],
    });
  });

  it("maps research_subagent", () => {
    expect(
      parseResearchSegment(
        segment("research_subagent", { name: "flights", status: "running" }),
      ),
    ).toEqual({ type: "research_subagent", name: "flights", status: "running" });
  });

  it("maps research_tool", () => {
    expect(
      parseResearchSegment(
        segment("research_tool", { name: "write_file", status: "start" }),
      ),
    ).toEqual({ type: "research_tool", name: "write_file", status: "start" });
  });

  it("maps research_file with a numeric byte size", () => {
    expect(
      parseResearchSegment(
        segment("research_file", { path: "dossier/flights.md", bytes: 2048 }),
      ),
    ).toEqual({ type: "research_file", path: "dossier/flights.md", bytes: 2048 });
  });

  it("maps research_eval", () => {
    expect(
      parseResearchSegment(
        segment("research_eval", {
          iteration: 2,
          result: "pass",
          explanation: "Coverage sufficient",
        }),
      ),
    ).toEqual({
      type: "research_eval",
      iteration: 2,
      result: "pass",
      explanation: "Coverage sufficient",
    });
  });

  it("maps research_done with files + proposal_ready", () => {
    expect(
      parseResearchSegment(
        segment("research_done", {
          status: "completed",
          files: ["dossier/flights.md", "dossier/hotels.md"],
          proposal_ready: true,
        }),
      ),
    ).toEqual({
      type: "research_done",
      status: "completed",
      files: ["dossier/flights.md", "dossier/hotels.md"],
      proposalReady: true,
    });
  });

  it("maps research_error", () => {
    expect(
      parseResearchSegment(
        segment("research_error", { code: "timeout", message: "ran too long" }),
      ),
    ).toEqual({ type: "research_error", code: "timeout", message: "ran too long" });
  });

  it("returns null for an unrecognized event name (forward-compatible)", () => {
    expect(
      parseResearchSegment(segment("research_future_thing", { anything: true })),
    ).toBeNull();
  });
});

describe("readResearchStream — over a mocked Response", () => {
  it("yields events in order", async () => {
    const events = await collect(
      responseFromChunks([
        sse("research_start", { run_id: "r1", trip_id: "t1" }),
        sse("research_subagent", { name: "flights", status: "running" }),
        sse("research_done", {
          status: "completed",
          files: ["dossier/flights.md"],
          proposal_ready: true,
        }),
      ]),
    );
    expect(events).toEqual([
      { type: "research_start", runId: "r1", tripId: "t1" },
      { type: "research_subagent", name: "flights", status: "running" },
      {
        type: "research_done",
        status: "completed",
        files: ["dossier/flights.md"],
        proposalReady: true,
      },
    ]);
  });

  it("reassembles an event split across byte chunks and skips unknowns", async () => {
    const events = await collect(
      responseFromChunks([
        'event: research_start\ndata: {"run_id":"r',
        '1","trip_id":"t1"}\n\n',
        "event: research_future\ndata: {}\n\n",
        sse("research_error", { code: "internal", message: "boom" }),
      ]),
    );
    expect(events).toEqual([
      { type: "research_start", runId: "r1", tripId: "t1" },
      { type: "research_error", code: "internal", message: "boom" },
    ]);
  });

  it("yields nothing when the Response has no body", async () => {
    const events = await collect({ body: null } as unknown as Response);
    expect(events).toEqual([]);
  });
});
