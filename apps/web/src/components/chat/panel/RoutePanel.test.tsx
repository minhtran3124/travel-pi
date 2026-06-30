import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { RoutePanelData } from "@/lib/stream/panel";
import { RoutePanel } from "./RoutePanel";

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

vi.mock("maplibre-gl/dist/maplibre-gl.css", () => ({}));
vi.mock("maplibre-gl", () => ({
  default: {
    Map: MapMock,
    Marker: vi.fn(() => ({
      setLngLat: () => ({ setPopup: () => ({ addTo: () => undefined }) }),
    })),
    Popup: vi.fn(() => ({ setText: () => ({}) })),
    LngLatBounds: vi.fn(() => ({ extend: vi.fn() })),
  },
}));

const DATA: RoutePanelData = {
  origin: { name: "Hotel", lat: 16.06, lng: 108.22 },
  destination: { name: "Dragon Bridge", lat: 16.07, lng: 108.23 },
  recommended_mode: "car",
  legs: [
    { mode: "walk", distance_km: 2.1, duration_minutes: 26 },
    { mode: "car", distance_km: 2.4, duration_minutes: 7 },
  ],
  straight_line_km: 1.9,
  source: "estimate",
  geometry: null,
  gmaps_url:
    "https://www.google.com/maps/dir/?api=1&origin=16.06,108.22&destination=16.07,108.23",
};

describe("RoutePanel", () => {
  beforeEach(() => {
    MapMock.mockClear();
    mapInstance.addSource.mockClear();
  });

  it("renders the route headline, recommended leg and gmaps deep-link", () => {
    render(<RoutePanel data={DATA} />);
    expect(screen.getByText("Hotel → Dragon Bridge")).toBeInTheDocument();
    expect(screen.getByText(/2.4 km · ~7 min by car \(estimated\)/)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /open in google maps/i });
    expect(link).toHaveAttribute("href", DATA.gmaps_url);
    // one chip per mode
    expect(screen.getByText(/walk · 2.1 km · 26 min/)).toBeInTheDocument();
    expect(screen.getByText(/car · 2.4 km · 7 min/)).toBeInTheDocument();
  });

  it("initialises a MapLibre map and draws a straight line when geometry is null", async () => {
    render(<RoutePanel data={DATA} />);
    await waitFor(() => expect(MapMock).toHaveBeenCalledTimes(1));
    const lineCall = mapInstance.addSource.mock.calls.find((c) => c[0] === "route");
    expect(lineCall).toBeTruthy();
    expect(lineCall?.[1].data.geometry.coordinates).toEqual([
      [108.22, 16.06],
      [108.23, 16.07],
    ]);
  });
});
