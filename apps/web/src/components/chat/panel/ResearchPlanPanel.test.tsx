import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { server } from "@/test/msw";
import type { Flight, Hotel, Place } from "@/lib/query/research";

import en from "../../../../messages/en.json";
import { PanelIntlProvider } from "./PanelIntlProvider";

// The map is a client-only MapLibre canvas; a stub lets us assert the markers
// (numbered badges, place-name labels) the panel hands it without loading GL in jsdom.
vi.mock("@/components/map/TripMap", () => ({
  TripMap: ({ markers }: { markers: Array<{ label: string; badge?: string }> }) => (
    <div
      data-testid="trip-map"
      data-badges={markers.map((m) => m.badge).join(",")}
      data-labels={markers.map((m) => m.label).join(",")}
    />
  ),
}));

import { ResearchPlanPanel, type ResearchPlanPanelData } from "./ResearchPlanPanel";

const BASE = "/api/be";
const TRIP_ID = "trip-1";
const RUN_ID = "run-1";

function place(overrides: Partial<Place> & { id: string; name: string }): Place {
  return {
    city: "Da Nang",
    country: "Vietnam",
    category: "cafe",
    description: "A place.",
    address: "1 Beach Rd",
    rating: 4.7,
    review_count: 120,
    price_level: 2,
    image_url: "https://example.test/p.jpg",
    tags: [],
    is_recommended: false,
    short_code: "PLC-000001",
    latitude: 16.05,
    longitude: 108.24,
    ...overrides,
  } as Place;
}

function flight(): Flight {
  return {
    id: "f1",
    airline: { code: "VN", name: "Vietnam Airlines" },
    flight_number: "VN456",
    origin: "SGN",
    destination: "DAD",
    departure_time: "2026-10-25T16:15:00",
    arrival_time: "2026-10-25T17:35:00",
    duration_minutes: 80,
    price: 139,
    currency: "USD",
    seats_available: 12,
    stops: 0,
  };
}

function hotel(): Hotel {
  return {
    id: "h1",
    code: "DAD001",
    name: "Cham Hotel",
    city: "Da Nang",
    country: "Vietnam",
    address: "2 River Rd",
    star_rating: 3,
    price_per_night: 35,
    currency: "USD",
    amenities: ["wifi"],
    image_url: "https://example.test/h.jpg",
    rating: 4.4,
    review_count: 300,
    description: "A hotel.",
    property_type: "Hotel",
    chain: "Independent",
    check_in_time: "14:00",
    check_out_time: "12:00",
    breakfast_included: true,
    free_cancellation: true,
    languages_spoken: ["English"],
    short_code: "HTL-000001",
  };
}

interface Overrides {
  proposal?: Record<string, unknown>;
  summary?: string;
  totalCap?: number | null;
  placeStatus?: Record<string, number>;
  places?: Record<string, Partial<Place>>;
}

function useHandlers(o: Overrides) {
  const proposal = o.proposal ?? {};
  server.use(
    http.get(`${BASE}/agent/research/:runId/files/*`, ({ request }) => {
      const url = new URL(request.url);
      if (url.pathname.endsWith("proposal.json")) {
        return HttpResponse.json({ content: JSON.stringify(proposal) });
      }
      if (url.pathname.endsWith("summary.md")) {
        return HttpResponse.json({ content: o.summary ?? "" });
      }
      return HttpResponse.json({ content: "" });
    }),
    http.get(`${BASE}/places/:id`, ({ params }) => {
      const id = String(params.id);
      const status = o.placeStatus?.[id];
      if (status) return HttpResponse.json({ message: "gone" }, { status });
      const names: Record<string, string> = { p1: "Lighthouse Coffee", p2: "Dragon Bridge" };
      return HttpResponse.json(
        place({ id, name: names[id] ?? id, category: "attraction", ...o.places?.[id] }),
      );
    }),
    http.get(`${BASE}/flights/:id`, () => HttpResponse.json(flight())),
    http.get(`${BASE}/hotels/:id`, () => HttpResponse.json(hotel())),
    http.get(`${BASE}/trips/:tripId/budget`, () =>
      o.totalCap === undefined
        ? HttpResponse.json({ message: "no budget" }, { status: 404 })
        : HttpResponse.json({
            trip_id: TRIP_ID,
            categories: {},
            total_cap: o.totalCap,
            total_spent: 0,
            booked_total: 0,
            total_remaining: o.totalCap,
            over_budget: false,
          }),
    ),
    http.get(`${BASE}/trips/:tripId`, () =>
      HttpResponse.json({
        id: TRIP_ID,
        title: "Da Nang trip",
        city: "Da Nang",
        start_date: "2026-10-25",
        end_date: "2026-10-30",
        travelers: 2,
        notes: null,
        created_at: "2026-09-01T00:00:00Z",
        items: [],
        total_spent: 0,
        gaps: [],
        places: [],
      }),
    ),
  );
}

function renderPanel(
  files: string[],
  data: Partial<ResearchPlanPanelData> = {},
  locale: "en" | "vi" = "en",
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <PanelIntlProvider language={locale}>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </PanelIntlProvider>
  );
  return render(
    <ResearchPlanPanel
      data={{ tripId: TRIP_ID, runId: RUN_ID, files, review: null, ...data }}
    />,
    { wrapper: Wrapper },
  );
}

const FILES = ["plan/proposal.json", "summary.md"];
const rp = en.Panel.researchPlan;

const FULL_PROPOSAL = {
  itinerary: [
    { day: 1, time: "09:30", place_id: "p2", title: "Bridge" },
    { day: 1, time: "08:00", place_id: "p1", title: "Coffee" },
  ],
  shortlist: [],
  flights: ["f1"],
  hotels: ["h1"],
  budget_estimate: 275,
};

describe("ResearchPlanPanel", () => {
  it("switches between the three tabs", async () => {
    useHandlers({ proposal: FULL_PROPOSAL, summary: "- A short overview", totalCap: 375 });
    renderPanel(FILES);

    // Overview is the default: the summary and the budget line show.
    expect(await screen.findByText("A short overview")).toBeInTheDocument();
    expect(await screen.findByText("275 / 375 USD")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: rp.tabs.byDay }));
    expect(await screen.findByText("Lighthouse Coffee")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: rp.tabs.flightsStays }));
    expect(await screen.findByText(/Vietnam Airlines/)).toBeInTheDocument();
    expect(await screen.findByText("Cham Hotel")).toBeInTheDocument();
  });

  it("By day lists stops in time order and hands numbered markers to the map", async () => {
    useHandlers({ proposal: FULL_PROPOSAL, totalCap: 375 });
    renderPanel(FILES);

    fireEvent.click(screen.getByRole("button", { name: rp.tabs.byDay }));

    // The two stops resolve to their names, ordered by clock time (08:00 first).
    expect(await screen.findByText("Lighthouse Coffee")).toBeInTheDocument();
    const items = within(screen.getByRole("list")).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Lighthouse Coffee");
    expect(items[1]).toHaveTextContent("Dragon Bridge");

    // Markers are numbered in the same order and match the pins.
    await waitFor(() =>
      expect(screen.getByTestId("trip-map").dataset.badges).toBe("1,2"),
    );
    // The popup names the place, not the number.
    expect(screen.getByTestId("trip-map").dataset.labels).toBe(
      "Lighthouse Coffee,Dragon Bridge",
    );
  });

  it("shows flight and hotel cards on the Flights & stays tab", async () => {
    useHandlers({ proposal: FULL_PROPOSAL, totalCap: null });
    renderPanel(FILES);

    fireEvent.click(screen.getByRole("button", { name: rp.tabs.flightsStays }));
    expect(await screen.findByText("SGN → DAD")).toBeInTheDocument();
    expect(await screen.findByText("Cham Hotel")).toBeInTheDocument();
  });

  it("never renders a place id, flight id, or the map without coordinates", async () => {
    useHandlers({
      proposal: {
        itinerary: [{ day: 1, time: "08:00", place_id: "p1", title: "Coffee" }],
        shortlist: [],
        flights: [],
        hotels: [],
        budget_estimate: null,
      },
      places: { p1: { latitude: null, longitude: null } },
    });
    renderPanel(["plan/proposal.json"]);

    fireEvent.click(screen.getByRole("button", { name: rp.tabs.byDay }));
    expect(await screen.findByText("Lighthouse Coffee")).toBeInTheDocument();
    // No coordinates on any stop → the map is skipped, not blanked.
    expect(screen.queryByTestId("trip-map")).toBeNull();
    // The raw id never reaches the DOM.
    expect(screen.queryByText("p1")).toBeNull();
  });

  it("falls back to the summary and the Research-tab link with an empty proposal", async () => {
    useHandlers({
      proposal: {
        itinerary: [],
        shortlist: [],
        flights: [],
        hotels: [],
        budget_estimate: null,
      },
      summary: "- Nothing structured, but here is the gist",
    });
    renderPanel(FILES);

    expect(
      await screen.findByText("Nothing structured, but here is the gist"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: new RegExp(rp.fullReport) }),
    ).toHaveAttribute("href", `/trips/${TRIP_ID}?tab=research`);

    // By day and Flights & stays degrade to their empty hints, never crash.
    fireEvent.click(screen.getByRole("button", { name: rp.tabs.byDay }));
    expect(screen.getByText(rp.byDayEmpty)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: rp.tabs.flightsStays }));
    expect(screen.getByText(rp.empty)).toBeInTheDocument();
  });

  it("degrades a failed place lookup to the stop's own title", async () => {
    useHandlers({
      placeStatus: { p1: 404 },
      proposal: {
        itinerary: [{ day: 1, time: "08:00", place_id: "p1", title: "Coffee stop" }],
        shortlist: [],
        flights: [],
        hotels: [],
        budget_estimate: null,
      },
    });
    renderPanel(["plan/proposal.json"]);

    fireEvent.click(screen.getByRole("button", { name: rp.tabs.byDay }));
    expect(await screen.findByText("Coffee stop")).toBeInTheDocument();
    expect(screen.queryByText("Lighthouse Coffee")).toBeNull();
  });

  it("disables Apply and shows the updating notice while a newer run is running", async () => {
    useHandlers({ proposal: FULL_PROPOSAL, totalCap: 375 });
    renderPanel(FILES, { updating: true });

    const apply = await screen.findByRole("button", { name: rp.apply });
    expect(apply).toBeDisabled();
    expect(screen.getByText(rp.updating)).toBeInTheDocument();
  });

  it("enables Apply and hides the updating notice when not updating", async () => {
    useHandlers({ proposal: FULL_PROPOSAL, totalCap: 375 });
    renderPanel(FILES);

    const apply = await screen.findByRole("button", { name: rp.apply });
    expect(apply).not.toBeDisabled();
    expect(screen.queryByText(rp.updating)).toBeNull();
  });

  it("renders the Vietnamese tab labels", async () => {
    useHandlers({ proposal: FULL_PROPOSAL, totalCap: 375 });
    renderPanel(FILES, {}, "vi");

    expect(
      screen.getByRole("button", { name: "Tổng quan" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Theo ngày" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Bay & ở" })).toBeInTheDocument();
  });
});
