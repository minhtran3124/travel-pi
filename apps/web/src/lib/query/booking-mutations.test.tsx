import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { server } from "@/test/msw";
import { PremiumRequiredError } from "@/lib/api/errors";
import { useBookFlight, type FlightBookingRequest } from "./flights";
import { useBookHotel, type HotelBookingRequest } from "./hotels";

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

const FLIGHT_BODY: FlightBookingRequest = {
  flight_id: "flight-1",
  passenger_name: "Nguyen Van A",
  passenger_email: "nguyen.a@example.com",
  passenger_phone: "+84 901 234 567",
};

const HOTEL_BODY: HotelBookingRequest = {
  hotel_id: "hotel-1",
  check_in: "2026-06-01",
  check_out: "2026-06-03",
  rooms: 1,
  adults: 2,
  children: 0,
  guest_name: "Nguyen Van A",
  guest_email: "nguyen.a@example.com",
  guest_phone: "+84 901 234 567",
};

describe("useBookFlight — 403", () => {
  it("raises PremiumRequiredError on a 403 response", async () => {
    server.use(
      http.post("*/flights/book", () =>
        HttpResponse.json(
          {
            error: "PremiumRequiredError",
            message: "Booking requires a premium plan",
            status_code: 403,
            path: "/flights/book",
            hint: "Upgrade to book flights",
          },
          { status: 403 },
        ),
      ),
    );

    const { result } = renderHook(() => useBookFlight(), {
      wrapper: wrapper(freshClient()),
    });

    await expect(result.current.mutateAsync(FLIGHT_BODY)).rejects.toMatchObject(
      { hint: "Upgrade to book flights" },
    );

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeInstanceOf(PremiumRequiredError);
  });

  it("sends an Idempotency-Key header", async () => {
    let capturedKey: string | null = null;
    server.use(
      http.post("*/flights/book", ({ request }) => {
        capturedKey = request.headers.get("Idempotency-Key");
        return HttpResponse.json(
          {
            error: "ValidationError",
            message: "not used",
            status_code: 422,
            path: "/flights/book",
          },
          { status: 422 },
        );
      }),
    );

    const { result } = renderHook(() => useBookFlight(), {
      wrapper: wrapper(freshClient()),
    });

    await expect(result.current.mutateAsync(FLIGHT_BODY)).rejects.toBeTruthy();
    expect(capturedKey).toBeTruthy();
  });

  it("reuses the same key when the same attempt is resubmitted after a failure", async () => {
    const capturedKeys: (string | null)[] = [];
    server.use(
      http.post("*/flights/book", ({ request }) => {
        capturedKeys.push(request.headers.get("Idempotency-Key"));
        return HttpResponse.error();
      }),
    );

    const { result } = renderHook(() => useBookFlight(), {
      wrapper: wrapper(freshClient()),
    });

    await expect(result.current.mutateAsync(FLIGHT_BODY)).rejects.toBeTruthy();
    await expect(result.current.mutateAsync(FLIGHT_BODY)).rejects.toBeTruthy();

    expect(capturedKeys).toHaveLength(2);
    expect(capturedKeys[0]).toBeTruthy();
    expect(capturedKeys[0]).toBe(capturedKeys[1]);
  });

  it("mints a fresh key for a new attempt after reset()", async () => {
    const capturedKeys: (string | null)[] = [];
    server.use(
      http.post("*/flights/book", ({ request }) => {
        capturedKeys.push(request.headers.get("Idempotency-Key"));
        return HttpResponse.error();
      }),
    );

    const { result } = renderHook(() => useBookFlight(), {
      wrapper: wrapper(freshClient()),
    });

    await expect(result.current.mutateAsync(FLIGHT_BODY)).rejects.toBeTruthy();
    result.current.reset();
    await expect(result.current.mutateAsync(FLIGHT_BODY)).rejects.toBeTruthy();

    expect(capturedKeys).toHaveLength(2);
    expect(capturedKeys[0]).toBeTruthy();
    expect(capturedKeys[1]).toBeTruthy();
    expect(capturedKeys[0]).not.toBe(capturedKeys[1]);
  });
});

describe("useBookHotel — 404 is not a PremiumRequiredError", () => {
  it("does not raise PremiumRequiredError on a 404 response", async () => {
    server.use(
      http.post("*/hotels/book", () =>
        HttpResponse.json(
          {
            error: "NotFoundError",
            message: "No hotel 'hotel-1'",
            status_code: 404,
            path: "/hotels/book",
          },
          { status: 404 },
        ),
      ),
    );

    const { result } = renderHook(() => useBookHotel(), {
      wrapper: wrapper(freshClient()),
    });

    await expect(result.current.mutateAsync(HOTEL_BODY)).rejects.toMatchObject(
      { message: "No hotel 'hotel-1'" },
    );

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).not.toBeInstanceOf(PremiumRequiredError);
  });

  it("raises PremiumRequiredError on a 403 response", async () => {
    server.use(
      http.post("*/hotels/book", () =>
        HttpResponse.json(
          {
            error: "PremiumRequiredError",
            message: "Booking requires a premium plan",
            status_code: 403,
            path: "/hotels/book",
            hint: "Upgrade to book hotels",
          },
          { status: 403 },
        ),
      ),
    );

    const { result } = renderHook(() => useBookHotel(), {
      wrapper: wrapper(freshClient()),
    });

    await expect(result.current.mutateAsync(HOTEL_BODY)).rejects.toMatchObject(
      { hint: "Upgrade to book hotels" },
    );

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeInstanceOf(PremiumRequiredError);
  });

  it("sends an Idempotency-Key header", async () => {
    let capturedKey: string | null = null;
    server.use(
      http.post("*/hotels/book", ({ request }) => {
        capturedKey = request.headers.get("Idempotency-Key");
        return HttpResponse.json(
          {
            error: "ValidationError",
            message: "not used",
            status_code: 422,
            path: "/hotels/book",
          },
          { status: 422 },
        );
      }),
    );

    const { result } = renderHook(() => useBookHotel(), {
      wrapper: wrapper(freshClient()),
    });

    await expect(result.current.mutateAsync(HOTEL_BODY)).rejects.toBeTruthy();
    expect(capturedKey).toBeTruthy();
  });

  it("reuses the same key when the same attempt is resubmitted after a failure", async () => {
    const capturedKeys: (string | null)[] = [];
    server.use(
      http.post("*/hotels/book", ({ request }) => {
        capturedKeys.push(request.headers.get("Idempotency-Key"));
        return HttpResponse.error();
      }),
    );

    const { result } = renderHook(() => useBookHotel(), {
      wrapper: wrapper(freshClient()),
    });

    await expect(result.current.mutateAsync(HOTEL_BODY)).rejects.toBeTruthy();
    await expect(result.current.mutateAsync(HOTEL_BODY)).rejects.toBeTruthy();

    expect(capturedKeys).toHaveLength(2);
    expect(capturedKeys[0]).toBeTruthy();
    expect(capturedKeys[0]).toBe(capturedKeys[1]);
  });
});

describe("cache invalidation on a successful booking", () => {
  it("useBookFlight invalidates the bookings list and the booked trip's budget", async () => {
    server.use(
      http.post("*/flights/book", () =>
        HttpResponse.json({
          id: "booking-1",
          type: "flight",
          reference_id: "flight-1",
          customer_name: "Nguyen Van A",
          customer_email: "nguyen.a@example.com",
          total_price: 120,
          currency: "USD",
          status: "confirmed",
          created_at: "2026-01-01T00:00:00Z",
          details: { kind: "flight", flight_id: "flight-1" },
          trip_id: "trip-1",
          confirmation_code: "ABC123",
          summary: "Flight",
        }),
      ),
    );

    const queryClient = freshClient();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useBookFlight(), {
      wrapper: wrapper(queryClient),
    });

    await result.current.mutateAsync({ ...FLIGHT_BODY, trip_id: "trip-1" });

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["bookings"] });
      expect(invalidateSpy).toHaveBeenCalledWith({
        queryKey: ["budget", "trip-1"],
      });
    });
  });

  it("useBookHotel invalidates the bookings list but not budget when no trip is attached", async () => {
    server.use(
      http.post("*/hotels/book", () =>
        HttpResponse.json({
          id: "booking-2",
          type: "hotel",
          reference_id: "hotel-1",
          customer_name: "Nguyen Van A",
          customer_email: "nguyen.a@example.com",
          total_price: 200,
          currency: "USD",
          status: "confirmed",
          created_at: "2026-01-01T00:00:00Z",
          details: { kind: "hotel", hotel_id: "hotel-1" },
          trip_id: null,
          confirmation_code: "XYZ789",
          summary: "Hotel",
        }),
      ),
    );

    const queryClient = freshClient();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useBookHotel(), {
      wrapper: wrapper(queryClient),
    });

    await result.current.mutateAsync(HOTEL_BODY);

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["bookings"] });
    });
    expect(invalidateSpy).not.toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: expect.arrayContaining(["budget"]) }),
    );
  });
});
