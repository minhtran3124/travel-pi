import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { client } from "@/lib/api/client";
import { qk } from "@/lib/api/keys";
import type { components } from "@/lib/api/schema";

export type Booking = components["schemas"]["Booking"];
export type BookingListResponse = components["schemas"]["BookingListResponse"];
export type FlightBookingDetails =
  components["schemas"]["FlightBookingDetails"];
export type HotelBookingDetails = components["schemas"]["HotelBookingDetails"];

// Per-booking query key. keys.ts has no per-booking factory, so use the
// documented ["booking", id] tuple (Task 2.2 context).
const bookingKey = (id: string) => ["booking", id] as const;

/**
 * GET /bookings — the full bookings ledger. Phase 1 does all filtering/sorting
 * client-side, so no server query params are sent (see design.md §5).
 */
export function useBookings() {
  return useQuery({
    queryKey: qk.bookings(),
    queryFn: async () => {
      const { data, error } = await client.GET("/bookings");
      if (error) throw error;
      return data;
    },
  });
}

/** GET /bookings/{id} — accepts a UUID or a 6-char confirmation code. */
export function useBooking(id: string | null) {
  return useQuery({
    queryKey: bookingKey(id ?? ""),
    enabled: id !== null,
    queryFn: async () => {
      const { data, error } = await client.GET("/bookings/{booking_id}", {
        params: { path: { booking_id: id as string } },
      });
      if (error) throw error;
      return data;
    },
  });
}

/**
 * POST /bookings/{id}/cancel — no body, returns the cancelled Booking (idempotent).
 * Invalidates both the bookings list and the individual booking so the UI refetches.
 */
export function useCancelBooking() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      const { data, error } = await client.POST(
        "/bookings/{booking_id}/cancel",
        { params: { path: { booking_id: id } } },
      );
      if (error) throw error;
      return data;
    },
    onSuccess: (booking) => {
      queryClient.invalidateQueries({ queryKey: qk.bookings() });
      if (booking) {
        queryClient.invalidateQueries({ queryKey: bookingKey(booking.id) });
      }
    },
  });
}
