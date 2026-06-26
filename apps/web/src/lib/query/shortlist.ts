"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { client, unwrap } from "@/lib/api/client";
import { AlreadyShortlistedError, throwOn409 } from "@/lib/api/errors";
import { qk } from "@/lib/api/keys";
import type { components } from "@/lib/api/schema";
import type { PlaceSource } from "@/lib/query/places";

export type ShortlistEntry = components["schemas"]["ShortlistEntry"];

// Re-exported so existing callers (ShortlistTab, tests) keep their import path.
export { AlreadyShortlistedError };

/** GET /trips/{id}/places — a PLAIN `ShortlistEntry[]`, not a PagedResponse. */
export function useShortlist(tripId: string) {
  return useQuery({
    queryKey: qk.shortlist(tripId),
    queryFn: () =>
      unwrap(
        client.GET("/trips/{trip_id}/places", {
          params: { path: { trip_id: tripId } },
        }),
      ),
  });
}

interface AddToShortlistVars {
  place_id: string;
  source: PlaceSource;
}

/**
 * POST /trips/{id}/places. A 409 (already shortlisted) is surfaced as an
 * `AlreadyShortlistedError` so callers can show a friendly notice rather than
 * crashing on a duplicate add.
 */
export function useAddToShortlist(tripId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ place_id, source }: AddToShortlistVars) => {
      const { data, error, response } = await client.POST(
        "/trips/{trip_id}/places",
        {
          params: { path: { trip_id: tripId } },
          body: { place_id, source },
        },
      );
      if (error) {
        throwOn409(response, error, AlreadyShortlistedError);
        throw error;
      }
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.shortlist(tripId) });
    },
  });
}

/** DELETE /trips/{id}/places/{link_id} — removes by `link_id`, NOT place_id. */
export function useRemoveFromShortlist(tripId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (linkId: string) =>
      unwrap(
        client.DELETE("/trips/{trip_id}/places/{link_id}", {
          params: { path: { trip_id: tripId, link_id: linkId } },
        }),
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.shortlist(tripId) });
    },
  });
}
