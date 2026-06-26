"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { client } from "@/lib/api/client";
import { qk } from "@/lib/api/keys";
import type { components } from "@/lib/api/schema";
import type { PlaceSource } from "@/lib/query/places";

export type ShortlistEntry = components["schemas"]["ShortlistEntry"];

/**
 * Raised by `useAddToShortlist` when the BE reports the place is already on the
 * trip's shortlist (409). Surfaced as a distinct type so the UI can show a
 * friendly, non-crashing notice instead of treating it as a hard error.
 */
export class AlreadyShortlistedError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AlreadyShortlistedError";
  }
}

/** GET /trips/{id}/places — a PLAIN `ShortlistEntry[]`, not a PagedResponse. */
export function useShortlist(tripId: string) {
  return useQuery({
    queryKey: qk.shortlist(tripId),
    queryFn: async () => {
      const { data, error } = await client.GET("/trips/{trip_id}/places", {
        params: { path: { trip_id: tripId } },
      });
      if (error) throw error;
      return data;
    },
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
        if (response.status === 409) {
          throw new AlreadyShortlistedError(error.message);
        }
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
    mutationFn: async (linkId: string) => {
      const { error } = await client.DELETE(
        "/trips/{trip_id}/places/{link_id}",
        { params: { path: { trip_id: tripId, link_id: linkId } } },
      );
      if (error) throw error;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.shortlist(tripId) });
    },
  });
}
