import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it } from "vitest";

import { server } from "@/test/msw";

import en from "../../../../messages/en.json";
import { ResearchTab } from "./ResearchTab";

const BASE = "/api/be";
const TRIP_ID = "trip-1";
const RUN_ID = "run-9";

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
    expect(
      screen.getByRole("button", { name: en.TripDetail.research.start }),
    ).toBeInTheDocument();
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
});
