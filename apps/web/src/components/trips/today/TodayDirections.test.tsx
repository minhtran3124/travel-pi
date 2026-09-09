import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { server } from "@/test/msw";
import type { components } from "@/lib/api/schema";
import en from "../../../../messages/en.json";
import { TodayDirections } from "./TodayDirections";

type DayPlanItem = components["schemas"]["DayPlanItem"];

// RoutePanel lazily imports maplibre-gl inside an effect; stub it so the map
// draws nothing in jsdom (same mock RoutePanel's own test uses).
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

function item(placeId: string | null): DayPlanItem {
  return {
    item: { place_id: placeId, status: "pending", title: "x" },
  } as unknown as DayPlanItem;
}

function renderDirections(
  previous: DayPlanItem | null,
  next: DayPlanItem | null,
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <NextIntlClientProvider locale="en" messages={en}>
      <QueryClientProvider client={queryClient}>
        <TodayDirections previous={previous} next={next} />
      </QueryClientProvider>
    </NextIntlClientProvider>,
  );
}

const ROUTE = {
  origin: {
    kind: "place",
    id: "place-a",
    name: "Hotel",
    latitude: 16.06,
    longitude: 108.22,
  },
  destination: {
    kind: "place",
    id: "place-b",
    name: "Dragon Bridge",
    latitude: 16.07,
    longitude: 108.23,
  },
  straight_line_km: 1.9,
  recommended_mode: "car",
  legs: [
    { mode: "walk", profile: "foot-walking", distance_km: 2.1, duration_minutes: 26 },
    { mode: "car", profile: "driving-car", distance_km: 2.4, duration_minutes: 7 },
  ],
  source: "estimate",
  geometry: null,
  attribution: "OpenRouteService",
};

const UNAVAILABLE = en.Today.directions.unavailable;

describe("TodayDirections", () => {
  it("renders a route through RoutePanel when both items have a place", async () => {
    server.use(
      http.get("*/places/route", () => HttpResponse.json(ROUTE)),
    );

    renderDirections(item("place-a"), item("place-b"));

    await waitFor(() =>
      expect(screen.getByText("Hotel → Dragon Bridge")).toBeInTheDocument(),
    );
    // The Maps deep-link is derived from the endpoint coordinates, exactly as
    // the backend panel builder derives it.
    const link = screen.getByRole("link", { name: /open in google maps/i });
    expect(link).toHaveAttribute(
      "href",
      "https://www.google.com/maps/dir/?api=1&origin=16.06,108.22&destination=16.07,108.23",
    );
    expect(screen.queryByText(UNAVAILABLE)).not.toBeInTheDocument();
  });

  it("renders the unavailable note and fires NO request when the next item has no place", async () => {
    let called = false;
    server.use(
      http.get("*/places/route", () => {
        called = true;
        return HttpResponse.json(ROUTE);
      }),
    );

    renderDirections(item("place-a"), item(null));

    expect(screen.getByText(UNAVAILABLE)).toBeInTheDocument();
    // Flush microtasks; a disabled query never reaches the network.
    await Promise.resolve();
    expect(called).toBe(false);
  });

  it("renders the unavailable note when previous is null", () => {
    renderDirections(null, item("place-b"));
    expect(screen.getByText(UNAVAILABLE)).toBeInTheDocument();
  });
});
