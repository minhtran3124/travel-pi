"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef } from "react";

import { client } from "@/lib/api/client";
import { PremiumRequiredError, throwOn403 } from "@/lib/api/errors";
import { qk } from "@/lib/api/keys";
import type { components } from "@/lib/api/schema";

export type Hotel = components["schemas"]["Hotel"];
export type HotelSearchResponse = components["schemas"]["HotelSearchResponse"];
export type HotelBookingRequest = components["schemas"]["HotelBookingRequest"];
export type Booking = components["schemas"]["Booking"];

// Re-exported so call sites can `instanceof`-check without a separate import.
export { PremiumRequiredError };

/**
 * POST /hotels/book. A 403 (tier gate) is surfaced as `PremiumRequiredError`
 * so callers can show an upgrade prompt instead of a generic error.
 *
 * Mints one Idempotency-Key per booking attempt and reuses it across
 * resubmits (a network flake → generic error → user tries again should
 * replay, not double-book, #164). The key resets once the attempt
 * succeeds, or when the caller resets the mutation (e.g. closing the
 * booking dialog) — so the next attempt gets a fresh key.
 *
 * On success, invalidates the bookings list (and the booked trip's budget,
 * if any) so a mounted trip Bookings/Budget view picks up the new booking
 * instead of showing pre-booking numbers — mirrors `useCancelBooking`.
 */
export function useBookHotel() {
  const queryClient = useQueryClient();
  const idempotencyKeyRef = useRef<string | null>(null);
  const mutation = useMutation({
    mutationFn: async (body: HotelBookingRequest) => {
      idempotencyKeyRef.current ??= crypto.randomUUID();
      const { data, error, response } = await client.POST("/hotels/book", {
        body,
        headers: { "Idempotency-Key": idempotencyKeyRef.current },
      });
      if (error) {
        throwOn403(response, error, PremiumRequiredError);
        throw error;
      }
      idempotencyKeyRef.current = null;
      return data;
    },
    onSuccess: (booking) => {
      queryClient.invalidateQueries({ queryKey: qk.bookings() });
      if (booking?.trip_id) {
        queryClient.invalidateQueries({ queryKey: qk.budget(booking.trip_id) });
      }
    },
  });
  return {
    ...mutation,
    reset: () => {
      idempotencyKeyRef.current = null;
      mutation.reset();
    },
  };
}
