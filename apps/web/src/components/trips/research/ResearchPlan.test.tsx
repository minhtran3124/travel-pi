import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it } from "vitest";

import { server } from "@/test/msw";
import type { Flight, Hotel, Place } from "@/lib/query/research";

import en from "../../../../messages/en.json";
import { ResearchPlan } from "./ResearchPlan";

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
    rating: 4.6,
    review_count: 120,
    price_level: 2,
    image_url: "https://example.test/p.jpg",
    tags: [],
    is_recommended: false,
    short_code: "PLC-000001",
    ...overrides,
  };
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
  files?: string[];
  fileContent?: (path: string) => string;
  totalCap?: number | null;
  placeStatus?: Record<string, number>;
}

/** Register the file/lookup/budget handlers a plan render pulls on. */
function useHandlers(o: Overrides) {
  const proposal = o.proposal ?? {};
  server.use(
    http.get(`${BASE}/agent/research/:runId/files/*`, ({ request }) => {
      const url = new URL(request.url);
      if (url.pathname.endsWith("proposal.json")) {
        return HttpResponse.json({ content: JSON.stringify(proposal) });
      }
      const content = o.fileContent ? o.fileContent(url.pathname) : "";
      return HttpResponse.json({ content });
    }),
    http.get(`${BASE}/places/:id`, ({ params }) => {
      const id = String(params.id);
      const status = o.placeStatus?.[id];
      if (status) return HttpResponse.json({ message: "gone" }, { status });
      const names: Record<string, string> = {
        p1: "Lighthouse Coffee",
        p2: "Dragon Bridge",
      };
      return HttpResponse.json(place({ id, name: names[id] ?? id }));
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
  );
}

function renderPlan(files: string[]) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <NextIntlClientProvider locale="en" messages={en}>
      <QueryClientProvider client={queryClient}>
        <ResearchPlan tripId={TRIP_ID} runId={RUN_ID} files={files} review={null} />
      </QueryClientProvider>
    </NextIntlClientProvider>,
  );
}

const FULL_FILES = [
  "plan/proposal.json",
  "summary.md",
  "research/flights.md",
  "research/stays.md",
  "research/budget.md",
  "research/entry-and-season.md",
  "research/days/day-1.md",
];

describe("ResearchPlan", () => {
  it("renders the header, itinerary place names, a flight card, a hotel card, and the budget bar", async () => {
    useHandlers({
      totalCap: 375,
      proposal: {
        itinerary: [
          { day: 1, time: "08:00", place_id: "p1", title: "Coffee" },
          { day: 1, time: "09:30", place_id: "p2", title: "Bridge" },
        ],
        shortlist: ["p1"],
        flights: ["f1"],
        hotels: ["h1"],
        budget_estimate: 275,
      },
    });

    renderPlan(FULL_FILES);

    expect(
      await screen.findByText(en.TripDetail.research.plan.readyTitle),
    ).toBeInTheDocument();
    expect(await screen.findByText("Lighthouse Coffee")).toBeInTheDocument();
    expect(await screen.findByText("Dragon Bridge")).toBeInTheDocument();
    expect(await screen.findByText(/Vietnam Airlines/)).toBeInTheDocument();
    expect(await screen.findByText("Cham Hotel")).toBeInTheDocument();
    // budgetLine: "{spent} / {cap} USD"
    expect(await screen.findByText("275 / 375 USD")).toBeInTheDocument();

    // The section nav jumps to each section the plan actually shows.
    const nav = screen.getByRole("navigation", {
      name: en.TripDetail.research.plan.navLabel,
    });
    const links = within(nav).getAllByRole("link");
    expect(links.map((a) => a.getAttribute("href"))).toEqual([
      "#research-itinerary",
      "#research-flights",
      "#research-stays",
      "#research-budget",
      "#research-entry",
    ]);
    for (const href of links.map((a) => a.getAttribute("href")!)) {
      expect(document.querySelector(href)).not.toBeNull();
    }
  });

  it("falls back to the stop's prose when a place lookup fails", async () => {
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

    renderPlan(["plan/proposal.json"]);

    // The failed lookup degrades to the proposal's own title, not a crash.
    expect(await screen.findByText("Coffee stop")).toBeInTheDocument();
    expect(screen.queryByText("Lighthouse Coffee")).not.toBeInTheDocument();
  });

  it("falls back to section prose when the proposal carries no ids", async () => {
    useHandlers({
      proposal: {
        itinerary: [],
        shortlist: [],
        flights: [],
        hotels: [],
        budget_estimate: null,
      },
      fileContent: (path) =>
        path.endsWith("flights.md") ? "Cheapest flight is VN456." : "",
    });

    renderPlan(["plan/proposal.json", "research/flights.md"]);

    expect(
      await screen.findByText("Cheapest flight is VN456."),
    ).toBeInTheDocument();
  });

  it("applies only the checked stops", async () => {
    const posted: unknown[] = [];
    useHandlers({
      proposal: {
        itinerary: [
          { day: 1, time: "08:00", place_id: "p1", title: "Coffee" },
          { day: 1, time: "09:30", place_id: "p2", title: "Bridge" },
        ],
        shortlist: [],
        flights: [],
        hotels: [],
        budget_estimate: null,
      },
    });
    server.use(
      http.post(`${BASE}/trips/:tripId/items`, async ({ request }) => {
        posted.push(await request.json());
        return HttpResponse.json({}, { status: 201 });
      }),
    );

    renderPlan(["plan/proposal.json"]);

    await screen.findByText("Lighthouse Coffee");
    // Uncheck the second stop (Dragon Bridge).
    const checkboxes = screen.getAllByRole("checkbox");
    expect(checkboxes).toHaveLength(2);
    fireEvent.click(checkboxes[1]);

    fireEvent.click(screen.getByRole("button", { name: en.TripDetail.research.apply }));

    await waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0]).toMatchObject({ place_id: "p1" });
  });
});
