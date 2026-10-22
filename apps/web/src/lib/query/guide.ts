import { useQuery } from "@tanstack/react-query";

import { client, unwrap } from "@/lib/api/client";
import { qk } from "@/lib/api/keys";
import type { components } from "@/lib/api/schema";

export type VisaResponse = components["schemas"]["VisaResponse"];
export type TipsResponse = components["schemas"]["TipsResponse"];
export type ClimateResponse = components["schemas"]["ClimateResponse"];

/** GET /visa — general, nationality-dependent entry guidance for a city. */
export function useVisa(city: string) {
  return useQuery({
    queryKey: qk.visa(city),
    queryFn: () =>
      unwrap(client.GET("/visa", { params: { query: { city } } })),
    enabled: city.length > 0,
  });
}

/** GET /tips — local tips merged from country- and city-level guidance. */
export function useTips(city: string) {
  return useQuery({
    queryKey: qk.tips(city),
    queryFn: () =>
      unwrap(client.GET("/tips", { params: { query: { city } } })),
    enabled: city.length > 0,
  });
}

/** GET /destinations/climate — monthly climate normals for a city. */
export function useClimate(city: string) {
  return useQuery({
    queryKey: qk.climate(city),
    queryFn: () =>
      unwrap(
        client.GET("/destinations/climate", { params: { query: { city } } }),
      ),
    enabled: city.length > 0,
  });
}
