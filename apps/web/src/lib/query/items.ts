"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { client, unwrap } from "@/lib/api/client";
import { OverBudgetError, throwOn409 } from "@/lib/api/errors";
import { qk } from "@/lib/api/keys";
import type { components } from "@/lib/api/schema";

export type TripItem = components["schemas"]["TripItem"];
export type TripItemCreate = components["schemas"]["TripItemCreate"];
export type TripItemUpdate = components["schemas"]["TripItemUpdate"];
export type TripItemKind = components["schemas"]["TripItemKind"];
export type TripItemStatus = components["schemas"]["TripItemStatus"];
export type TripDetail = components["schemas"]["TripDetail"];

// Re-exported so existing callers (ItineraryTab, tests) keep their import path.
export { OverBudgetError };

/**
 * Build a COMPLETE `TripItemUpdate` body from a stored item. PUT is a full
 * replace (the BE schema is identical to create and includes `sort_order`), so
 * every field — including the optional ones — must be present. Sending a partial
 * body would wipe the omitted fields. Optional fields are normalised to `null`
 * rather than dropped so the replacement is unambiguous.
 */
export function toUpdateBody(item: TripItem): TripItemUpdate {
  return {
    day: item.day,
    kind: item.kind,
    status: item.status,
    title: item.title,
    sort_order: item.sort_order,
    place_id: item.place_id ?? null,
    booking_id: item.booking_id ?? null,
    start_time: item.start_time ?? null,
    notes: item.notes ?? null,
  };
}

// Items live inside TripDetail (qk.trip) and the budget rollup changes whenever
// items change, so both keys are invalidated together on every mutation.
function invalidateItemQueries(
  queryClient: ReturnType<typeof useQueryClient>,
  tripId: string,
): void {
  queryClient.invalidateQueries({ queryKey: qk.items(tripId) });
  queryClient.invalidateQueries({ queryKey: qk.trip(tripId) });
}

/**
 * POST /trips/{id}/items — the client middleware auto-adds the Idempotency-Key
 * header. A 409 (over-budget) is surfaced as `OverBudgetError` carrying the
 * BE hint so callers can show a toast/notice.
 */
export function useAddItem(tripId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: TripItemCreate) => {
      const { data, error, response } = await client.POST(
        "/trips/{trip_id}/items",
        { params: { path: { trip_id: tripId } }, body },
      );
      if (error) {
        throwOn409(response, error, OverBudgetError);
        throw error;
      }
      return data;
    },
    onSuccess: () => invalidateItemQueries(queryClient, tripId),
  });
}

/**
 * PUT /trips/{id}/items/{itemId} — FULL REPLACE. Reads the current item, merges
 * the requested `changes`, and sends the COMPLETE `TripItemUpdate` body
 * (including `sort_order`). Never a partial PUT.
 */
export function useUpdateItem(tripId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      item,
      changes,
    }: {
      item: TripItem;
      changes: Partial<TripItemUpdate>;
    }) =>
      unwrap(
        client.PUT("/trips/{trip_id}/items/{item_id}", {
          params: { path: { trip_id: tripId, item_id: item.id } },
          body: { ...toUpdateBody(item), ...changes },
        }),
      ),
    onSuccess: () => invalidateItemQueries(queryClient, tripId),
  });
}

/** DELETE /trips/{id}/items/{itemId}. */
export function useDeleteItem(tripId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (itemId: string) =>
      unwrap(
        client.DELETE("/trips/{trip_id}/items/{item_id}", {
          params: { path: { trip_id: tripId, item_id: itemId } },
        }),
      ),
    onSuccess: () => invalidateItemQueries(queryClient, tripId),
  });
}

interface ReorderVars {
  a: TripItem;
  b: TripItem;
}

interface ReorderContext {
  prev?: TripDetail;
}

/**
 * Swap the `sort_order` of two adjacent items via two full-replace PUTs.
 * OPTIMISTIC: the swap is written to the cached TripDetail immediately and
 * rolled back if either PUT fails.
 *
 * NOTE: the two PUTs are NOT server-side atomic — if the first succeeds and the
 * second fails, the BE is left with both items sharing one `sort_order`. The
 * optimistic rollback below only restores the *client* cache; `onSettled`
 * re-fetches to surface the true server state. A batch/transactional reorder
 * endpoint would be the proper fix if this becomes user-visible.
 */
export function useReorderItem(tripId: string) {
  const queryClient = useQueryClient();
  return useMutation<void, Error, ReorderVars, ReorderContext>({
    mutationFn: async ({ a, b }) => {
      // Full-replace bodies with sort_order swapped — never partial.
      await unwrap(
        client.PUT("/trips/{trip_id}/items/{item_id}", {
          params: { path: { trip_id: tripId, item_id: a.id } },
          body: { ...toUpdateBody(a), sort_order: b.sort_order },
        }),
      );
      await unwrap(
        client.PUT("/trips/{trip_id}/items/{item_id}", {
          params: { path: { trip_id: tripId, item_id: b.id } },
          body: { ...toUpdateBody(b), sort_order: a.sort_order },
        }),
      );
    },
    onMutate: async ({ a, b }) => {
      await queryClient.cancelQueries({ queryKey: qk.trip(tripId) });
      const prev = queryClient.getQueryData<TripDetail>(qk.trip(tripId));
      if (prev?.items) {
        queryClient.setQueryData<TripDetail>(qk.trip(tripId), {
          ...prev,
          items: prev.items.map((it) =>
            it.id === a.id
              ? { ...it, sort_order: b.sort_order }
              : it.id === b.id
                ? { ...it, sort_order: a.sort_order }
                : it,
          ),
        });
      }
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) queryClient.setQueryData(qk.trip(tripId), ctx.prev);
    },
    onSettled: () => invalidateItemQueries(queryClient, tripId),
  });
}
