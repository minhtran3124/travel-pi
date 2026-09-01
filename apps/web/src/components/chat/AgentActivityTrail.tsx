"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { cn } from "@/lib/cn";
import type { ActivityStep } from "./useAgentStream";

/**
 * Wire tool name → activity family label key (resolved against `Chat.activity.*`).
 * Keeps the raw tool name out of the UI: the trail only ever shows the human
 * family label. Anything unmapped falls back to the generic `working` label.
 */
const TOOL_FAMILY: Record<string, string> = {
  // hotels
  search_hotels: "hotels",
  browse_hotels: "hotels",
  book_hotel: "hotels",
  cancel_hotel: "hotels",
  // flights
  search_flights: "flights",
  book_flight: "flights",
  cancel_flight: "flights",
  // weather / climate
  get_weather: "weather",
  get_climate: "weather",
  // air quality
  get_air_quality: "airQuality",
  // route
  get_route: "route",
  get_city_route: "route",
  // places
  search_places: "places",
  nearby_places: "places",
  resolve_place: "places",
  parse_nl_query: "places",
  list_place_categories: "places",
  add_place_to_trip: "places",
  // budget / expenses
  get_trip_budget: "budget",
  add_expense: "budget",
  list_expenses: "budget",
  expense_summary: "budget",
  // itinerary / journal / trip / tips
  create_trip: "journal",
  get_trip_summary: "journal",
  list_trip_places: "journal",
  add_itinerary_item: "journal",
  get_local_tips: "journal",
  get_packing: "journal",
};

function familyKey(tool: string): string {
  return TOOL_FAMILY[tool] ?? "working";
}

/** Per-status dot color; the running dot pulses only when motion is allowed. */
const STATUS_DOT: Record<ActivityStep["status"], string> = {
  running: "bg-lime tp-trail-dot",
  ok: "bg-status-confirmed",
  error: "bg-status-cancelled",
};

export interface AgentActivityTrailProps {
  steps: ActivityStep[];
  isStreaming: boolean;
  /** Turn duration in ms, shown in the collapsed summary. Defaults to 0. */
  elapsedMs?: number;
}

/**
 * Fork-4 activity trail. While a turn streams it shows one row per tool step —
 * a state dot + the localized family label (never the raw tool name). Once the
 * turn ends it collapses to a single summary line that expands the rows on
 * click. Presentational only: no hook access, all inputs arrive as props.
 */
export function AgentActivityTrail({
  steps,
  isStreaming,
  elapsedMs,
}: AgentActivityTrailProps) {
  const t = useTranslations("Chat");
  const [expanded, setExpanded] = useState(false);

  if (steps.length === 0) return null;

  const rows = (
    <ul className="flex flex-col gap-1">
      {steps.map((step) => (
        <li
          key={step.id}
          className="flex items-center gap-2 text-xs text-muted"
        >
          <span
            aria-hidden="true"
            className={cn(
              "h-1.5 w-1.5 shrink-0 rounded-pill",
              STATUS_DOT[step.status],
            )}
          />
          <span>{t(`activity.${familyKey(step.tool)}`)}</span>
        </li>
      ))}
    </ul>
  );

  if (isStreaming) {
    return (
      <div aria-live="polite" className="px-lg py-sm">
        {rows}
      </div>
    );
  }

  const seconds =
    elapsedMs != null ? Math.max(0, Math.round(elapsedMs / 1000)) : 0;

  return (
    <div aria-live="polite" className="px-lg py-sm">
      <button
        type="button"
        aria-expanded={expanded}
        onClick={() => setExpanded((v) => !v)}
        className="text-xs font-medium text-muted transition-colors duration-150 hover:text-ink"
      >
        {t("activity.summary", { count: steps.length, seconds })}
      </button>
      {expanded && <div className="mt-1">{rows}</div>}
    </div>
  );
}
