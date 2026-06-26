import Link from "next/link";

import { cn } from "@/lib/cn";
import type { Trip } from "@/lib/query/trips";

// API dates are timezone-less ISO (YYYY-MM-DD); pin formatting to UTC so the
// calendar day never shifts backwards in negative-offset timezones.
function fmt(iso: string, opts: Intl.DateTimeFormatOptions): string {
  return new Intl.DateTimeFormat("en-US", { ...opts, timeZone: "UTC" }).format(
    new Date(`${iso}T00:00:00Z`),
  );
}

function dateRange(start?: string | null, end?: string | null): string | null {
  if (start && end) {
    const sameYear = start.slice(0, 4) === end.slice(0, 4);
    const sameMonth = sameYear && start.slice(0, 7) === end.slice(0, 7);
    if (sameMonth) {
      // Jun 26 – 30, 2026
      return `${fmt(start, { month: "short", day: "numeric" })} – ${fmt(end, { day: "numeric" })}, ${start.slice(0, 4)}`;
    }
    if (sameYear) {
      // Jun 26 – Jul 2, 2026
      return `${fmt(start, { month: "short", day: "numeric" })} – ${fmt(end, { month: "short", day: "numeric" })}, ${start.slice(0, 4)}`;
    }
    // Dec 30, 2025 – Jan 2, 2026
    const full: Intl.DateTimeFormatOptions = {
      month: "short",
      day: "numeric",
      year: "numeric",
    };
    return `${fmt(start, full)} – ${fmt(end, full)}`;
  }
  const full: Intl.DateTimeFormatOptions = {
    month: "short",
    day: "numeric",
    year: "numeric",
  };
  if (start) return `From ${fmt(start, full)}`;
  if (end) return `Until ${fmt(end, full)}`;
  return null;
}

// --- Trip lifecycle: where the trip sits relative to today, as a human label.

const DAY = 86_400_000;
type Phase = "now" | "upcoming" | "past";
interface TripStatus {
  phase: Phase;
  label: string;
}

function utcDay(iso: string): number {
  return Date.UTC(
    Number(iso.slice(0, 4)),
    Number(iso.slice(5, 7)) - 1,
    Number(iso.slice(8, 10)),
  );
}

function todayUTC(): number {
  const n = new Date();
  return Date.UTC(n.getFullYear(), n.getMonth(), n.getDate());
}

function futureLabel(d: number): string {
  if (d <= 1) return "Tomorrow";
  if (d < 14) return `in ${d} days`;
  if (d < 60) return `in ${Math.round(d / 7)} weeks`;
  return `in ${Math.round(d / 30)} months`;
}

function pastLabel(d: number): string {
  if (d <= 1) return "Yesterday";
  if (d < 14) return `${d} days ago`;
  if (d < 60) return `${Math.round(d / 7)} weeks ago`;
  return `${Math.round(d / 30)} months ago`;
}

function tripStatus(
  start?: string | null,
  end?: string | null,
): TripStatus | null {
  if (!start && !end) return null;
  const s = utcDay((start ?? end) as string);
  const e = utcDay((end ?? start) as string);
  const today = todayUTC();
  if (today < s) return { phase: "upcoming", label: futureLabel((s - today) / DAY) };
  if (today > e) return { phase: "past", label: pastLabel((today - e) / DAY) };
  return { phase: "now", label: "Happening now" };
}

/** One or two initials from the city (preferred) or trip name, for the anchor tile. */
function monogram(source: string): string {
  const words = source.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "✈";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

// --- Destination cover: a soft postcard gradient + a dotted flight path.
// We have no real photos (mock backend), so each trip gets a deterministic
// "horizon" seeded by its city/title — warmth and variety without imagery.

interface Cover {
  from: string;
  to: string;
  /** Arc + plane stroke; a mid-tone of the cover hue, kept low-opacity. */
  trail: string;
}

const COVERS: Cover[] = [
  { from: "#d7e9ff", to: "#eff6ff", trail: "#3b82f6" }, // sky
  { from: "#ffe0d3", to: "#fff2ec", trail: "#fb7755" }, // coral
  { from: "#cdf0e8", to: "#ecfbf7", trail: "#14b8a6" }, // sea
  { from: "#e6def9", to: "#f4efff", trail: "#8b5cf6" }, // dawn
  { from: "#ffdcea", to: "#fff0f6", trail: "#ec4899" }, // rose
  { from: "#ffe7bd", to: "#fff8ea", trail: "#e59411" }, // sunset
];

// "Happening now" trips wear the brand lime so the active signal carries.
const COVER_NOW: Cover = { from: "#e9f7b8", to: "#f6fce0", trail: "#7e9e12" };

function coverFor(seed: string): Cover {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  return COVERS[h % COVERS.length];
}

/** The postcard cover band: gradient wash, a dotted great-circle arc, a plane. */
function CoverArt({ cover, now }: { cover: Cover; now: boolean }) {
  return (
    <div
      aria-hidden="true"
      className="relative h-[108px] overflow-hidden"
      style={{ background: `linear-gradient(135deg, ${cover.from}, ${cover.to})` }}
    >
      <svg
        viewBox="0 0 320 108"
        preserveAspectRatio="none"
        className="absolute inset-0 size-full"
      >
        <path
          d="M22 90 Q 150 6 300 38"
          fill="none"
          stroke={cover.trail}
          strokeOpacity={now ? 0.5 : 0.42}
          strokeWidth="2"
          strokeLinecap="round"
          strokeDasharray="1 8"
        />
        <circle cx="22" cy="90" r="3.5" fill={cover.trail} fillOpacity="0.7" />
        <g
          className="tp-plane"
          transform="translate(296 38)"
          fill={cover.trail}
          fillOpacity="0.85"
        >
          <path
            transform="rotate(28) scale(0.85)"
            d="M2 0 L-9 4 L-6 0 L-9 -4 Z"
          />
        </g>
      </svg>
    </div>
  );
}

function StatusChip({ status }: { status: TripStatus }) {
  if (status.phase === "now") {
    return (
      <span className="inline-flex shrink-0 items-center gap-xs rounded-pill bg-lime px-sm py-px text-xs font-bold text-on-accent shadow-sm">
        <span className="size-1.5 animate-pulse rounded-pill bg-on-accent" />
        {status.label}
      </span>
    );
  }
  // Frosted pill so it stays legible on any cover gradient.
  return (
    <span
      className={cn(
        "shrink-0 rounded-pill bg-white/80 px-sm py-px text-xs font-bold shadow-sm ring-1 ring-black/5 backdrop-blur-sm",
        status.phase === "upcoming" ? "text-ink" : "text-muted",
      )}
    >
      {status.label}
    </span>
  );
}

export function TripCard({ trip }: { trip: Trip }) {
  const range = dateRange(trip.start_date, trip.end_date);
  const status = tripStatus(trip.start_date, trip.end_date);
  const now = status?.phase === "now";
  const cover = now ? COVER_NOW : coverFor(trip.city || trip.title);

  return (
    <Link href={`/trips/${trip.id}`} className="group block">
      <article
        className={cn(
          "relative flex h-full flex-col overflow-hidden rounded-md border border-line bg-panel shadow-card transition duration-200 hover:-translate-y-0.5 hover:border-[#e0e0e0] hover:shadow-lift",
          now && "ring-2 ring-lime",
        )}
      >
        <CoverArt cover={cover} now={now} />

        {status ? (
          <div className="absolute right-md top-md">
            <StatusChip status={status} />
          </div>
        ) : null}

        {/* Monogram straddles the cover seam for depth, avatar-style. */}
        <span
          aria-hidden="true"
          className={cn(
            "absolute left-lg top-[108px] flex size-12 -translate-y-1/2 items-center justify-center rounded-md text-base font-extrabold shadow-card ring-1 ring-black/5",
            now ? "bg-lime text-on-accent" : "bg-panel text-ink",
          )}
        >
          {monogram(trip.city || trip.title)}
        </span>

        <div className="flex flex-1 flex-col gap-xs px-lg pb-lg pt-[34px]">
          <h3 className="line-clamp-2 break-words text-[1.2rem] font-extrabold leading-tight text-ink">
            {trip.title}
          </h3>

          {trip.city ? (
            <p className="flex items-center gap-xs text-sm font-bold text-muted">
              <PinIcon className="text-coral" />
              {trip.city}
            </p>
          ) : null}

          <div className="mt-auto flex flex-wrap items-center gap-x-lg gap-y-xs border-t border-line-soft pt-md text-sm text-muted">
            <span className="flex items-center gap-xs">
              <CalendarIcon />
              {range ?? "No dates yet"}
            </span>
            <span className="flex items-center gap-xs">
              <UsersIcon />
              {trip.travelers} {trip.travelers === 1 ? "traveler" : "travelers"}
            </span>
          </div>
        </div>
      </article>
    </Link>
  );
}

/** Placeholder matching {@link TripCard}'s shape for the list loading state. */
export function TripCardSkeleton() {
  return (
    <div
      aria-hidden="true"
      className="relative h-full animate-pulse overflow-hidden rounded-md border border-line bg-panel shadow-card"
    >
      <div className="h-[108px] bg-panel-raised" />
      <div className="absolute left-lg top-[108px] size-12 -translate-y-1/2 rounded-md bg-line ring-1 ring-black/5" />
      <div className="flex flex-col gap-sm px-lg pb-lg pt-[34px]">
        <div className="h-5 w-3/4 rounded-sm bg-panel-raised" />
        <div className="h-3 w-1/2 rounded-sm bg-panel-raised" />
        <div className="mt-sm flex gap-lg border-t border-line-soft pt-md">
          <div className="h-3 w-2/5 rounded-sm bg-panel-raised" />
          <div className="h-3 w-1/4 rounded-sm bg-panel-raised" />
        </div>
      </div>
    </div>
  );
}

const iconProps = {
  width: 14,
  height: 14,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round",
  strokeLinejoin: "round",
  "aria-hidden": true,
  className: "shrink-0",
} as const;

function PinIcon({ className }: { className?: string }) {
  return (
    <svg {...iconProps} className={cn(iconProps.className, className)}>
      <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z" />
      <circle cx="12" cy="10" r="3" />
    </svg>
  );
}

function CalendarIcon() {
  return (
    <svg {...iconProps}>
      <rect x="3" y="4" width="18" height="18" rx="2" />
      <path d="M16 2v4M8 2v4M3 10h18" />
    </svg>
  );
}

function UsersIcon() {
  return (
    <svg {...iconProps}>
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  );
}
