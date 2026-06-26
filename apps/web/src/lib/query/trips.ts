"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { client } from "@/lib/api/client";
import { qk } from "@/lib/api/keys";
import type { components } from "@/lib/api/schema";

export type Trip = components["schemas"]["Trip"];
export type TripDetail = components["schemas"]["TripDetail"];
export type TripCreate = components["schemas"]["TripCreate"];
export type TripUpdate = components["schemas"]["TripUpdate"];
export type TripListResponse = components["schemas"]["TripListResponse"];

export type TripListParams = {
  limit?: number;
  offset?: number;
};

/** GET /trips — paginated list (newest first). */
export function useTrips(params?: TripListParams) {
  return useQuery({
    queryKey: params ? qk.trips(params) : qk.trips(),
    queryFn: async () => {
      const { data, error } = await client.GET("/trips", {
        params: { query: params },
      });
      if (error) throw error;
      return data;
    },
  });
}

/** GET /trips/{id} — single trip enriched with total_spent / gaps / places. */
export function useTrip(id: string) {
  return useQuery({
    queryKey: qk.trip(id),
    enabled: id.length > 0,
    queryFn: async () => {
      const { data, error } = await client.GET("/trips/{trip_id}", {
        params: { path: { trip_id: id } },
      });
      if (error) throw error;
      return data;
    },
  });
}

/** POST /trips — the client middleware auto-adds the Idempotency-Key header. */
export function useCreateTrip() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: TripCreate) => {
      const { data, error } = await client.POST("/trips", { body });
      if (error) throw error;
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.trips() });
    },
  });
}

/** PUT /trips/{id} — full replacement (fields minus items). */
export function useUpdateTrip(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: TripUpdate) => {
      const { data, error } = await client.PUT("/trips/{trip_id}", {
        params: { path: { trip_id: id } },
        body,
      });
      if (error) throw error;
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.trips() });
      queryClient.invalidateQueries({ queryKey: qk.trip(id) });
    },
  });
}

/** DELETE /trips/{id}. */
export function useDeleteTrip() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await client.DELETE("/trips/{trip_id}", {
        params: { path: { trip_id: id } },
      });
      if (error) throw error;
    },
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: qk.trips() });
      queryClient.invalidateQueries({ queryKey: qk.trip(id) });
    },
  });
}
