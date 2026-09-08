"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { TripDetailPageSkeleton } from "@/components/skeletons/TripDetailPageSkeleton";
import { BudgetTab } from "@/components/trips/budget/BudgetTab";
import { ExpensesTab } from "@/components/trips/expenses/ExpensesTab";
import { ItineraryTab } from "@/components/trips/itinerary/ItineraryTab";
import { ShortlistTab } from "@/components/trips/shortlist/ShortlistTab";
import { TripHeader } from "@/components/trips/TripHeader";
import { Tabs, type Tab } from "@/components/ui/Tabs";
import { useTrip } from "@/lib/query/trips";

export default function TripDetailPage() {
  const t = useTranslations("TripDetail");
  const params = useParams<{ tripId: string }>();
  const tripId = params.tripId;
  const [activeTab, setActiveTab] = useState("itinerary");
  const { data: trip, isPending, isError } = useTrip(tripId);

  const tabs: Tab[] = [
    { id: "itinerary", label: t("tabs.itinerary") },
    { id: "budget", label: t("tabs.budget") },
    { id: "expenses", label: t("tabs.expenses") },
    { id: "shortlist", label: t("tabs.shortlist") },
  ];

  return (
    <>
      <span role="status" className="sr-only">
        {isPending ? t("loadingLabel") : ""}
      </span>
      {isPending ? (
        <TripDetailPageSkeleton />
      ) : isError || !trip ? (
        <div className="flex flex-col items-start gap-md rounded-lg border border-line bg-panel px-xl py-xl shadow-card">
          <h1 className="text-lg font-extrabold text-ink">{t("errorTitle")}</h1>
          <p className="max-w-[48ch] text-sm text-muted">{t("errorHint")}</p>
          <Link
            href="/trips"
            className="inline-flex h-[34px] items-center rounded-sm bg-ink px-[18px] text-sm font-bold text-on-ink transition hover:bg-ink-hover active:translate-y-px"
          >
            {t("backToAllTrips")}
          </Link>
        </div>
      ) : (
        <div className="flex flex-col gap-lg">
          <TripHeader trip={trip} />
          <Tabs tabs={tabs} active={activeTab} onChange={setActiveTab} />
          <div>
            {activeTab === "itinerary" ? <ItineraryTab tripId={tripId} /> : null}
            {activeTab === "budget" ? <BudgetTab tripId={tripId} /> : null}
            {activeTab === "expenses" ? <ExpensesTab tripId={tripId} /> : null}
            {activeTab === "shortlist" ? <ShortlistTab tripId={tripId} /> : null}
          </div>
        </div>
      )}
    </>
  );
}
