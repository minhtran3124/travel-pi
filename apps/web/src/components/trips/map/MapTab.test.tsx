import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { NextIntlClientProvider } from "next-intl";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { server } from "@/test/msw";

import en from "../../../../messages/en.json";
import { MapTab } from "./MapTab";

const BASE = "/api/be";
const TRIP_ID = "trip-1";

// maplibre-gl does not run under jsdom (WebGL) — mocked the way RoutePanel's
// test mocks it, capturing constructor args so marker color/popup text (the
// per-day coloring and click summary) are assertable without a real canvas.
const mapInstance = {
  on: (ev: string, cb: () => void) => {
    if (ev === "load") cb();
  },
  addSource: vi.fn(),
  addLayer: vi.fn(),
  fitBounds: vi.fn(),
  remove: vi.fn(),
};
const MapMock = vi.fn(() => mapInstance);
const MarkerMock = vi.fn((opts: { color?: string }) => ({
  setLngLat: () => ({
    setPopup: (popup: { text: string }) => ({
      addTo: () => {
        markerPopups.push({ color: opts.color, text: popup.text });
      },
    }),
  }),
}));
let markerPopups: { color?: string; text: string }[] = [];

vi.mock("maplibre-gl/dist/maplibre-gl.css", () => ({}));
vi.mock("maplibre-gl", () => ({
  default: {
    Map: MapMock,
    Marker: MarkerMock,
    Popup: vi.fn(() => ({
      setText: (text: string) => ({ text }),
    })),
    LngLatBounds: vi.fn(() => ({ extend: vi.fn() })),
  },
}));

function makeTrip(overrides: Record<string, unknown> = {}) {
  return {
    id: TRIP_ID,
    title: "Da Nang long weekend",
    travelers: 2,
    created_at: "2026-01-01T00:00:00Z",
    total_spent: 0,
    places: [
      {
        link_id: "link-1",
        source: "catalog",
        place: {
          id: "place-1",
          name: "Dragon Bridge",
          city: "Da Nang",
          country: "Vietnam",
          category: "attraction",
          description: "",
          address: "",
          rating: 4.5,
          review_count: 10,
          price_level: 1,
          image_url: "",
          tags: [],
          is_recommended: false,
          latitude: 16.07,
          longitude: 108.23,
          short_code: "PLC-000001",
        },
      },
    ],
    items: [
      {
        id: "item-1",
        trip_id: TRIP_ID,
        day: 1,
        kind: "place",
        status: "pending",
        title: "Visit the bridge",
        sort_order: 0,
        place_id: "place-1",
      },
    ],
    ...overrides,
  };
}

function renderTab() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <NextIntlClientProvider locale="en" messages={en}>
      <QueryClientProvider client={queryClient}>
        <MapTab tripId={TRIP_ID} />
      </QueryClientProvider>
    </NextIntlClientProvider>,
  );
}

describe("MapTab", () => {
  beforeEach(() => {
    MapMock.mockClear();
    MarkerMock.mockClear();
    markerPopups = [];
  });

  it("plots the shortlisted place and the itinerary item, colored by day", async () => {
    server.use(
      http.get(`${BASE}/trips/:tripId`, () => HttpResponse.json(makeTrip())),
    );

    renderTab();

    await waitFor(() => expect(MapMock).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(markerPopups).toHaveLength(2));

    const saved = markerPopups.find((m) => m.text === "Dragon Bridge");
    const itinerary = markerPopups.find((m) =>
      m.text.includes("Visit the bridge"),
    );
    expect(saved).toBeTruthy();
    expect(itinerary).toBeTruthy();
    expect(itinerary?.text).toBe("Day 1 · Visit the bridge");
    // Distinct colors: the saved-place marker is neutral, the day-1 item isn't.
    expect(saved?.color).not.toBe(itinerary?.color);
  });

  it("shows an empty state when the trip has no located places or itinerary items", async () => {
    server.use(
      http.get(`${BASE}/trips/:tripId`, () =>
        HttpResponse.json(makeTrip({ places: [], items: [] })),
      ),
    );

    renderTab();

    await waitFor(() =>
      expect(
        screen.getByText("Nothing to show on the map yet"),
      ).toBeInTheDocument(),
    );
    expect(MapMock).not.toHaveBeenCalled();
  });

  it("shows an error state when the trip fails to load", async () => {
    server.use(
      http.get(`${BASE}/trips/:tripId`, () =>
        HttpResponse.json({ error: "NotFound", message: "no trip" }, { status: 404 }),
      ),
    );

    renderTab();

    await waitFor(() =>
      expect(screen.getByText("Couldn't load the map")).toBeInTheDocument(),
    );
  });
});
