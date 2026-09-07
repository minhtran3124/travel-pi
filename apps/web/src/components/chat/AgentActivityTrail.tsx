"use client";

import { useTranslations } from "next-intl";
import { type ReactElement, useState } from "react";

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
  // HITL plan approval — a client-side status step, not a wire tool
  plan_approved: "approved",
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

/** One glyph per tool family — 14px, currentColor, no new color tokens. */
const FAMILY_ICON: Record<string, ReactElement> = {
  approved: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 6 9 17l-5-5" />
    </svg>
  ),
  flights: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 2 11 13" />
      <path d="M22 2 15 22l-4-9-9-4 20-7Z" />
    </svg>
  ),
  hotels: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 7v11a1 1 0 0 0 1 1h16a1 1 0 0 0 1-1v-4a2 2 0 0 0-2-2H3" />
      <circle cx="7" cy="14" r="1.4" />
      <path d="M3 12V6a1 1 0 0 1 1-1h6l3 3h6a1 1 0 0 1 1 1v3" />
    </svg>
  ),
  weather: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17.5 19a4.5 4.5 0 1 0-1.44-8.76A6 6 0 0 0 5 12.5 4 4 0 0 0 6 20.5h11.5Z" />
    </svg>
  ),
  airQuality: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9.6 4.6a2 2 0 1 1 1.4 3.4H2" />
      <path d="M12.6 19.4a2 2 0 1 0 1.4-3.4H2" />
      <path d="M17.4 8a2.5 2.5 0 1 1 1.76 4.28H2" />
    </svg>
  ),
  route: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="6" cy="19" r="2" />
      <circle cx="18" cy="5" r="2" />
      <path d="M8 19h7a4 4 0 0 0 4-4v-1a4 4 0 0 0-4-4H9a4 4 0 0 1-4-4V5" />
    </svg>
  ),
  places: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 21s7-6.6 7-11.5A7 7 0 0 0 5 9.5C5 14.4 12 21 12 21Z" />
      <circle cx="12" cy="9.5" r="2.3" />
    </svg>
  ),
  budget: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2.5" y="6" width="19" height="13" rx="2" />
      <path d="M2.5 10h19" />
      <circle cx="17" cy="14.5" r="1.4" />
    </svg>
  ),
  journal: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 4h13a2 2 0 0 1 2 2v14l-3-2-3 2-3-2-3 2-3-2-3 2V6a2 2 0 0 1 2-2Z" />
      <path d="M8 8h8M8 12h8M8 16h5" />
    </svg>
  ),
  working: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="8" />
      <path d="M12 8v4l2.5 2.5" />
    </svg>
  ),
};

/**
 * One row in the rendered trail: consecutive `ActivityStep`s sharing a family
 * collapse into a single group so a turn that repeats the same tool (e.g. 11
 * itinerary edits) doesn't render 11 identical lines. Group status is the
 * "worst" status among its members (error > running > ok) so an in-progress
 * or failed member is never hidden behind an earlier ok one.
 */
type StepGroup = {
  key: string;
  family: string;
  status: ActivityStep["status"];
  count: number;
};

const STATUS_RANK: Record<ActivityStep["status"], number> = {
  error: 2,
  running: 1,
  ok: 0,
};

function groupSteps(steps: ActivityStep[]): StepGroup[] {
  const groups: StepGroup[] = [];
  for (const step of steps) {
    const family = familyKey(step.tool);
    const last = groups[groups.length - 1];
    if (last && last.family === family) {
      last.count += 1;
      if (STATUS_RANK[step.status] > STATUS_RANK[last.status]) {
        last.status = step.status;
      }
      continue;
    }
    groups.push({
      key: step.id,
      family,
      status: step.status,
      count: 1,
    });
  }
  return groups;
}

export interface AgentActivityTrailProps {
  steps: ActivityStep[];
  isStreaming: boolean;
  /** Turn duration in ms, shown in the collapsed summary. Defaults to 0. */
  elapsedMs?: number;
  /**
   * Re-run the turn after a failed step. There is no backend capability to
   * retry a single tool call in isolation, so this re-runs the whole turn via
   * the same action as the "Regenerate" message action. Omit to hide Retry.
   */
  onRetry?: () => void;
}

/**
 * Activity trail. While a turn streams it shows one row per tool-family group
 * — an icon + the localized family label (never the raw tool name) + a count
 * when the same family repeats, plus a trailing state dot. A group containing
 * a failed step renders as an inline alert with family-specific copy and a
 * Retry action instead. Once the turn ends it collapses to a single summary
 * line that expands the rows on click. Presentational only: no hook access,
 * all inputs arrive as props.
 */
export function AgentActivityTrail({
  steps,
  isStreaming,
  elapsedMs,
  onRetry,
}: AgentActivityTrailProps) {
  const t = useTranslations("Chat");
  const [expanded, setExpanded] = useState(false);

  if (steps.length === 0) return null;

  const groups = groupSteps(steps);

  const rows = (
    <ul className="flex flex-col gap-1">
      {groups.map((group, i) => {
        const icon = FAMILY_ICON[group.family] ?? FAMILY_ICON.working;

        if (group.status === "error") {
          return (
            <li
              key={group.key}
              className="tp-row-in flex flex-col gap-1 rounded-sm border border-status-cancelled/40 bg-status-cancelled/10 px-2 py-1.5 text-status-cancelled"
              style={{ animationDelay: `${Math.min(i, 6) * 30}ms` }}
            >
              <div className="flex items-center gap-2">
                <span aria-hidden="true" className="flex h-4 w-4 shrink-0 items-center justify-center">
                  {icon}
                </span>
                <span className="flex-1 text-xs font-semibold">
                  {t(`activity.error.${group.family}`)}
                </span>
                {onRetry ? (
                  <button
                    type="button"
                    onClick={onRetry}
                    className="shrink-0 rounded-pill bg-panel px-2 py-0.5 text-[0.68rem] font-bold text-status-cancelled transition-colors duration-150 hover:bg-panel-raised"
                  >
                    {t("activity.retry")}
                  </button>
                ) : null}
              </div>
            </li>
          );
        }

        return (
          <li
            key={group.key}
            className="tp-row-in flex items-center gap-2 text-xs text-muted"
            style={{ animationDelay: `${Math.min(i, 6) * 30}ms` }}
          >
            <span aria-hidden="true" className="flex h-4 w-4 shrink-0 items-center justify-center text-muted">
              {icon}
            </span>
            <span
              aria-hidden="true"
              className={cn("h-1.5 w-1.5 shrink-0 rounded-pill", STATUS_DOT[group.status])}
            />
            <span className="flex-1">
              {t(`activity.${group.family}`)}
              {group.count > 1 ? (
                <span className="ml-1 font-semibold text-faint">×{group.count}</span>
              ) : null}
            </span>
          </li>
        );
      })}
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
