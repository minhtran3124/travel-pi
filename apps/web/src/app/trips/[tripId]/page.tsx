"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { BudgetTab } from "@/components/trips/budget/BudgetTab";
import { ExpensesTab } from "@/components/trips/expenses/ExpensesTab";
import { ItineraryTab } from "@/components/trips/itinerary/ItineraryTab";
import { ShortlistTab } from "@/components/trips/shortlist/ShortlistTab";
import { TripHeader, TripHeaderSkeleton } from "@/components/trips/TripHeader";
import { Tabs, type Tab } from "@/components/ui/Tabs";
import { useTrip } from "@/lib/query/trips";

const TABS: Tab[] = [
  { id: "itinerary", label: "Itinerary" },
  { id: "budget", label: "Budget" },
  { id: "expenses", label: "Expenses" },
  { id: "shortlist", label: "Shortlist" },
];

export default function TripDetailPage() {
  const params = useParams<{ tripId: string }>();
  const tripId = params.tripId;
  const [activeTab, setActiveTab] = useState("itinerary");
  const { data: trip, isPending, isError } = useTrip(tripId);

  if (isPending) {
    return <TripHeaderSkeleton />;
  }

  if (isError || !trip) {
    return (
      <div className="flex flex-col items-start gap-md rounded-lg border border-line bg-panel px-xl py-xl shadow-card">
        <h1 className="text-lg font-extrabold text-ink">
          We couldn&apos;t load this trip
        </h1>
        <p className="max-w-[48ch] text-sm text-muted">
          The trip may have been removed, or the connection dropped. Head back
          and pick another, or try again in a moment.
        </p>
        <Link
          href="/trips"
          className="inline-flex h-[34px] items-center rounded-sm bg-ink px-[18px] text-sm font-bold text-white transition hover:bg-[#2e2e2e] active:translate-y-px"
        >
          Back to all trips
        </Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-lg">
      <TripHeader trip={trip} />
      <Tabs tabs={TABS} active={activeTab} onChange={setActiveTab} />
      <div>
        {activeTab === "itinerary" ? <ItineraryTab tripId={tripId} /> : null}
        {activeTab === "budget" ? <BudgetTab tripId={tripId} /> : null}
        {activeTab === "expenses" ? <ExpensesTab tripId={tripId} /> : null}
        {activeTab === "shortlist" ? <ShortlistTab tripId={tripId} /> : null}
      </div>
    </div>
  );
}
