import { Pill } from "@/components/ui/Pill";
import type { TripDetail } from "@/lib/query/trips";

function money(value: number): string {
  return value.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });
}

function dateRange(start?: string | null, end?: string | null): string | null {
  if (start && end) return `${start} → ${end}`;
  if (start) return `from ${start}`;
  if (end) return `until ${end}`;
  return null;
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-xs">
      <span className="text-[0.68rem] font-bold uppercase tracking-[0.08em] text-muted">
        {label}
      </span>
      <span className="text-[1.1rem] font-extrabold text-ink">{value}</span>
    </div>
  );
}

export function TripHeader({ trip }: { trip: TripDetail }) {
  const range = dateRange(trip.start_date, trip.end_date);
  const gaps = trip.gaps ?? [];
  return (
    <header className="flex flex-col gap-md border-b border-line pb-lg">
      <div className="flex flex-col gap-xs">
        <h1 className="text-2xl font-extrabold text-ink">{trip.title}</h1>
        <div className="flex flex-wrap items-center gap-md text-sm text-muted">
          {trip.city ? (
            <span className="font-bold text-muted">{trip.city}</span>
          ) : null}
          {range ? <span>{range}</span> : null}
          <span>
            {trip.travelers} {trip.travelers === 1 ? "traveler" : "travelers"}
          </span>
        </div>
      </div>

      <div className="flex flex-wrap gap-xl">
        <Stat label="Total spent" value={money(trip.total_spent)} />
        <Stat
          label="Remaining budget"
          value={
            trip.remaining_budget === null || trip.remaining_budget === undefined
              ? "No cap"
              : money(trip.remaining_budget)
          }
        />
      </div>

      {gaps.length > 0 ? (
        <ul className="flex flex-wrap gap-sm">
          {gaps.map((gap) => (
            <li key={gap}>
              <Pill variant="status" tone="delayed" label={gap} />
            </li>
          ))}
        </ul>
      ) : null}
    </header>
  );
}
