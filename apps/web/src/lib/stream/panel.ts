// Side-panel artifact types — mirror of apps/api/app/streaming/panels.py.
//
// A panel-capable agent tool emits a `panel` SSE event carrying a structured
// payload the chat drawer renders by `kind`. Only `route` has a typed shape
// today (the first panel-capable tool); `places`/`weather` arrive with their
// tool conversions. The transport keeps `kind`/`data` loose so unknown kinds
// pass through forward-compatibly; renderers narrow per kind.

export type PanelKind = "route" | "places" | "weather";

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
