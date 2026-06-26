"use client";

import { Spinner } from "@/components/ui/Spinner";

// STUB — the itinerary day-plan UI is filled in Task 2.4.
export function ItineraryTab({ tripId }: { tripId: string }) {
  void tripId;
  return (
    <section className="flex flex-col gap-md">
      <h2 className="text-lg font-extrabold text-ink">Itinerary</h2>
      <div className="flex items-center gap-sm text-sm text-muted">
        <Spinner label="Itinerary coming soon" />
        <span>Coming soon</span>
      </div>
    </section>
  );
}
