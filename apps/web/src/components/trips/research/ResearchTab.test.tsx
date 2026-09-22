import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";

import { server } from "@/test/msw";

import en from "../../../../messages/en.json";
import { ResearchTab } from "./ResearchTab";

const BASE = "/api/be";
const TRIP_ID = "trip-1";
const RUN_ID = "run-9";

/** One Server-Sent Event frame, as the research stream emits them. */
const sse = (event: string, data: Record<string, unknown>) =>
  `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;

/** A ReadableStream body emitting each SSE frame as a separate wire chunk. */
function sseStream(frames: string[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const frame of frames) controller.enqueue(enc.encode(frame));
      controller.close();
    },
  });
}

function renderTab() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <NextIntlClientProvider locale="en" messages={en}>
      <QueryClientProvider client={queryClient}>
        <ResearchTab tripId={TRIP_ID} />
      </QueryClientProvider>
    </NextIntlClientProvider>,
  );
}

describe("ResearchTab", () => {
  it("renders the locked state for a free (non-premium) user", async () => {
    // GET latest → 403 from require_premium.
    server.use(
      http.get(`${BASE}/agent/trips/:tripId/research`, () =>
        HttpResponse.json({ message: "premium only" }, { status: 403 }),
      ),
    );

    renderTab();

    await waitFor(() =>
      expect(
        screen.getByText(en.TripDetail.research.lockedTitle),
      ).toBeInTheDocument(),
    );
    // The locked state offers an upgrade hint, never a start button.
    expect(
      screen.queryByRole("button", { name: en.TripDetail.research.start }),
    ).not.toBeInTheDocument();
  });

  it("renders the empty state with a start button for a premium user with no run", async () => {
    // GET latest → 404 (no research run yet for this trip).
    server.use(
      http.get(`${BASE}/agent/trips/:tripId/research`, () =>
        HttpResponse.json({ message: "no run" }, { status: 404 }),
      ),
    );

    renderTab();

    await waitFor(() =>
      expect(
        screen.getByText(en.TripDetail.research.emptyHint),
      ).toBeInTheDocument(),
    );
    // No departure point yet: Start stays disabled — the tab never assumes one.
    const start = screen.getByRole("button", { name: en.TripDetail.research.start });
    expect(start).toBeDisabled();
    fireEvent.change(screen.getByLabelText(en.TripDetail.research.originLabel), {
      target: { value: "   " },
    });
    expect(start).toBeDisabled();
  });

  it("lists the dossier files from a mocked status response", async () => {
    server.use(
      http.get(`${BASE}/agent/trips/:tripId/research`, () =>
        HttpResponse.json({
          run_id: RUN_ID,
          trip_id: TRIP_ID,
          status: "completed",
          thread_turn: 1,
          files: ["/research/overview.md", "/plan/proposal.json"],
          proposal_ready: false,
        }),
      ),
    );

    renderTab();

    await waitFor(() =>
      expect(
        screen.getByText(en.TripDetail.research.filesHeading),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText("/research/overview.md")).toBeInTheDocument();
    expect(screen.getByText("/plan/proposal.json")).toBeInTheDocument();
  });

  it("leaves the running state and shows the dossier once the stream reaches done", async () => {
    let startBody: unknown = null;
    // No run yet → premium empty state with a Start button; POST books a run
    // this session streams live (before the latest-summary query refetches).
    server.use(
      http.get(`${BASE}/agent/trips/:tripId/research`, () =>
        HttpResponse.json({ message: "no run" }, { status: 404 }),
      ),
      http.post(`${BASE}/agent/trips/:tripId/research`, async ({ request }) => {
        startBody = await request.json();
        return HttpResponse.json({ run_id: RUN_ID, thread_turn: 1 }, { status: 202 });
      }),
    );

    // The live SSE bypasses the `/api/be` proxy and hits the origin directly via
    // `useResearchStream`'s AbortController-signalled fetch. undici (the test
    // env's fetch) rejects jsdom's AbortSignal, so — like `useResearchStream`'s
    // own tests — stub fetch for the stream URL and delegate everything else
    // (the MSW-handled GET/POST) to the real fetch.
    const realFetch = globalThis.fetch;
    vi.stubGlobal("fetch", (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/stream")) {
        return Promise.resolve(
          new HttpResponse(
            sseStream([
              sse("research_start", { run_id: RUN_ID, trip_id: TRIP_ID }),
              sse("research_done", {
                status: "completed",
                files: ["/research/overview.md"],
                proposal_ready: false,
              }),
            ]),
            { headers: { "Content-Type": "text/event-stream" } },
          ),
        );
      }
      return realFetch(input, init);
    });

    try {
      renderTab();

      const startButton = await screen.findByRole("button", {
        name: en.TripDetail.research.start,
      });
      fireEvent.change(screen.getByLabelText(en.TripDetail.research.originLabel), {
        target: { value: " Ho Chi Minh City " },
      });
      fireEvent.click(startButton);

      // The spinner card appears while the run streams…
      await waitFor(() =>
        expect(
          screen.getByText(en.TripDetail.research.running),
        ).toBeInTheDocument(),
      );

      // …then the terminal `research_done` must retire it and reveal the dossier
      // (this assertion fails before the A2 fix — the card spun forever).
      await waitFor(() =>
        expect(
          screen.queryByText(en.TripDetail.research.running),
        ).not.toBeInTheDocument(),
      );
      expect(
        screen.getByText(en.TripDetail.research.filesHeading),
      ).toBeInTheDocument();
      expect(screen.getByText("/research/overview.md")).toBeInTheDocument();
      // The trimmed departure point went to the start request.
      expect(startBody).toMatchObject({ origin: "Ho Chi Minh City" });
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
