import { useQuery } from "@tanstack/react-query";

import { client, unwrap } from "@/lib/api/client";
import { qk } from "@/lib/api/keys";
import type { components } from "@/lib/api/schema";

export type DayPlanResponse = components["schemas"]["DayPlanResponse"];
export type WeatherResponse = components["schemas"]["WeatherResponse"];
export type AirQualityResponse = components["schemas"]["AirQualityResponse"];
export type RouteResponse = components["schemas"]["RouteResponse"];

/** GET /trips/{id}/day-plan — the ordered plan for one calendar date. */
export function useDayPlan(tripId: string, date: string) {
  return useQuery({
    queryKey: qk.dayPlan(tripId, date),
    queryFn: () =>
      unwrap(
        client.GET("/trips/{trip_id}/day-plan", {
          params: { path: { trip_id: tripId }, query: { date } },
        }),
      ),
    enabled: tripId.length > 0 && date.length > 0,
  });
}

/** GET /weather — current conditions for a city. */
export function useWeather(city: string) {
  return useQuery({
    queryKey: qk.weather(city),
    queryFn: () =>
      unwrap(client.GET("/weather", { params: { query: { city } } })),
    enabled: city.length > 0,
  });
}

/** GET /air-quality — current US-AQI reading for a city. */
export function useAirQuality(city: string) {
  return useQuery({
    queryKey: qk.airQuality(city),
    queryFn: () =>
      unwrap(client.GET("/air-quality", { params: { query: { city } } })),
    enabled: city.length > 0,
  });
}

/** GET /places/route — distance, time and mode between two places. */
export function useRoute(fromPlaceId: string, toPlaceId: string) {
  return useQuery({
    queryKey: qk.placesRoute(fromPlaceId, toPlaceId),
    queryFn: () =>
      unwrap(
        client.GET("/places/route", {
          params: {
            query: { origin: fromPlaceId, destination: toPlaceId },
          },
        }),
      ),
    enabled: fromPlaceId.length > 0 && toPlaceId.length > 0,
  });
}
