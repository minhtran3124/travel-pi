"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { NewTripModal } from "@/components/trips/NewTripModal";
import { TripCard } from "@/components/trips/TripCard";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
import { useTrips } from "@/lib/query/trips";

export default function TripsPage() {
  const router = useRouter();
  const [modalOpen, setModalOpen] = useState(false);
  const { data, isPending, isError } = useTrips();

  const trips = data?.results ?? [];

  return (
    <div className="flex flex-col gap-lg">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-extrabold text-ink">Trips</h1>
        <Button onClick={() => setModalOpen(true)}>New trip</Button>
      </div>

      {isPending ? (
        <div className="flex justify-center py-xl">
          <Spinner label="Loading trips" />
        </div>
      ) : isError ? (
        <p className="text-sm font-bold text-status-cancelled">
          Could not load trips. Please try again.
        </p>
      ) : trips.length === 0 ? (
        <EmptyState
          icon="🧳"
          title="No trips yet"
          hint="Plan your first trip to start building an itinerary."
          action={<Button onClick={() => setModalOpen(true)}>New trip</Button>}
        />
      ) : (
        <div className="grid grid-cols-1 gap-md sm:grid-cols-2 lg:grid-cols-3">
          {trips.map((trip) => (
            <TripCard key={trip.id} trip={trip} />
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
