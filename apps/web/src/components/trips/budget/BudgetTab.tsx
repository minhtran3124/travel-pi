"use client";

import { Spinner } from "@/components/ui/Spinner";

// STUB — the budget caps vs spend UI is filled in Task 2.5.
export function BudgetTab({ tripId }: { tripId: string }) {
  void tripId;
  return (
    <section className="flex flex-col gap-md">
      <h2 className="text-lg font-extrabold text-ink">Budget</h2>
      <div className="flex items-center gap-sm text-sm text-muted">
        <Spinner label="Budget coming soon" />
        <span>Coming soon</span>
      </div>
    </section>
  );
}
