// Side-panel artifact types — mirror of apps/api/app/streaming/panels.py.
//
// A panel-capable agent tool emits a `panel` SSE event carrying a structured
// payload the chat drawer renders by `kind`. `route` and `weather` have typed
// shapes today; `places` arrives with its tool conversion. The transport keeps
// `kind`/`data` loose so unknown kinds pass through forward-compatibly;
// renderers narrow per kind.

export type PanelKind = "route" | "places" | "weather";

/** Sky-mood bucket — drives the hero gradient + card tint. Mirror of `_condition`. */
export type WeatherCondition =
  | "clear"
  | "partly"
  | "cloud"
  | "rain"
  | "snow"
  | "storm";

export interface WeatherPanelCurrent {
  temperature_c: number;
  apparent_temperature_c: number;
  relative_humidity: number;
  wind_speed_kmh: number;
  description: string;
  emoji: string;
  condition: WeatherCondition;
  time: string;
}

export interface WeatherPanelDay {
  date: string;
  temp_min_c: number;
  temp_max_c: number;
  precipitation_probability_max: number | null;
  description: string;
  emoji: string;
  condition: WeatherCondition;
}

export interface WeatherPanelData {
  location_name: string;
  country: string | null;
  timezone: string;
  current: WeatherPanelCurrent;
  daily: WeatherPanelDay[];
  attribution: string;
}

export interface RoutePanelEndpoint {
  name: string;
  lat: number;
  lng: number;
}

export interface RoutePanelLeg {
  mode: string;
  distance_km: number;
  duration_minutes: number;
}

export interface RoutePanelData {
  origin: RoutePanelEndpoint;
  destination: RoutePanelEndpoint;
  recommended_mode: string;
  legs: RoutePanelLeg[];
  straight_line_km: number;
  source: string;
  /** ORS road line as [lng, lat] pairs; null in estimate mode (draw a straight line). */
  geometry: [number, number][] | null;
  gmaps_url: string;
}

/** One side-panel payload, as accumulated by the stream hook. */
export interface PanelArtifact {
  toolCallId: string;
  kind: string;
  data: unknown;
}
