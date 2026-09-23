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

  it("renders the plan view with a collapsible detailed report", async () => {
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
      // The plan view resolves the proposal + budget for its sections; empty
      // here so every section falls back to prose without crashing.
      http.get(`${BASE}/agent/research/:runId/files/*`, () =>
        HttpResponse.json({ content: "" }),
      ),
      http.get(`${BASE}/trips/:tripId/budget`, () =>
        HttpResponse.json({ message: "no budget" }, { status: 404 }),
      ),
    );

    renderTab();

    // The plan header replaces the old flat file list.
    await waitFor(() =>
      expect(
        screen.getByText(en.TripDetail.research.plan.readyTitle),
      ).toBeInTheDocument(),
    );
    // The dossier stays reachable under a collapsible report.
    const report = screen.getByRole("button", {
      name: new RegExp(en.TripDetail.research.plan.report.title),
    });
    fireEvent.click(report);
    expect(
      screen.getByText(en.TripDetail.research.plan.report.overview),
    ).toBeInTheDocument();
  });

  // A proposal with a shortlist entry so Apply renders on a completed run
  // (shortlist alone gives applyCount > 0 without needing place lookups).
  const APPLYABLE_PROPOSAL = {
    itinerary: [],
    shortlist: ["p1"],
    flights: [],
    hotels: [],
    budget_estimate: null,
  };

  /** Register a latest-run summary with `status` plus the plan-view lookups. */
  function useStatusHandlers(status: string) {
    server.use(
      http.get(`${BASE}/agent/trips/:tripId/research`, () =>
        HttpResponse.json({
          run_id: RUN_ID,
          trip_id: TRIP_ID,
          status,
          thread_turn: 1,
          files: ["/plan/proposal.json", "/research/overview.md"],
          proposal_ready: status === "completed",
        }),
      ),
      http.get(`${BASE}/agent/research/:runId/files/*`, ({ request }) => {
        const url = new URL(request.url);
        if (url.pathname.endsWith("proposal.json")) {
          return HttpResponse.json({ content: JSON.stringify(APPLYABLE_PROPOSAL) });
        }
        return HttpResponse.json({ content: "" });
      }),
      http.get(`${BASE}/trips/:tripId/budget`, () =>
        HttpResponse.json({ message: "no budget" }, { status: 404 }),
      ),
    );
  }

  it("shows the unfinished notice, keeps the dossier, and hides Apply for a failed run", async () => {
    useStatusHandlers("failed");
    renderTab();

    await waitFor(() =>
      expect(
        screen.getByText(en.TripDetail.research.unfinishedTitle),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByText(en.TripDetail.research.failedHint),
    ).toBeInTheDocument();
    // The dossier files stay reachable under the detailed report.
    expect(
      screen.getByRole("button", {
        name: new RegExp(en.TripDetail.research.plan.report.title),
      }),
    ).toBeInTheDocument();
    // Apply is hidden even though the proposal has appliable ids.
    expect(
      screen.queryByRole("button", { name: en.TripDetail.research.apply }),
    ).not.toBeInTheDocument();
  });

  it("shows the interrupted hint for an interrupted run", async () => {
    useStatusHandlers("interrupted");
    renderTab();

    await waitFor(() =>
      expect(
        screen.getByText(en.TripDetail.research.unfinishedTitle),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByText(en.TripDetail.research.interruptedHint),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: en.TripDetail.research.apply }),
    ).not.toBeInTheDocument();
  });

  it("shows Apply and no unfinished notice for a completed run", async () => {
    useStatusHandlers("completed");
    renderTab();

    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: en.TripDetail.research.apply }),
      ).toBeInTheDocument(),
    );
    expect(
      screen.queryByText(en.TripDetail.research.unfinishedTitle),
    ).not.toBeInTheDocument();
  });

  it("Run again revises the unfinished run with the resume instruction", async () => {
    let reviseBody: unknown = null;
    useStatusHandlers("interrupted");
    server.use(
      http.post(`${BASE}/agent/research/:runId/revise`, async ({ request }) => {
        reviseBody = await request.json();
        return HttpResponse.json({ run_id: RUN_ID, thread_turn: 2 }, { status: 202 });
      }),
    );

    // The re-run swaps in a live stream; stub the direct-to-origin SSE (see the
    // done-stream test above for why undici needs this) with an empty stream.
    const realFetch = globalThis.fetch;
    vi.stubGlobal("fetch", (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/stream")) {
        return Promise.resolve(
          new HttpResponse(sseStream([]), {
            headers: { "Content-Type": "text/event-stream" },
          }),
        );
      }
      return realFetch(input, init);
    });

    try {
      renderTab();

      const runAgain = await screen.findByRole("button", {
        name: en.TripDetail.research.runAgain,
      });
      fireEvent.click(runAgain);

      await waitFor(() =>
        expect(reviseBody).toMatchObject({
          instruction: en.TripDetail.research.resumeInstruction,
        }),
      );
    } finally {
      vi.unstubAllGlobals();
    }
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
      // The plan view (shown once the run finishes) resolves the trip budget.
      http.get(`${BASE}/trips/:tripId/budget`, () =>
        HttpResponse.json({ message: "no budget" }, { status: 404 }),
      ),
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
      // The finished run lands on the plan view, dossier under the report.
      expect(
        screen.getByText(en.TripDetail.research.plan.readyTitle),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", {
          name: new RegExp(en.TripDetail.research.plan.report.title),
        }),
      ).toBeInTheDocument();
      // The trimmed departure point went to the start request.
      expect(startBody).toMatchObject({ origin: "Ho Chi Minh City" });
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
