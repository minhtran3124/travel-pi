"use client";

import { Spinner } from "@/components/ui/Spinner";

// STUB — the shortlisted-places UI is filled in Task 2.6.
export function ShortlistTab({ tripId }: { tripId: string }) {
  void tripId;
  return (
    <section className="flex flex-col gap-md">
      <h2 className="text-lg font-extrabold text-ink">Shortlist</h2>
      <div className="flex items-center gap-sm text-sm text-muted">
        <Spinner label="Shortlist coming soon" />
        <span>Coming soon</span>
      </div>
    </section>
  );
}
