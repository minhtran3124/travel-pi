import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { server } from "@/test/msw";
import { qk } from "@/lib/api/keys";
import {
  OverBudgetError,
  useAddItem,
  useReorderItem,
  useUpdateItem,
  type TripDetail,
  type TripItem,
} from "./items";

const TRIP_ID = "33333333-3333-3333-3333-333333333333";

// Every field of TripItemUpdate that a full-replace PUT must carry.
const UPDATE_FIELDS = [
  "day",
  "kind",
  "status",
  "title",
  "sort_order",
  "place_id",
  "booking_id",
  "start_time",
  "notes",
] as const;

function makeItem(overrides: Partial<TripItem> = {}): TripItem {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    trip_id: TRIP_ID,
    day: 1,
    kind: "place",
    status: "pending",
    title: "Marble Mountains",
    sort_order: 0,
    place_id: null,
    booking_id: null,
    start_time: null,
    notes: null,
    ...overrides,
  };
}

function wrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

function freshClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

describe("useUpdateItem (full replace)", () => {
  it("sends a COMPLETE TripItemUpdate body (all fields present, not partial)", async () => {
    const item = makeItem({ start_time: "09:00", notes: "bring water" });
    const queryClient = freshClient();
    let captured: Record<string, unknown> | undefined;

    server.use(
      http.put("*/trips/:tripId/items/:itemId", async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(item, { status: 200 });
      }),
    );

    const { result } = renderHook(() => useUpdateItem(TRIP_ID), {
      wrapper: wrapper(queryClient),
    });

    await act(async () => {
      await result.current.mutateAsync({
        item,
        changes: { title: "Renamed" },
      });
    });

    expect(captured).toBeDefined();
    // Every TripItemUpdate field must be present — a partial PUT would drop them.
    for (const field of UPDATE_FIELDS) {
      expect(captured).toHaveProperty(field);
    }
    expect(captured?.title).toBe("Renamed");
    expect(captured?.sort_order).toBe(0);
    expect(captured?.start_time).toBe("09:00");
  });
});

describe("useReorderItem (full-replace swap, optimistic)", () => {
  it("swaps sort_order via two COMPLETE PUT bodies", async () => {
    const a = makeItem({ id: "a", sort_order: 0, title: "First" });
    const b = makeItem({ id: "b", sort_order: 1, title: "Second" });
    const queryClient = freshClient();
    const bodies: Record<string, unknown>[] = [];

    server.use(
      http.put("*/trips/:tripId/items/:itemId", async ({ request, params }) => {
        const body = (await request.json()) as Record<string, unknown>;
        bodies.push({ ...body, _itemId: params.itemId });
        return HttpResponse.json(makeItem(), { status: 200 });
      }),
    );

    const { result } = renderHook(() => useReorderItem(TRIP_ID), {
      wrapper: wrapper(queryClient),
    });

    await act(async () => {
      await result.current.mutateAsync({ a, b });
    });

    expect(bodies).toHaveLength(2);
    for (const body of bodies) {
      for (const field of UPDATE_FIELDS) {
        expect(body).toHaveProperty(field);
      }
    }
    // a took b's sort_order and vice versa.
    const aBody = bodies.find((x) => x._itemId === "a");
    const bBody = bodies.find((x) => x._itemId === "b");
    expect(aBody?.sort_order).toBe(1);
    expect(bBody?.sort_order).toBe(0);
  });

  it("rolls back the optimistic swap when a PUT fails", async () => {
    const a = makeItem({ id: "a", sort_order: 0 });
    const b = makeItem({ id: "b", sort_order: 1 });
    const detail = {
      id: TRIP_ID,
      title: "Trip",
      items: [a, b],
    } as unknown as TripDetail;
    const queryClient = freshClient();
    queryClient.setQueryData(qk.trip(TRIP_ID), detail);

    server.use(
      http.put("*/trips/:tripId/items/:itemId", () =>
        HttpResponse.json(
          {
            error: "ServerError",
            message: "boom",
            status_code: 500,
            path: "/trips/x/items/y",
          },
          { status: 500 },
        ),
      ),
    );

    const { result } = renderHook(() => useReorderItem(TRIP_ID), {
      wrapper: wrapper(queryClient),
    });

    act(() => {
      result.current.mutate({ a, b });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));

    const rolledBack = queryClient.getQueryData<TripDetail>(qk.trip(TRIP_ID));
    const ra = rolledBack?.items?.find((it) => it.id === "a");
    const rb = rolledBack?.items?.find((it) => it.id === "b");
    expect(ra?.sort_order).toBe(0);
    expect(rb?.sort_order).toBe(1);
  });
});

describe("useAddItem", () => {
  it("attaches an Idempotency-Key header (via client middleware)", async () => {
    const queryClient = freshClient();
    let key: string | null = null;

    server.use(
      http.post("*/trips/:tripId/items", ({ request }) => {
        key = request.headers.get("Idempotency-Key");
        return HttpResponse.json(makeItem(), { status: 201 });
      }),
    );

    const { result } = renderHook(() => useAddItem(TRIP_ID), {
      wrapper: wrapper(queryClient),
    });

    await act(async () => {
      await result.current.mutateAsync({
        day: 1,
        kind: "place",
        status: "pending",
        title: "New stop",
        sort_order: 0,
      });
    });

    expect(key).toBeTruthy();
  });

  it("surfaces an OverBudgetError with the hint on 409", async () => {
    const queryClient = freshClient();

    server.use(
      http.post("*/trips/:tripId/items", () =>
        HttpResponse.json(
          {
            error: "ConflictError",
            message: "Linked booking exceeds the budget cap",
            status_code: 409,
            path: "/trips/x/items",
            hint: "hotels cap exceeded by $120",
          },
          { status: 409 },
        ),
      ),
    );

    const { result } = renderHook(() => useAddItem(TRIP_ID), {
      wrapper: wrapper(queryClient),
    });

    await expect(
      result.current.mutateAsync({
        day: 1,
        kind: "place",
        status: "booked",
        title: "Pricey hotel",
        sort_order: 0,
        booking_id: "BK-ABCD1234",
      }),
    ).rejects.toBeInstanceOf(OverBudgetError);

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as OverBudgetError).hint).toBe(
      "hotels cap exceeded by $120",
    );
  });
});
