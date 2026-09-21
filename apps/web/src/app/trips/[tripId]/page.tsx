"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useState } from "react";

import { BookingsTab } from "@/components/trips/bookings/BookingsTab";
import { BudgetTab } from "@/components/trips/budget/BudgetTab";
import { ExpensesTab } from "@/components/trips/expenses/ExpensesTab";
import { ItineraryTab } from "@/components/trips/itinerary/ItineraryTab";
import { MapTab } from "@/components/trips/map/MapTab";
import { ResearchTab } from "@/components/trips/research/ResearchTab";
import { ShortlistTab } from "@/components/trips/shortlist/ShortlistTab";
import { TodayTab } from "@/components/trips/today/TodayTab";
import { TripHeader, TripHeaderSkeleton } from "@/components/trips/TripHeader";
import { Tabs, type Tab } from "@/components/ui/Tabs";
import { researchEnabled } from "@/lib/features";
import { useTrip } from "@/lib/query/trips";

export default function TripDetailPage() {
  const t = useTranslations("TripDetail");
  const tToday = useTranslations("Today");
  const params = useParams<{ tripId: string }>();
  const tripId = params.tripId;
  // `?tab=` opens a tab directly (the chat's research-done card links here).
  const tabParam = useSearchParams().get("tab");
  const [tabState, setActiveTab] = useState(tabParam ?? "itinerary");
  const [seenTabParam, setSeenTabParam] = useState(tabParam);
  if (tabParam !== seenTabParam) {
    setSeenTabParam(tabParam);
    if (tabParam) setActiveTab(tabParam);
  }
  const { data: trip, isPending, isError } = useTrip(tripId);

  const tabs: Tab[] = [
    { id: "today", label: tToday("tab") },
    { id: "itinerary", label: t("tabs.itinerary") },
    { id: "budget", label: t("tabs.budget") },
    { id: "expenses", label: t("tabs.expenses") },
    { id: "bookings", label: t("tabs.bookings") },
    { id: "shortlist", label: t("tabs.shortlist") },
    { id: "map", label: t("tabs.map") },
    ...(researchEnabled()
      ? [{ id: "research", label: t("research.tabLabel") }]
      : []),
  ];
  // An unknown or disabled `?tab=` falls back rather than rendering no tab.
  const activeTab = tabs.some((tab) => tab.id === tabState)
    ? tabState
    : "itinerary";

  if (isPending) {
    return <TripHeaderSkeleton />;
  }

  if (isError || !trip) {
    return (
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
    );
  }

  return (
    <div className="flex flex-col gap-lg">
      <TripHeader trip={trip} />
      <Tabs tabs={tabs} active={activeTab} onChange={setActiveTab} />
      <div>
        {activeTab === "today" ? <TodayTab tripId={tripId} /> : null}
        {activeTab === "itinerary" ? <ItineraryTab tripId={tripId} /> : null}
        {activeTab === "budget" ? <BudgetTab tripId={tripId} /> : null}
        {activeTab === "expenses" ? <ExpensesTab tripId={tripId} /> : null}
        {activeTab === "bookings" ? <BookingsTab tripId={tripId} /> : null}
        {activeTab === "shortlist" ? <ShortlistTab tripId={tripId} /> : null}
        {activeTab === "map" ? <MapTab tripId={tripId} /> : null}
        {activeTab === "research" ? <ResearchTab tripId={tripId} /> : null}
      </div>
    </div>
  );
}
