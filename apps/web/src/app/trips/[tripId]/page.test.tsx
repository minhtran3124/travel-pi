import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it, vi } from "vitest";

import en from "../../../../messages/en.json";
import TripDetailPage from "./page";

const search = vi.hoisted(() => ({ tab: null as string | null }));
vi.mock("next/navigation", () => ({
  useParams: () => ({ tripId: "trip-1" }),
  useSearchParams: () => new URLSearchParams(search.tab ? { tab: search.tab } : {}),
}));
vi.mock("@/lib/query/trips", () => ({
  useTrip: () => ({
    data: { id: "trip-1" },
    isPending: false,
    isError: false,
  }),
}));
vi.mock("@/components/trips/TripHeader", () => ({
  TripHeader: () => null,
  TripHeaderSkeleton: () => null,
}));
vi.mock("@/components/trips/itinerary/ItineraryTab", () => ({
  ItineraryTab: () => null,
}));
vi.mock("@/components/trips/research/ResearchTab", () => ({
  ResearchTab: () => null,
}));

function renderPage() {
  return render(
    <NextIntlClientProvider locale="en" messages={en}>
      <QueryClientProvider client={new QueryClient()}>
        <TripDetailPage />
      </QueryClientProvider>
    </NextIntlClientProvider>,
  );
}

describe("TripDetailPage research tab", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    search.tab = null;
  });

  it("shows the Research tab while research is enabled", () => {
    vi.stubEnv("NEXT_PUBLIC_RESEARCH_ENABLED", "true");
    renderPage();
    expect(
      screen.getByRole("tab", { name: en.TripDetail.research.tabLabel }),
    ).toBeInTheDocument();
  });

  it("hides the Research tab when research is disabled", () => {
    // With the API's kill switch off the router is absent: a tab here would
    // offer a Start button that can only 404.
    vi.stubEnv("NEXT_PUBLIC_RESEARCH_ENABLED", "false");
    renderPage();
    expect(
      screen.queryByRole("tab", {
        name: en.TripDetail.research.tabLabel,
      }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("tab", { name: en.TripDetail.tabs.itinerary }),
    ).toBeInTheDocument();
  });

  it("opens the Research tab from ?tab=research (the chat card's link)", () => {
    vi.stubEnv("NEXT_PUBLIC_RESEARCH_ENABLED", "true");
    search.tab = "research";
    renderPage();
    expect(
      screen.getByRole("tab", { name: en.TripDetail.research.tabLabel }),
    ).toHaveAttribute("aria-selected", "true");
  });

  it("falls back to the itinerary for ?tab=research while research is disabled", () => {
    vi.stubEnv("NEXT_PUBLIC_RESEARCH_ENABLED", "false");
    search.tab = "research";
    renderPage();
    expect(
      screen.getByRole("tab", { name: en.TripDetail.tabs.itinerary }),
    ).toHaveAttribute("aria-selected", "true");
  });
});
