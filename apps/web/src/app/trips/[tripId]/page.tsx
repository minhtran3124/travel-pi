"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { BudgetTab } from "@/components/trips/budget/BudgetTab";
import { ExpensesTab } from "@/components/trips/expenses/ExpensesTab";
import { ItineraryTab } from "@/components/trips/itinerary/ItineraryTab";
import { ShortlistTab } from "@/components/trips/shortlist/ShortlistTab";
import { TripHeader } from "@/components/trips/TripHeader";
import { Spinner } from "@/components/ui/Spinner";
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
    return (
      <div className="flex justify-center py-xl">
        <Spinner label="Loading trip" />
      </div>
    );
  }

  if (isError || !trip) {
    return (
      <div className="flex flex-col gap-md py-xl">
        <p className="text-sm font-bold text-status-cancelled">
          Could not load this trip.
        </p>
        <Link href="/trips" className="text-sm font-bold text-coral-soft">
          ← Back to trips
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
