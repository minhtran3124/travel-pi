"use client";

import { useQuery } from "@tanstack/react-query";

import { client, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

export type Place = components["schemas"]["Place"];
export type Flight = components["schemas"]["Flight"];
export type Hotel = components["schemas"]["Hotel"];

// Single-resource lookups the plan view resolves an id at a time. Keys are local
// (not in `qk`) since only the research plan reads them; React Query dedupes
// repeated ids across cards by key, so each id is fetched at most once.

/** GET /places/{id} — resolves one itinerary/shortlist place. */
export function usePlaceLookup(id: string | null) {
  return useQuery({
    queryKey: ["research", "place", id] as const,
    enabled: id != null,
    retry: false,
    queryFn: () =>
      unwrap(
        client.GET("/places/{place_id}", {
          params: { path: { place_id: id! } },
        }),
      ),
  });
}

/** GET /flights/{id} — resolves one proposed flight offer. */
export function useFlightLookup(id: string | null) {
  return useQuery({
    queryKey: ["research", "flight", id] as const,
    enabled: id != null,
    retry: false,
    queryFn: () =>
      unwrap(
        client.GET("/flights/{flight_id}", {
          params: { path: { flight_id: id! } },
        }),
      ),
  });
}

/** GET /hotels/{id} — resolves one proposed hotel. */
export function useHotelLookup(id: string | null) {
  return useQuery({
    queryKey: ["research", "hotel", id] as const,
    enabled: id != null,
    retry: false,
    queryFn: () =>
      unwrap(
        client.GET("/hotels/{hotel_id}", {
          params: { path: { hotel_id: id! } },
        }),
      ),
  });
}
