import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { client } from "@/lib/api/client";
import { qk } from "@/lib/api/keys";
import type { components } from "@/lib/api/schema";

export type TripBudget = components["schemas"]["TripBudget"];
export type TripBudgetSet = components["schemas"]["TripBudgetSet"];
export type BudgetCategories = components["schemas"]["BudgetCategories"];
export type CategoryBudget = components["schemas"]["CategoryBudget"];

/** GET /trips/{id}/budget — per-category caps vs booked spend. 404 if unknown. */
export function useBudget(tripId: string) {
  return useQuery({
    queryKey: qk.budget(tripId),
    queryFn: async () => {
      const { data, error } = await client.GET("/trips/{trip_id}/budget", {
        params: { path: { trip_id: tripId } },
      });
      if (error) throw error;
      return data;
    },
  });
}

/**
 * POST /trips/{id}/budget — full replacement of caps (omitted categories become
 * uncapped). Invalidates the budget (caps changed) and the trip (totals surface
 * on the trip header).
 */
export function useSetBudget(tripId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: TripBudgetSet) => {
      const { data, error } = await client.POST("/trips/{trip_id}/budget", {
        params: { path: { trip_id: tripId } },
        body,
      });
      if (error) throw error;
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.budget(tripId) });
      queryClient.invalidateQueries({ queryKey: qk.trip(tripId) });
    },
  });
}
