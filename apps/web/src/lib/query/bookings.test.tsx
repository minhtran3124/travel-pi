import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { server } from "@/test/msw";

import { useBookings, useCancelBooking } from "./bookings";

const BASE = "/api/be";

function makeBooking(overrides: Record<string, unknown> = {}) {
  return {
    id: "c1e1f5a4-ce3a-5b24-8f2e-8a0a8b3c2c5a",
    type: "flight",
    reference_id: "FL-1",
    customer_name: "Ada Lovelace",
    customer_email: "ada@example.com",
    total_price: 420.5,
    currency: "USD",
    status: "confirmed",
    created_at: "2026-06-20T10:00:00Z",
    details: {
      kind: "flight",
      flight_id: "FL-1",
      flight_number: "VN123",
      airline: "Vietnam Airlines",
      origin: "SGN",
      destination: "HAN",
      departure_time: "2026-07-01T08:00:00Z",
      arrival_time: "2026-07-01T10:00:00Z",
      passenger_name: "Ada Lovelace",
      passenger_phone: null,
    },
    notes: null,
    confirmation_code: "ABC123",
    summary: "VN123 SGN → HAN",
    ...overrides,
  };
}

function wrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

describe("useBookings", () => {
  it("parses the PagedResponse list", async () => {
    server.use(
      http.get(`${BASE}/bookings`, () =>
        HttpResponse.json({
          total: 1,
          limit: 20,
          offset: 0,
          results: [makeBooking()],
        }),
      ),
    );

    const { result } = renderHook(() => useBookings(), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.total).toBe(1);
    expect(result.current.data?.results).toHaveLength(1);
    expect(result.current.data?.results[0].confirmation_code).toBe("ABC123");
    expect(result.current.data?.results[0].details.kind).toBe("flight");
  });
});

describe("useCancelBooking", () => {
  it("cancels and invalidates the list, triggering a refetch with the cancelled status", async () => {
    let cancelled = false;
    let listCalls = 0;

    server.use(
      http.get(`${BASE}/bookings`, () => {
        listCalls += 1;
        return HttpResponse.json({
          total: 1,
          limit: 20,
          offset: 0,
          results: [
            makeBooking({ status: cancelled ? "cancelled" : "confirmed" }),
          ],
        });
      }),
      http.post(`${BASE}/bookings/:id/cancel`, () => {
        cancelled = true;
        return HttpResponse.json(makeBooking({ status: "cancelled" }));
      }),
    );

    const { result } = renderHook(
      () => ({ list: useBookings(), cancel: useCancelBooking() }),
      { wrapper: wrapper() },
    );

    await waitFor(() => expect(result.current.list.isSuccess).toBe(true));
    expect(result.current.list.data?.results[0].status).toBe("confirmed");
    expect(listCalls).toBe(1);

    result.current.cancel.mutate("c1e1f5a4-ce3a-5b24-8f2e-8a0a8b3c2c5a");

    await waitFor(() =>
      expect(result.current.cancel.isSuccess).toBe(true),
    );
    expect(result.current.cancel.data?.status).toBe("cancelled");

    // Invalidation forces the list query to refetch and reflect the new status.
    await waitFor(() => {
      expect(listCalls).toBeGreaterThan(1);
      expect(result.current.list.data?.results[0].status).toBe("cancelled");
    });
  });
});
