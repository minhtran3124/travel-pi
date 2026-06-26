import type { TripDetail } from "@/lib/query/trips";

const DAY = 86_400_000;

function money(value: number): string {
  return value.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });
}

// Dates are timezone-less ISO (YYYY-MM-DD); pin to UTC so the day never shifts.
function fmt(iso: string, opts: Intl.DateTimeFormatOptions): string {
  return new Intl.DateTimeFormat("en-US", { ...opts, timeZone: "UTC" }).format(
    new Date(`${iso}T00:00:00Z`),
  );
}

function dateRange(start?: string | null, end?: string | null): string | null {
  const full: Intl.DateTimeFormatOptions = {
    month: "short",
    day: "numeric",
    year: "numeric",
  };
  if (start && end) {
    const sameYear = start.slice(0, 4) === end.slice(0, 4);
    const sameMonth = sameYear && start.slice(0, 7) === end.slice(0, 7);
    if (sameMonth) {
      return `${fmt(start, { month: "short", day: "numeric" })} – ${fmt(end, { day: "numeric" })}, ${start.slice(0, 4)}`;
    }
    if (sameYear) {
      return `${fmt(start, { month: "short", day: "numeric" })} – ${fmt(end, { month: "short", day: "numeric" })}, ${start.slice(0, 4)}`;
    }
    return `${fmt(start, full)} – ${fmt(end, full)}`;
  }
  if (start) return `From ${fmt(start, full)}`;
  if (end) return `Until ${fmt(end, full)}`;
  return null;
}

function utcDay(iso: string): number {
  return Date.UTC(
    Number(iso.slice(0, 4)),
    Number(iso.slice(5, 7)) - 1,
    Number(iso.slice(8, 10)),
  );
}

function tripDays(start?: string | null, end?: string | null): number | null {
  if (!start || !end) return null;
  return Math.round((utcDay(end) - utcDay(start)) / DAY) + 1;
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

/**
 * The backend `gaps` list is one verbose sentence per unplanned day
 * ("Day 1 has no planned items."). Rendering all of them is a wall of noise —
 * and framing not-yet-planned days as warnings is the wrong tone. Collapse into
 * a calm nudge: a single line when the whole trip is open, compact day chips
 * when only some days are.
 */
function GapsSummary({
  gaps,
  totalDays,
}: {
  gaps: string[];
  totalDays: number | null;
}) {
  const dayNums: number[] = [];
  const other: string[] = [];
  for (const gap of gaps) {
    const match = gap.match(/day\s+(\d+)/i);
    if (match) dayNums.push(Number(match[1]));
    else other.push(gap);
  }
  const days = [...new Set(dayNums)].sort((a, b) => a - b);
  const allOpen =
    totalDays !== null && other.length === 0 && days.length >= totalDays;

  return (
    <div className="flex flex-col gap-sm rounded-md bg-panel-raised px-md py-md">
      <span className="text-[0.68rem] font-bold uppercase tracking-[0.08em] text-muted">
        Still to plan
      </span>

      {allOpen ? (
        <p className="text-sm text-muted">
          Blank canvas — all {totalDays} days are open. Add your first stop in
          the <span className="font-bold text-ink">Itinerary</span> tab to start
          mapping it out.
        </p>
      ) : (
        <div className="flex flex-col gap-sm">
          {days.length > 0 ? (
            <>
              <p className="text-sm text-muted">
                <span className="font-bold text-ink">{days.length}</span>{" "}
                {days.length === 1 ? "day still needs" : "days still need"} a plan
              </p>
              <ul className="flex flex-wrap gap-xs">
                {days.map((d) => (
                  <li key={d}>
                    <span className="inline-flex rounded-pill bg-panel px-sm py-px text-xs font-bold text-muted ring-1 ring-line">
                      Day {d}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          ) : null}
          {other.length > 0 ? (
            <ul className="flex flex-col gap-xs text-sm text-muted">
              {other.map((o) => (
                <li key={o}>{o}</li>
              ))}
            </ul>
          ) : null}
        </div>
      )}
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
        <GapsSummary gaps={gaps} totalDays={tripDays(trip.start_date, trip.end_date)} />
      ) : null}
    </header>
  );
}
