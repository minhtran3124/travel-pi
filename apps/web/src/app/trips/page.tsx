"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { NewTripModal } from "@/components/trips/NewTripModal";
import { TripCard, TripCardSkeleton } from "@/components/trips/TripCard";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { useTrips, type Trip } from "@/lib/query/trips";

/** A "well-traveled friend" momentum line for the welcome strip. */
function momentum(trips: Trip[]): string {
  if (trips.length === 0) {
    return "Plan your first trip and start mapping it out — I'll help.";
  }
  const today = new Date().toISOString().slice(0, 10);

  const now = trips.find(
    (t) => t.start_date && t.end_date && t.start_date <= today && today <= t.end_date,
  );
  if (now) return `${now.city || now.title} is happening right now — have a great trip.`;

  const next = trips
    .filter((t) => t.start_date && t.start_date >= today)
    .sort((a, b) => (a.start_date! < b.start_date! ? -1 : 1))[0];
  if (next) {
    const days = Math.round(
      (Date.parse(`${next.start_date}T00:00:00Z`) -
        Date.parse(`${today}T00:00:00Z`)) /
        86_400_000,
    );
    const when =
      days <= 0 ? "today" : days === 1 ? "tomorrow" : days < 14 ? `in ${days} days` : `in ${Math.round(days / 7)} weeks`;
    return `${next.city || next.title} is up next — ${when}.`;
  }

  const n = trips.length;
  return `${n} ${n === 1 ? "trip" : "trips"} in the books. Where to next?`;
}

export default function TripsPage() {
  const router = useRouter();
  const [modalOpen, setModalOpen] = useState(false);
  const { data, isPending, isError, refetch } = useTrips();

  const trips = data?.results ?? [];

  return (
    <div className="flex flex-col gap-xl">
      {/* Welcome strip — a soft travel horizon that warms the page without noise. */}
      <section
        className="relative overflow-hidden rounded-lg border border-line px-xl py-lg"
        style={{
          background:
            "linear-gradient(110deg, #eaf3ff 0%, #f5fbe3 55%, #ffeede 100%)",
        }}
      >
        <svg
          aria-hidden="true"
          viewBox="0 0 200 120"
          preserveAspectRatio="none"
          className="pointer-events-none absolute right-0 top-0 h-full w-1/2 opacity-60"
        >
          <path
            d="M-10 96 Q 90 8 210 36"
            fill="none"
            stroke="#fb7755"
            strokeOpacity="0.45"
            strokeWidth="2"
            strokeLinecap="round"
            strokeDasharray="1 9"
          />
        </svg>
        <div className="relative flex flex-wrap items-end justify-between gap-md">
          <div className="flex flex-col gap-xs">
            <h1 className="text-[1.7rem] font-extrabold leading-tight tracking-tight text-ink">
              Where to next?
            </h1>
            <p className="max-w-[48ch] text-sm font-medium text-ink/70">
              {isPending ? "Loading your trips…" : momentum(trips)}
            </p>
          </div>
          <Button onClick={() => setModalOpen(true)} className="gap-xs">
            <PlusIcon />
            New trip
          </Button>
        </div>
      </section>

      {isPending ? (
        <>
          <span role="status" className="sr-only">
            Loading your trips
          </span>
          <div className="grid grid-cols-1 gap-lg sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <TripCardSkeleton key={i} />
            ))}
          </div>
        </>
      ) : isError ? (
        <EmptyState
          icon="⚠️"
          title="We couldn't load your trips"
          hint="Check your connection and try again."
          action={<Button onClick={() => refetch()}>Try again</Button>}
        />
      ) : trips.length === 0 ? (
        <EmptyState
          icon="🧳"
          title="Your next adventure starts here"
          hint="Create a trip and we'll help you build the itinerary, find places, and track the budget."
          action={
            <Button onClick={() => setModalOpen(true)} className="gap-xs">
              <PlusIcon />
              Plan a trip
            </Button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-lg sm:grid-cols-2 lg:grid-cols-3">
          {trips.map((trip, i) => (
            <div
              key={trip.id}
              className="tp-deal"
              style={{ animationDelay: `${Math.min(i, 8) * 70}ms` }}
            >
              <TripCard trip={trip} />
            </div>
          ))}
        </div>
      )}

      <NewTripModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onCreated={(id) => router.push(`/trips/${id}`)}
      />
    </div>
  );
}

function PlusIcon() {
  return (
    <svg
      width={15}
      height={15}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.5}
      strokeLinecap="round"
      aria-hidden="true"
    >
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}
