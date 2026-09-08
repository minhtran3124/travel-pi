"use client";

import { useMutation, useQuery } from "@tanstack/react-query";

import { client, unwrap } from "@/lib/api/client";
import { PremiumRequiredError, throwOn403 } from "@/lib/api/errors";
import { qk } from "@/lib/api/keys";
import type { components } from "@/lib/api/schema";

export type Flight = components["schemas"]["Flight"];
export type FlightSearchResponse = components["schemas"]["FlightSearchResponse"];
export type FlightBookingRequest = components["schemas"]["FlightBookingRequest"];
export type Booking = components["schemas"]["Booking"];

// Re-exported so call sites can `instanceof`-check without a separate import.
export { PremiumRequiredError };

// A type alias (not an interface) so it carries an implicit index signature and
// stays assignable to `qk.flightSearch`'s `Record<string, unknown>` parameter.
export type FlightSearchFilters = {
  origin: string;
  destination: string;
  departure_date: string;
  adults?: number;
  return_date?: string;
  airline?: string;
  max_price?: number;
  max_stops?: number;
};

/** GET /flights/search — one-way or round-trip flights for a route and date. */
export function useFlightSearch(filters: FlightSearchFilters, enabled = true) {
  return useQuery({
    queryKey: qk.flightSearch(filters),
    enabled,
    queryFn: () =>
      unwrap(client.GET("/flights/search", { params: { query: filters } })),
  });
}

/**
 * POST /flights/book. A 403 (tier gate) is surfaced as `PremiumRequiredError`
 * so callers can show an upgrade prompt instead of a generic error.
 */
export function useBookFlight() {
  return useMutation({
    mutationFn: async (body: FlightBookingRequest) => {
      const { data, error, response } = await client.POST("/flights/book", {
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
