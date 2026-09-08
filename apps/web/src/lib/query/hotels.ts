"use client";

import { useMutation, useQuery } from "@tanstack/react-query";

import { client, unwrap } from "@/lib/api/client";
import { PremiumRequiredError, throwOn403 } from "@/lib/api/errors";
import { qk } from "@/lib/api/keys";
import type { components } from "@/lib/api/schema";

export type Hotel = components["schemas"]["Hotel"];
export type HotelSearchResponse = components["schemas"]["HotelSearchResponse"];
export type HotelBookingRequest = components["schemas"]["HotelBookingRequest"];
export type Booking = components["schemas"]["Booking"];

// Re-exported so call sites can `instanceof`-check without a separate import.
export { PremiumRequiredError };

// A type alias (not an interface) so it carries an implicit index signature and
// stays assignable to `qk.hotelSearch`'s `Record<string, unknown>` parameter.
export type HotelSearchFilters = {
  city: string;
  min_stars?: number;
  max_price?: number;
  amenities?: string[];
};

/** GET /hotels/search — browse hotels in a city, no dates (discovery). */
export function useHotelSearch(filters: HotelSearchFilters, enabled = true) {
  return useQuery({
    queryKey: qk.hotelSearch(filters),
    enabled,
    queryFn: () =>
      unwrap(client.GET("/hotels/search", { params: { query: filters } })),
  });
}

/**
 * POST /hotels/book. A 403 (tier gate) is surfaced as `PremiumRequiredError`
 * so callers can show an upgrade prompt instead of a generic error.
 */
export function useBookHotel() {
  return useMutation({
    mutationFn: async (body: HotelBookingRequest) => {
      const { data, error, response } = await client.POST("/hotels/book", {
        body,
      });
      if (error) {
        throwOn403(response, error, PremiumRequiredError);
        throw error;
      }
      return data;
    },
  });
}
