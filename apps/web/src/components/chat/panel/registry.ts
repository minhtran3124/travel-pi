import dynamic from "next/dynamic";
import type { ComponentType } from "react";

import { AirQualityPanel } from "./AirQualityPanel";
import { FlightsPanel } from "./FlightsPanel";
import { HotelsPanel } from "./HotelsPanel";
import { PlacesPanel } from "./PlacesPanel";
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
 * nothing for them — forward-compatible with future panel kinds added when their
 * tools become panel-capable.
 */
export const PANEL_RENDERERS: Record<string, ComponentType<{ data: unknown }>> = {
  route: RoutePanel as unknown as ComponentType<{ data: unknown }>,
  places: PlacesPanel as unknown as ComponentType<{ data: unknown }>,
  weather: WeatherPanel as unknown as ComponentType<{ data: unknown }>,
  air_quality: AirQualityPanel as unknown as ComponentType<{ data: unknown }>,
  flights: FlightsPanel as unknown as ComponentType<{ data: unknown }>,
  hotels: HotelsPanel as unknown as ComponentType<{ data: unknown }>,
};

/**
 * panel kind → `Panel.tabs.*` translation key. Resolved via `useTranslations`
 * at render (in SidePanel) so the tab labels follow the streamed panel language.
 */
export const PANEL_LABEL_KEYS: Record<string, string> = {
  route: "tabs.route",
  places: "tabs.places",
  weather: "tabs.weather",
  air_quality: "tabs.airQuality",
  flights: "tabs.flights",
  hotels: "tabs.hotels",
};
