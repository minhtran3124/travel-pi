import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { server } from "@/test/msw";
import en from "../../../../messages/en.json";
import { TodayTab } from "./TodayTab";

// TodayTab -> TodayDirections -> RoutePanel lazily imports maplibre-gl. The
// plan items below carry no place_id, so directions render the "unavailable"
// note and never mount the map, but stub maplibre defensively all the same.
vi.mock("maplibre-gl/dist/maplibre-gl.css", () => ({}));
vi.mock("maplibre-gl", () => ({
  default: {
    Map: vi.fn(() => ({
      on: (ev: string, cb: () => void) => {
        if (ev === "load") cb();
      },
      addSource: vi.fn(),
      addLayer: vi.fn(),
      fitBounds: vi.fn(),
      remove: vi.fn(),
    })),
    Marker: vi.fn(() => ({
      setLngLat: () => ({ setPopup: () => ({ addTo: () => undefined }) }),
    })),
    Popup: vi.fn(() => ({ setText: () => ({}) })),
    LngLatBounds: vi.fn(() => ({ extend: vi.fn() })),
  },
}));

const TRIP_ID = "33333333-3333-3333-3333-333333333333";
const today = en.Today;

function renderTab() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <NextIntlClientProvider locale="en" messages={en}>
      <QueryClientProvider client={queryClient}>
        <TodayTab tripId={TRIP_ID} />
      </QueryClientProvider>
    </NextIntlClientProvider>,
  );
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function tripResponse(overrides: Record<string, any> = {}) {
  return {
    id: TRIP_ID,
    title: "Da Nang trip",
    city: "Da Nang",
    start_date: "2026-09-01",
    end_date: "2026-09-30",
    travelers: 2,
    created_at: "2026-08-01T00:00:00Z",
    items: [],
    total_spent: 0,
    ...overrides,
  };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function serveTrip(trip: Record<string, any>) {
  server.use(http.get("*/trips/:tripId", () => HttpResponse.json(trip)));
}

describe("TodayTab", () => {
  beforeEach(() => {
    // Fake only Date so react-query and waitFor keep real timers.
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-09-15T12:00:00"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders today's plan, its travel time, and the weather/air cards inside the trip window", async () => {
    serveTrip(tripResponse());
    server.use(
      http.get("*/trips/:tripId/day-plan", () =>
        HttpResponse.json({
          trip_id: TRIP_ID,
          date: "2026-09-15",
          day: 1,
          items: [
            {
              item: {
                id: "i1",
                trip_id: TRIP_ID,
                day: 1,
                kind: "place",
                status: "pending",
                title: "Marble Mountains",
                sort_order: 0,
              },
              travel_to_next_minutes: 15,
            },
            {
              item: {
                id: "i2",
                trip_id: TRIP_ID,
                day: 1,
                kind: "place",
                status: "pending",
                title: "Dragon Bridge",
                sort_order: 1,
              },
              travel_to_next_minutes: null,
            },
          ],
        }),
      ),
      http.get("*/weather", () =>
        HttpResponse.json({
          city: "Da Nang",
          current: {
            time: "2026-09-15T12:00",
            temperature_c: 30,
            apparent_temperature_c: 34,
            relative_humidity: 70,
            wind_speed_kmh: 10,
            weather_code: 1,
            description: "Mainly clear",
          },
        }),
      ),
      http.get("*/air-quality", () =>
        HttpResponse.json({ city: "Da Nang", us_aqi: 42, category: "Good", pm2_5: 8 }),
      ),
    );

    renderTab();

    // The plan card and its items appear once the day-plan resolves.
    await waitFor(() =>
      expect(screen.getByText("Marble Mountains")).toBeInTheDocument(),
    );
    expect(screen.getByText(today.plan.title)).toBeInTheDocument();
    expect(screen.getByText("Dragon Bridge")).toBeInTheDocument();
    expect(screen.getByText("15 min to the next stop")).toBeInTheDocument();

    // Weather and air-quality cards render for the trip's city.
    expect(screen.getByText(today.weather.title)).toBeInTheDocument();
    expect(screen.getByText(today.air.title)).toBeInTheDocument();

    // It is not the "not in progress" state.
    expect(screen.queryByText(today.notInProgress.title)).not.toBeInTheDocument();
  });

  it("renders the dated not-in-progress state outside the trip window", async () => {
    serveTrip(
      tripResponse({ start_date: "2026-10-01", end_date: "2026-10-10" }),
    );

    renderTab();

    await waitFor(() =>
      expect(
        screen.getByText(today.notInProgress.title),
      ).toBeInTheDocument(),
    );
    // The dates variant carries both bounds.
    expect(
      screen.getByText("It runs 2026-10-01 – 2026-10-10."),
    ).toBeInTheDocument();
    // No plan is fetched or shown outside the window.
    expect(screen.queryByText(today.plan.title)).not.toBeInTheDocument();
  });
});
