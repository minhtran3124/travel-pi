"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { client } from "@/lib/api/client";
import { qk } from "@/lib/api/keys";
import type { components } from "@/lib/api/schema";

export type TripItem = components["schemas"]["TripItem"];
export type TripItemCreate = components["schemas"]["TripItemCreate"];
export type TripItemUpdate = components["schemas"]["TripItemUpdate"];
export type TripItemKind = components["schemas"]["TripItemKind"];
export type TripItemStatus = components["schemas"]["TripItemStatus"];
export type TripDetail = components["schemas"]["TripDetail"];

/**
 * Raised by `useAddItem` when the BE rejects the item because a linked
 * `booking_id` would push the trip over a budget cap (409). Carries the BE
 * `hint` so the UI can surface a precise over-budget notice instead of crashing.
 */
export class OverBudgetError extends Error {
  readonly hint?: string;
  constructor(message: string, hint?: string) {
    super(message);
    this.name = "OverBudgetError";
    this.hint = hint;
  }
}

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
        if (response.status === 409) {
          throw new OverBudgetError(error.message, error.hint ?? undefined);
        }
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
    mutationFn: async ({
      item,
      changes,
    }: {
      item: TripItem;
      changes: Partial<TripItemUpdate>;
    }) => {
      const body: TripItemUpdate = { ...toUpdateBody(item), ...changes };
      const { data, error } = await client.PUT(
        "/trips/{trip_id}/items/{item_id}",
        { params: { path: { trip_id: tripId, item_id: item.id } }, body },
      );
      if (error) throw error;
      return data;
    },
    onSuccess: () => invalidateItemQueries(queryClient, tripId),
  });
}

/** DELETE /trips/{id}/items/{itemId}. */
export function useDeleteItem(tripId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (itemId: string) => {
      const { error } = await client.DELETE(
        "/trips/{trip_id}/items/{item_id}",
        { params: { path: { trip_id: tripId, item_id: itemId } } },
      );
      if (error) throw error;
    },
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
 */
export function useReorderItem(tripId: string) {
  const queryClient = useQueryClient();
  return useMutation<void, Error, ReorderVars, ReorderContext>({
    mutationFn: async ({ a, b }) => {
      // Full-replace bodies with sort_order swapped — never partial.
      const aBody: TripItemUpdate = {
        ...toUpdateBody(a),
        sort_order: b.sort_order,
      };
      const bBody: TripItemUpdate = {
        ...toUpdateBody(b),
        sort_order: a.sort_order,
      };
      const r1 = await client.PUT("/trips/{trip_id}/items/{item_id}", {
        params: { path: { trip_id: tripId, item_id: a.id } },
        body: aBody,
      });
      if (r1.error) throw r1.error;
      const r2 = await client.PUT("/trips/{trip_id}/items/{item_id}", {
        params: { path: { trip_id: tripId, item_id: b.id } },
        body: bBody,
      });
      if (r2.error) throw r2.error;
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
