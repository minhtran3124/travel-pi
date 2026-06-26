"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";

import { client, unwrap } from "@/lib/api/client";
import { DuplicatePlaceError, throwOn409 } from "@/lib/api/errors";
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

// Re-exported so existing callers (SavedPlaceCard, tests) keep their import path.
export { DuplicatePlaceError };

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

// A type alias (not an interface) so it carries an implicit index signature and
// stays assignable to `qk.placeSearch`'s `Record<string, unknown>` parameter.
export type PlaceSearchFilters = {
  city?: string;
  category?: PlaceCategory;
  min_rating?: string;
  price_level?: string;
  recommended?: boolean;
  sort?: PlaceSort;
};

// Prefix key matching every saved-places query regardless of its filter suffix
// (`["savedPlaces"]` and `["savedPlaces", filters]`). Used to cancel/snapshot/
// invalidate the whole family during optimistic flag writes.
const savedPlacesPrefix = qk.savedPlaces();

/** GET /places/saved — newest first, optionally filtered by city/category/flags. */
export function useSavedPlaces(filters?: SavedPlaceFilters) {
  return useQuery({
    queryKey: filters ? qk.savedPlaces(filters) : qk.savedPlaces(),
    queryFn: () =>
      unwrap(client.GET("/places/saved", { params: { query: filters } })),
  });
}

/** GET /places/search — catalog search; unknown city yields `total: 0`, not 404. */
export function usePlaceSearch(filters: PlaceSearchFilters, enabled = true) {
  return useQuery({
    queryKey: qk.placeSearch(filters),
    enabled,
    queryFn: () =>
      unwrap(client.GET("/places/search", { params: { query: filters } })),
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
        throwOn409(response, error, DuplicatePlaceError);
        throw error;
      }
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: savedPlacesPrefix });
    },
  });
}

/** DELETE /places/saved/{id} — soft delete; accepts a UUID or SPL- code. */
export function useDeleteSavedPlace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(
        client.DELETE("/places/saved/{saved_id}", {
          params: { path: { saved_id: id } },
        }),
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: savedPlacesPrefix });
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
  await queryClient.cancelQueries({ queryKey: savedPlacesPrefix });
  const snapshots = queryClient.getQueriesData<SavedPlaceListResponse>({
    queryKey: savedPlacesPrefix,
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
    mutationFn: ({ id, value }: FlagVars) =>
      unwrap(
        client.POST("/places/saved/{saved_id}/favorite", {
          params: { path: { saved_id: id } },
          body: { value },
        }),
      ),
    onMutate: (vars) => applyOptimisticFlag(queryClient, "favorite", vars),
    onError: (_err, _vars, snapshots) => rollbackFlag(queryClient, snapshots),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: savedPlacesPrefix });
    },
  });
}

/** POST /places/saved/{id}/visited — idempotent SET; optimistic with rollback. */
export function useSetVisited() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, value }: FlagVars) =>
      unwrap(
        client.POST("/places/saved/{saved_id}/visited", {
          params: { path: { saved_id: id } },
          body: { value },
        }),
      ),
    onMutate: (vars) => applyOptimisticFlag(queryClient, "visited", vars),
    onError: (_err, _vars, snapshots) => rollbackFlag(queryClient, snapshots),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: savedPlacesPrefix });
    },
  });
}
