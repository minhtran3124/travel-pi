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
  | "hotels";

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
  results_count: number;
  places: PlacesPanelPlace[];
}

/** One side-panel payload, as accumulated by the stream hook. */
export interface PanelArtifact {
  toolCallId: string;
  kind: string;
  data: unknown;
}
