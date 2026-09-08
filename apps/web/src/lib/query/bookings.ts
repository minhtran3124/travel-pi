import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { client, unwrap } from "@/lib/api/client";
import { qk } from "@/lib/api/keys";
import type { components } from "@/lib/api/schema";

export type Booking = components["schemas"]["Booking"];
export type BookingListResponse = components["schemas"]["BookingListResponse"];
export type FlightBookingDetails =
  components["schemas"]["FlightBookingDetails"];
export type HotelBookingDetails = components["schemas"]["HotelBookingDetails"];

export type BookingFilters = {
  trip_id?: string;
  limit?: number;
};

/**
 * GET /bookings — the full bookings ledger. Phase 1 does all filtering/sorting
 * client-side, so no server query params are sent (see design.md §5), except
 * `trip_id` — used to scope the list to one trip's bookings (e.g. the trip
 * Bookings tab), which the server filters directly.
 */
export function useBookings(filters?: BookingFilters) {
  return useQuery({
    queryKey: filters ? qk.bookings(filters) : qk.bookings(),
    queryFn: () =>
      unwrap(client.GET("/bookings", { params: { query: filters } })),
  });
}

/** GET /bookings/{id} — accepts a UUID or a 6-char confirmation code. */
export function useBooking(id: string | null) {
  return useQuery({
    queryKey: qk.booking(id ?? ""),
    enabled: id !== null,
    queryFn: () =>
      unwrap(
        client.GET("/bookings/{booking_id}", {
          params: { path: { booking_id: id as string } },
        }),
      ),
  });
}

/**
 * POST /bookings/{id}/cancel — no body, returns the cancelled Booking (idempotent).
 * Invalidates both the bookings list and the individual booking so the UI refetches.
 */
export function useCancelBooking() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(
        client.POST("/bookings/{booking_id}/cancel", {
          params: { path: { booking_id: id } },
        }),
      ),
    onSuccess: (booking) => {
      queryClient.invalidateQueries({ queryKey: qk.bookings() });
      if (booking) {
        queryClient.invalidateQueries({ queryKey: qk.booking(booking.id) });
      }
    },
  });
}
