import Link from "next/link";

import { Card } from "@/components/ui/Card";
import type { Trip } from "@/lib/query/trips";

function dateRange(start?: string | null, end?: string | null): string | null {
  if (start && end) return `${start} → ${end}`;
  if (start) return `from ${start}`;
  if (end) return `until ${end}`;
  return null;
}

export function TripCard({ trip }: { trip: Trip }) {
  const range = dateRange(trip.start_date, trip.end_date);
  return (
    <Link href={`/trips/${trip.id}`} className="block">
      <Card className="flex h-full flex-col gap-sm">
        <h3 className="text-[1.05rem] font-extrabold text-ink">{trip.title}</h3>
        {trip.city ? (
          <p className="text-sm font-bold text-coral-soft">{trip.city}</p>
        ) : null}
        <div className="mt-auto flex flex-col gap-xs pt-sm text-sm text-muted">
          {range ? <span>{range}</span> : null}
          <span>
            {trip.travelers} {trip.travelers === 1 ? "traveler" : "travelers"}
          </span>
        </div>
      </Card>
    </Link>
  );
}
