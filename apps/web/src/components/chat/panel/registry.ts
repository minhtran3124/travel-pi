import dynamic from "next/dynamic";
import type { ComponentType } from "react";

import { WeatherPanel } from "./WeatherPanel";

// Lazy-load the route renderer (and its MapLibre bundle + CSS) only when a route
// panel actually renders; ssr:false since the map is a client-only canvas.
const RoutePanel = dynamic(
  () => import("./RoutePanel").then((m) => m.RoutePanel),
  { ssr: false },
);

/**
 * kind → renderer. A renderer receives the panel's `data` (it narrows the
 * `unknown` per its kind). Unknown kinds are absent here, so the drawer renders
 * nothing for them — forward-compatible with a `places` panel added when its
 * tool becomes panel-capable.
 */
export const PANEL_RENDERERS: Record<string, ComponentType<{ data: unknown }>> = {
  route: RoutePanel as unknown as ComponentType<{ data: unknown }>,
  weather: WeatherPanel as unknown as ComponentType<{ data: unknown }>,
};

export const PANEL_LABELS: Record<string, string> = {
  route: "Route",
  places: "Places",
  weather: "Weather",
};
