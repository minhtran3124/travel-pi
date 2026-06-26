// Shared destination-cover system for the Trips surfaces.
//
// We have no real photos (mock backend), so every trip gets a deterministic
// "horizon" seeded by its city/title — warmth and variety without imagery.
// Both the Trips grid card and the trip-detail hero render from here so the
// click-through from a postcard into its trip stays visually continuous and
// the seed algorithm has a single source of truth.

import type { useFormatter, useTranslations } from "next-intl";

import { cn } from "@/lib/cn";

const DAY = 86_400_000;

// Locale-aware formatter + the `Trips` translator, threaded in from the calling
// client component (these helpers run outside React, so they can't call hooks).
type Formatter = ReturnType<typeof useFormatter>;
type Translator = ReturnType<typeof useTranslations>;
// next-intl's own date-options type (narrower `timeZoneName` than Intl's).
type DateOpts = NonNullable<Parameters<Formatter["dateTime"]>[2]>;

// API dates are timezone-less ISO (YYYY-MM-DD); pin formatting to UTC so the
// calendar day never shifts backwards in negative-offset timezones.
function fmt(format: Formatter, iso: string, opts: DateOpts): string {
  return format.dateTime(new Date(`${iso}T00:00:00Z`), {
    ...opts,
    timeZone: "UTC",
  });
}

export function dateRange(
  format: Formatter,
  t: Translator,
  start?: string | null,
  end?: string | null,
): string | null {
  const full: DateOpts = {
    month: "short",
    day: "numeric",
    year: "numeric",
  };
  if (start && end) {
    const sameYear = start.slice(0, 4) === end.slice(0, 4);
    const sameMonth = sameYear && start.slice(0, 7) === end.slice(0, 7);
    const sep = t("dateRange.separator");
    if (sameMonth) {
      // Jun 26 – 30, 2026
      return `${fmt(format, start, { month: "short", day: "numeric" })} ${sep} ${fmt(format, end, { day: "numeric" })}, ${start.slice(0, 4)}`;
    }
    if (sameYear) {
      // Jun 26 – Jul 2, 2026
      return `${fmt(format, start, { month: "short", day: "numeric" })} ${sep} ${fmt(format, end, { month: "short", day: "numeric" })}, ${start.slice(0, 4)}`;
    }
    // Dec 30, 2025 – Jan 2, 2026
    return `${fmt(format, start, full)} ${sep} ${fmt(format, end, full)}`;
  }
  if (start) return t("dateRange.from", { date: fmt(format, start, full) });
  if (end) return t("dateRange.until", { date: fmt(format, end, full) });
  return null;
}

function utcDay(iso: string): number {
  return Date.UTC(
    Number(iso.slice(0, 4)),
    Number(iso.slice(5, 7)) - 1,
    Number(iso.slice(8, 10)),
  );
}

/** Inclusive day count for a trip, or null when either endpoint is missing. */
export function tripDays(
  start?: string | null,
  end?: string | null,
): number | null {
  if (!start || !end) return null;
  return Math.round((utcDay(end) - utcDay(start)) / DAY) + 1;
}

// --- Trip lifecycle: where the trip sits relative to today, as a human label.

type Phase = "now" | "upcoming" | "past";
export interface TripStatus {
  phase: Phase;
  label: string;
}

function todayUTC(): number {
  const n = new Date();
  return Date.UTC(n.getFullYear(), n.getMonth(), n.getDate());
}

function futureLabel(t: Translator, d: number): string {
  if (d <= 1) return t("status.tomorrow");
  if (d < 14) return t("status.inDays", { count: d });
  if (d < 60) return t("status.inWeeks", { count: Math.round(d / 7) });
  return t("status.inMonths", { count: Math.round(d / 30) });
}

function pastLabel(t: Translator, d: number): string {
  if (d <= 1) return t("status.yesterday");
  if (d < 14) return t("status.daysAgo", { count: d });
  if (d < 60) return t("status.weeksAgo", { count: Math.round(d / 7) });
  return t("status.monthsAgo", { count: Math.round(d / 30) });
}

export function tripStatus(
  t: Translator,
  start?: string | null,
  end?: string | null,
): TripStatus | null {
  if (!start && !end) return null;
  const s = utcDay((start ?? end) as string);
  const e = utcDay((end ?? start) as string);
  const today = todayUTC();
  if (today < s) return { phase: "upcoming", label: futureLabel(t, (s - today) / DAY) };
  if (today > e) return { phase: "past", label: pastLabel(t, (today - e) / DAY) };
  return { phase: "now", label: t("status.happeningNow") };
}

/** One or two initials from the city (preferred) or trip name, for the tile. */
export function monogram(source: string): string {
  const words = source.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "✈";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

// --- Destination cover: a soft postcard gradient + a dotted flight path.

export interface Cover {
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

/** Resolve the cover for a trip, honouring the lime "happening now" override. */
export function coverForTrip(seed: string, now: boolean): Cover {
  return now ? COVER_NOW : coverFor(seed);
}

/** The postcard cover band: gradient wash, a dotted great-circle arc, a plane. */
export function CoverArt({
  cover,
  now,
  className,
}: {
  cover: Cover;
  now: boolean;
  className?: string;
}) {
  return (
    <div
      aria-hidden="true"
      className={cn("relative overflow-hidden", className ?? "h-[108px]")}
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

export function StatusChip({ status }: { status: TripStatus }) {
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

// --- Shared line icons (14px, currentColor stroke).

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

export function PinIcon({ className }: { className?: string }) {
  return (
    <svg {...iconProps} className={cn(iconProps.className, className)}>
      <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z" />
      <circle cx="12" cy="10" r="3" />
    </svg>
  );
}

export function CalendarIcon() {
  return (
    <svg {...iconProps}>
      <rect x="3" y="4" width="18" height="18" rx="2" />
      <path d="M16 2v4M8 2v4M3 10h18" />
    </svg>
  );
}

export function UsersIcon() {
  return (
    <svg {...iconProps}>
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  );
}
