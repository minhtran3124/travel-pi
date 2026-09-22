// Side-panel artifact types — mirror of apps/api/app/streaming/panels.py.
//
// A panel-capable agent tool emits a `panel` SSE event carrying a structured
// payload the chat drawer renders by `kind`. `route` and `weather` have typed
// shapes today; `places` arrives with its tool conversion. The transport keeps
// `kind`/`data` loose so unknown kinds pass through forward-compatibly;
// renderers narrow per kind.

export type PanelKind =
  | "route"
  | "places"
  | "weather"
  | "air_quality"
  | "flights"
  | "hotels"
  // Derived FE-only panel (not streamed): the finished trip-research plan. Its
  // `toolCallId` is `research-plan:<runId>`, so `panelKey` ("research_plan")
  // stays stable and a plan never renders twice.
  | "research_plan";

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

/** US-AQI category band — drives the hero gradient + dial/glow. Mirror of `_AQI_BAND`. */
export type AqiBand =
  | "good"
  | "moderate"
  | "usg"
  | "unhealthy"
  | "vunhealthy"
  | "hazardous"
  | "unknown";

export interface AirQualityPanelPollutant {
  label: string;
  value: number | null;
  unit: string;
  desc: string;
}

export interface AirQualityPanelDay {
  date: string;
  max_us_aqi: number | null;
  category: string;
  emoji: string;
  band: AqiBand;
}

export interface AirQualityPanelData {
  location_name: string;
  country: string | null;
  timezone: string;
  time: string;
  us_aqi: number | null;
  category: string;
  emoji: string;
  band: AqiBand;
  advice: string;
  pollutants: AirQualityPanelPollutant[];
  forecast: AirQualityPanelDay[];
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

export interface FlightsPanelFlight {
  id: string;
  flight_number: string;
  airline_name: string;
  airline_code: string;
  origin: string;
  destination: string;
  departure_time: string; // ISO (model_dump mode="json")
  arrival_time: string;
  duration_minutes: number;
  stops: number;
  seats_available: number;
  price: number;
  currency: string;
}

export interface FlightsPanelData {
  origin: string;
  destination: string;
  departure_date: string;
  results_count: number;
  cheapest_price: number;
  flights: FlightsPanelFlight[];
}

export interface HotelsPanelHotel {
  id: string;
  image_url: string;
  name: string;
  star_rating: number;
  price_per_night: number;
  currency: string;
  total_price: number;
  available: boolean;
  available_rooms: number;
  rating: number;
  review_count: number;
  amenities: string[];
  description: string;
}

export interface HotelsPanelData {
  city: string;
  check_in: string;
  check_out: string;
  nights: number;
  rooms: number;
  results_count: number;
  cheapest_total: number;
  hotels: HotelsPanelHotel[];
}

export interface PlacesPanelPlace {
  id: string;
  name: string;
  city: string;
  country: string;
  category: string;
  description: string;
  address: string;
  rating: number;
  review_count: number;
  price_level: number;
  opening_hours: string | null;
  image_url: string;
  tags: string[];
  is_recommended: boolean;
}

export interface PlacesPanelData {
  city: string | null;
  category: string | null;
  /** Canonical category slug, never localized — panel identity. Missing → null. */
  category_key?: string | null;
  results_count: number;
  places: PlacesPanelPlace[];
}

/** One side-panel payload, as accumulated by the stream hook. Identity is `panelKey`, not `kind`. */
export interface PanelArtifact {
  toolCallId: string;
  kind: string;
  data: unknown;
  /** Traveller's language the payload was localized to (e.g. "vi"). Absent → "en". */
  language?: string;
}

/** Places-category sub-key, or `null` when the panel has no (or an unset) category. */
function placesCategory(p: PanelArtifact): string | null {
  if (p.kind !== "places" || typeof p.data !== "object" || p.data === null) return null;
  const category = (p.data as PlacesPanelData).category;
  return typeof category === "string" && category.length > 0 ? category : null;
}

/**
 * Panel-identity category slug: prefers the canonical, never-localized
 * `category_key` (falls back to `category` when absent, e.g. older payloads)
 * so a language switch mid-conversation can't split one category into two tabs.
 */
function placesCategoryKey(p: PanelArtifact): string | null {
  if (p.kind !== "places" || typeof p.data !== "object" || p.data === null) return null;
  const categoryKey = (p.data as PlacesPanelData).category_key;
  if (typeof categoryKey === "string" && categoryKey.length > 0) return categoryKey;
  return placesCategory(p);
}

/** Identity key for a panel: `kind:category` for a places panel with a category, else bare `kind`. */
export function panelKey(p: PanelArtifact): string {
  const category = placesCategoryKey(p);
  return category ? `${p.kind}:${category}` : p.kind;
}

/** Human-readable sub-label for a panel's tab, e.g. the (localized) places category; `null` when there isn't one. */
export function panelSubLabel(p: PanelArtifact): string | null {
  return placesCategory(p);
}
