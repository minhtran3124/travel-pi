"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";

import { client } from "@/lib/api/client";
import { qk } from "@/lib/api/keys";
import type { components } from "@/lib/api/schema";

export type SavedPlace = components["schemas"]["SavedPlace"];
export type SavedPlaceCreate = components["schemas"]["SavedPlaceCreate"];
export type SavedPlaceListResponse =
  components["schemas"]["SavedPlaceListResponse"];
export type Place = components["schemas"]["Place"];
export type PlaceSearchResponse = components["schemas"]["PlaceSearchResponse"];
export type PlaceCategory = components["schemas"]["PlaceCategory"];
export type PlaceSort = components["schemas"]["PlaceSort"];

/** Where a picked place came from — the shared vocabulary used by the shortlist. */
export type PlaceSource = "catalog" | "saved";

// A type alias (not an interface) so it carries an implicit index signature and
// stays assignable to `qk.savedPlaces`'s `Record<string, unknown>` parameter.
export type SavedPlaceFilters = {
  city?: string;
  category?: string;
  favorite?: boolean;
  visited?: boolean;
};

export interface PlaceSearchFilters {
  city?: string;
  category?: PlaceCategory;
  min_rating?: string;
  price_level?: string;
  recommended?: boolean;
  sort?: PlaceSort;
}

/**
 * Raised by `useCreateSavedPlace` when the BE reports a duplicate (409). Carries
 * the `hint` (the existing place's `SPL-` short code) so the UI can point the
 * user at the place they already have instead of crashing.
 */
export class DuplicatePlaceError extends Error {
  readonly hint?: string;
  constructor(message: string, hint?: string) {
    super(message);
    this.name = "DuplicatePlaceError";
    this.hint = hint;
  }
}

// Prefix key matching every saved-places query regardless of its filter suffix
// (`["savedPlaces"]` and `["savedPlaces", filters]`). Used to cancel/snapshot/
// invalidate the whole family during optimistic flag writes.
const SAVED_PLACES_PREFIX = ["savedPlaces"] as const;

/** GET /places/saved — newest first, optionally filtered by city/category/flags. */
export function useSavedPlaces(filters?: SavedPlaceFilters) {
  return useQuery({
    queryKey: filters ? qk.savedPlaces(filters) : qk.savedPlaces(),
    queryFn: async () => {
      const { data, error } = await client.GET("/places/saved", {
        params: { query: filters },
      });
      if (error) throw error;
      return data;
    },
  });
}

/** GET /places/search — catalog search; unknown city yields `total: 0`, not 404. */
export function usePlaceSearch(filters: PlaceSearchFilters, enabled = true) {
  return useQuery({
    queryKey: ["placeSearch", filters] as const,
    enabled,
    queryFn: async () => {
      const { data, error } = await client.GET("/places/search", {
        params: { query: filters },
      });
      if (error) throw error;
      return data;
    },
  });
}

/**
 * POST /places/saved. A 409 (duplicate) is surfaced as `DuplicatePlaceError`
 * carrying the existing short code so callers can show a friendly notice.
 */
export function useCreateSavedPlace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: SavedPlaceCreate) => {
      const { data, error, response } = await client.POST("/places/saved", {
        body,
      });
      if (error) {
        if (response.status === 409) {
          throw new DuplicatePlaceError(error.message, error.hint ?? undefined);
        }
        throw error;
      }
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: SAVED_PLACES_PREFIX });
    },
  });
}

/** DELETE /places/saved/{id} — soft delete; accepts a UUID or SPL- code. */
export function useDeleteSavedPlace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await client.DELETE("/places/saved/{saved_id}", {
        params: { path: { saved_id: id } },
      });
      if (error) throw error;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: SAVED_PLACES_PREFIX });
    },
  });
}

// --- Optimistic flag writes --------------------------------------------------

interface FlagVars {
  id: string;
  value: boolean;
}

type SavedSnapshot = [readonly unknown[], SavedPlaceListResponse | undefined][];

/**
 * Optimistically write `flag = value` onto the matching saved place across every
 * cached saved-places query. Returns the prior snapshots so `onError` can roll back.
 */
async function applyOptimisticFlag(
  queryClient: QueryClient,
  flag: "favorite" | "visited",
  { id, value }: FlagVars,
): Promise<SavedSnapshot> {
  await queryClient.cancelQueries({ queryKey: SAVED_PLACES_PREFIX });
  const snapshots = queryClient.getQueriesData<SavedPlaceListResponse>({
    queryKey: SAVED_PLACES_PREFIX,
  });
  for (const [key, prev] of snapshots) {
    if (!prev) continue;
    queryClient.setQueryData<SavedPlaceListResponse>(key, {
      ...prev,
      results: prev.results.map((p) =>
        p.id === id ? { ...p, [flag]: value } : p,
      ),
    });
  }
  return snapshots;
}

function rollbackFlag(queryClient: QueryClient, snapshots?: SavedSnapshot): void {
  snapshots?.forEach(([key, prev]) => queryClient.setQueryData(key, prev));
}

/**
 * POST /places/saved/{id}/favorite — idempotent SET (client sends the target
 * boolean). Optimistic: writes the flag immediately, rolls back on error,
 * re-syncs on settle.
 */
export function useSetFavorite() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, value }: FlagVars) => {
      const { data, error } = await client.POST(
        "/places/saved/{saved_id}/favorite",
        { params: { path: { saved_id: id } }, body: { value } },
      );
      if (error) throw error;
      return data;
    },
    onMutate: (vars) => applyOptimisticFlag(queryClient, "favorite", vars),
    onError: (_err, _vars, snapshots) => rollbackFlag(queryClient, snapshots),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: SAVED_PLACES_PREFIX });
    },
  });
}

/** POST /places/saved/{id}/visited — idempotent SET; optimistic with rollback. */
export function useSetVisited() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, value }: FlagVars) => {
      const { data, error } = await client.POST(
        "/places/saved/{saved_id}/visited",
        { params: { path: { saved_id: id } }, body: { value } },
      );
      if (error) throw error;
      return data;
    },
    onMutate: (vars) => applyOptimisticFlag(queryClient, "visited", vars),
    onError: (_err, _vars, snapshots) => rollbackFlag(queryClient, snapshots),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: SAVED_PLACES_PREFIX });
    },
  });
}
